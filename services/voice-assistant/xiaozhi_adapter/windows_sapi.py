"""Copy beside sapi_client.py and sapi_worker.ps1 in core/providers/tts/."""
import asyncio
import logging
import threading

from core.providers.tts.base import TTSProviderBase
from core.providers.tts.dto.dto import SentenceType
from core.utils.tts import MarkdownCleaner
from core.utils.util import audio_bytes_to_data_stream
from .sapi_client import SapiClient, SapiConfig, SapiCancelled, SapiError


logger = logging.getLogger(__name__)


class TTSProvider(TTSProviderBase):
    def __init__(self, config, delete_audio_file):
        super().__init__(config, delete_audio_file)
        self.audio_file_type = 'wav'
        self._closed = threading.Event()
        self.client = SapiClient(SapiConfig(
            voice=config.get('voice', 'Microsoft Huihui Desktop'),
            rate=config.get('rate', 0), volume=config.get('volume', 100),
            timeout_seconds=self.tts_timeout))

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

    def _sentence(self):
        # The queued turn owns the text; conn.sentence_id may already be newer.
        return getattr(self, 'current_sentence_id', getattr(self.conn, 'sentence_id', None))

    async def text_to_speak(self, text, output_file):
        sentence = self._sentence()
        try:
            return await self.client.synthesize(text, output_file,
                cancelled=lambda: self._cancelled(sentence))
        except SapiCancelled:
            return None

    def _clean(self, text):
        text = MarkdownCleaner.clean_markdown(text)
        if self._correct_words_pattern:
            text = self._correct_words_pattern.sub(lambda match: self.correct_words[match.group(0)], text)
        return text

    def to_tts_stream(self, text, opus_handler=None):
        # One attempt: the upstream base otherwise repeats a timeout five times.
        sentence = self._sentence()
        if self._cancelled(sentence):
            return
        try:
            data = asyncio.run(self.text_to_speak(self._clean(text), None))
            if not data or self._cancelled(sentence):
                return
            self.tts_audio_queue.put((SentenceType.FIRST, None, text, sentence))

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
        except SapiError:
            logger.warning('local_sapi.synthesis_failed')
            return

    def to_tts(self, text):
        sentence = self._sentence()
        if self._cancelled(sentence):
            return None
        try:
            output = None if self.delete_audio_file else self.generate_filename('.wav')
            data = asyncio.run(self.text_to_speak(self._clean(text), output))
            if self._cancelled(sentence):
                return None
            if output is not None:
                # A cancelled worker never creates its target.
                from pathlib import Path
                return output if Path(output).is_file() else None
            if not data:
                return None
            packets = []
            audio_bytes_to_data_stream(data, file_type='wav', is_opus=True,
                callback=lambda packet: packets.append(packet) if not self._cancelled(sentence) else None,
                sample_rate=getattr(self.conn, 'sample_rate', 16000))
            return None if self._cancelled(sentence) else packets
        except SapiError:
            logger.warning('local_sapi.synthesis_failed')
            return None

    async def close(self):
        self._closed.set()
        await super().close()
