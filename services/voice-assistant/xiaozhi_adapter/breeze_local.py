"""xiaozhi TTS adapter for the loopback Breeze native PCM endpoint."""
import asyncio
import logging
from pathlib import Path
import threading
import time

from core.providers.tts.base import TTSProviderBase
from core.providers.tts.dto.dto import SentenceType
from core.utils.tts import MarkdownCleaner
from core.utils.util import audio_bytes_to_data_stream
from .breeze_client import BreezeClient, BreezeConfig, BreezeCancelled, BreezeError

logger = logging.getLogger(__name__)


def speech_segments(text):
    """Keep every character; bound first synthesis before queuing its audio."""
    start = 0
    first = True
    boundaries = frozenset('。！？；，：、\n,!?;: ')
    while start < len(text):
        limit = 24 if first else 36
        end = min(start + limit, len(text))
        if end < len(text):
            # Prefer a complete clause; never discard the unsent remainder.
            candidates = [i + 1 for i in range(start, end) if text[i] in boundaries]
            if candidates:
                end = candidates[-1]
        yield text[start:end]
        start = end
        first = False


class PcmOpusStream:
    """One owned resampler/encoder, with continuous sample and 60ms frame state."""
    def __init__(self, sample_rate, callback, cancelled):
        self.encoder = None
        self.resampler = None
        self.pending = bytearray()
        self.finished = False
        self.closed = False
        self.callback = callback
        self.cancelled = cancelled
        if type(sample_rate) is not int or sample_rate not in {8000, 12000, 16000, 24000, 48000}:
            raise BreezeError('invalid_format', 'Unsupported Opus sample rate.')
        self.frame_samples = sample_rate * 60 // 1000
        self.frame_bytes = self.frame_samples * 2
        try:
            import numpy as np
            import soxr
            from opuslib_next import Encoder, constants
            self.np = np
            if sample_rate != 24000:
                self.resampler = soxr.ResampleStream(24000, sample_rate, 1, dtype='int16', quality='HQ')
            self.encoder = Encoder(sample_rate, 1, constants.APPLICATION_AUDIO)
            self.encoder.bitrate = 24000
            self.encoder.complexity = 10
            self.encoder.signal = constants.SIGNAL_VOICE
        except ImportError:
            self.close()
            raise BreezeError('dependency_missing', 'Streaming audio dependencies are unavailable.') from None
        except Exception:
            self.close()
            raise BreezeError('codec_error', 'Local speech codec initialization failed.') from None

    def _check(self):
        if self.closed or self.finished:
            raise BreezeError('codec_closed', 'Local speech codec is closed.')
        if self.cancelled():
            raise BreezeCancelled()

    def _emit(self, frame):
        self._check()
        try:
            packet = self.encoder.encode(frame, self.frame_samples)
        except Exception:
            raise BreezeError('codec_error', 'Local speech encoding failed.') from None
        if not isinstance(packet, bytes) or not packet or len(packet) > 2048:
            raise BreezeError('codec_error', 'Invalid local speech packet.')
        self._check()
        self.callback(packet)

    def feed(self, pcm, final=False):
        self._check()
        if not isinstance(pcm, bytes) or len(pcm) % 2:
            raise BreezeError('invalid_audio', 'Unaligned local speech audio.')
        samples = self.np.frombuffer(pcm, dtype='<i2')
        try:
            if self.resampler is not None:
                samples = self.resampler.resample_chunk(samples, last=final)
        except Exception:
            raise BreezeError('codec_error', 'Local speech resampling failed.') from None
        self.pending.extend(samples.astype('<i2', copy=False).tobytes())
        while len(self.pending) >= self.frame_bytes:
            frame = bytes(self.pending[:self.frame_bytes])
            del self.pending[:self.frame_bytes]
            self._emit(frame)
        if final:
            if self.pending:
                self._emit(bytes(self.pending).ljust(self.frame_bytes, b'\0'))
                self.pending.clear()
            self.finished = True

    def finish(self):
        self.feed(b'', final=True)

    def close(self):
        # Discard every incomplete old frame. Cancellation must never flush it.
        self.pending.clear()
        self.resampler = None
        self.encoder = None  # opuslib_next owns and destroys its native state.
        self.closed = True


class TTSProvider(TTSProviderBase):
    def __init__(self, config, delete_audio_file):
        super().__init__(config, delete_audio_file)
        self.audio_file_type = 'wav'
        self.stream_pcm = config.get('stream_pcm', True)
        if type(self.stream_pcm) is not bool:
            raise ValueError('stream_pcm must be a boolean.')
        self._closed = threading.Event()
        self.client = BreezeClient(BreezeConfig(
            base_url=config.get('base_url', 'http://127.0.0.1:7861'),
            voice_id=config.get('voice_id', 'guanlang_playful_girl'),
            timeout_seconds=self.tts_timeout,
            max_text_chars=config.get('max_text_chars', 2000),
            max_frames=config.get('max_frames', 750),
            max_audio_bytes=config.get('max_audio_bytes', 8*1024*1024)))

    def _sentence(self):
        return getattr(self, 'current_sentence_id', getattr(self.conn, 'sentence_id', None))

    def _cancelled(self, sentence):
        if self._closed.is_set():
            return True
        connection = self.conn
        if connection is None:
            return False
        stop = getattr(connection, 'stop_event', None)
        return bool((stop is not None and stop.is_set()) or
                    getattr(connection, 'client_abort', False) or
                    sentence != getattr(connection, 'sentence_id', None))

    def _clean(self, text):
        text = MarkdownCleaner.clean_markdown(text)
        if self._correct_words_pattern:
            text = self._correct_words_pattern.sub(lambda match: self.correct_words[match.group(0)], text)
        return text

    async def text_to_speak(self, text, output_file):
        sentence = self._sentence()
        try:
            return await self.client.synthesize(text, output_file,
                cancelled=lambda: self._cancelled(sentence))
        except BreezeCancelled:
            return None

    def _to_native_pcm_stream(self, text, opus_handler):
        sentence = self._sentence()
        if self._cancelled(sentence):
            return
        codec = None
        first = True
        try:
            def emit(packet):
                nonlocal first
                if self._cancelled(sentence):
                    raise BreezeCancelled()
                if first:
                    self.tts_audio_queue.put((SentenceType.FIRST, None, text, sentence))
                    first = False
                if opus_handler is None or opus_handler == self.handle_opus:
                    self.tts_audio_queue.put((SentenceType.MIDDLE, packet, None, sentence))
                else:
                    opus_handler(packet)

            codec = PcmOpusStream(self.conn.sample_rate, emit, lambda: self._cancelled(sentence))
            asyncio.run(self.client.stream_pcm(self._clean(text), codec.feed,
                cancelled=lambda: self._cancelled(sentence)))
            if not self._cancelled(sentence):
                codec.finish()
        except BreezeError as exc:
            if not isinstance(exc, BreezeCancelled):
                logger.warning('local_breeze.%s', exc.code)
        finally:
            if codec is not None:
                codec.close()

    def to_tts_stream(self, text, opus_handler=None):
        if self.stream_pcm:
            return self._to_native_pcm_stream(text, opus_handler)
        # Synthesize short clauses, then queue each immediately. Keep the whole
        # call's original time/byte bounds and captured turn ID across clauses.
        sentence = self._sentence()
        if self._cancelled(sentence):
            return
        try:
            cleaned = self._clean(text)
            if (not cleaned.strip() or chr(0) in cleaned or
                    len(cleaned) > self.client.config.max_text_chars):
                raise BreezeError('invalid_text', 'Invalid local speech text.')
            deadline = time.monotonic() + self.tts_timeout
            total_pcm_bytes = 0
            for segment in speech_segments(cleaned):
                if not segment.strip():
                    continue
                if self._cancelled(sentence):
                    return
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise BreezeError('timeout', 'Local Breeze speech timed out.')

                async def synthesize_segment():
                    return await asyncio.wait_for(self.text_to_speak(segment, None), remaining)

                try:
                    data = asyncio.run(synthesize_segment())
                except asyncio.TimeoutError:
                    raise BreezeError('timeout', 'Local Breeze speech timed out.') from None
                if not data or self._cancelled(sentence):
                    return
                total_pcm_bytes += max(0, len(data) - 44)
                if total_pcm_bytes > self.client.config.pcm_byte_limit:
                    raise BreezeError('audio_limit', 'Local speech exceeded its audio limit.')
                self.tts_audio_queue.put((SentenceType.FIRST, None, segment, sentence))

                def emit(packet):
                    if self._cancelled(sentence):
                        return
                    if opus_handler is None or opus_handler == self.handle_opus:
                        self.tts_audio_queue.put((SentenceType.MIDDLE, packet, None, sentence))
                    else:
                        opus_handler(packet)

                audio_bytes_to_data_stream(data, file_type='wav', is_opus=True, callback=emit,
                    sample_rate=self.conn.sample_rate,
                    opus_encoder=getattr(self, 'opus_encoder', None))
        except BreezeError as exc:
            logger.warning('local_breeze.%s', exc.code)

    def to_tts(self, text):
        sentence = self._sentence()
        if self._cancelled(sentence):
            return None
        try:
            target = None if self.delete_audio_file else self.generate_filename('.wav')
            data = asyncio.run(self.text_to_speak(self._clean(text), target))
            if self._cancelled(sentence):
                return None
            if target is not None:
                return target if Path(target).is_file() else None
            if not data:
                return None
            packets = []
            audio_bytes_to_data_stream(data, file_type='wav', is_opus=True,
                callback=lambda packet: packets.append(packet) if not self._cancelled(sentence) else None,
                sample_rate=getattr(self.conn, 'sample_rate', 16000))
            return None if self._cancelled(sentence) else packets
        except BreezeError as exc:
            logger.warning('local_breeze.%s', exc.code)
            return None

    async def close(self):
        self._closed.set()
        await super().close()
