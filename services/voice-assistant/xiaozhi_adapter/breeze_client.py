"""Bounded local Breeze HTTP client. Optional HTTP dependency is imported lazily."""
import asyncio
from contextlib import asynccontextmanager
from dataclasses import dataclass
import io
import ipaddress
import math
import os
from pathlib import Path
import re
import tempfile
import time
from urllib.parse import urlsplit
import wave

SAMPLE_RATE = 24000
BYTES_PER_SAMPLE = 2
SAMPLES_PER_MODEL_FRAME = 1920  # Breeze generates 12.5 frames/second.
MAX_AUDIO_BYTES = 16 * 1024 * 1024


class BreezeError(RuntimeError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


class BreezeCancelled(BreezeError):
    def __init__(self):
        super().__init__('cancelled', 'Local Breeze speech was cancelled.')


class BreezeBusy(BreezeError):
    def __init__(self):
        super().__init__('busy', 'Local Breeze speech is busy; try again later.')


@dataclass(frozen=True)
class BreezeConfig:
    base_url: str = 'http://127.0.0.1:7861'
    voice_id: str = 'guanlang_playful_girl'
    timeout_seconds: float = 45
    max_text_chars: int = 2000
    max_frames: int = 750
    max_audio_bytes: int = 8 * 1024 * 1024

    def __post_init__(self):
        if not isinstance(self.base_url, str):
            raise ValueError('A numeric loopback Breeze URL is required.')
        try:
            parsed = urlsplit(self.base_url)
            address = ipaddress.ip_address(parsed.hostname or '')
            port = parsed.port
        except (ValueError, TypeError):
            raise ValueError('A numeric loopback Breeze URL is required.') from None
        if (parsed.scheme != 'http' or not address.is_loopback or port is None or
                not 1 <= port <= 65535 or parsed.username is not None or parsed.password is not None or
                parsed.path not in {'', '/'} or parsed.query or parsed.fragment or
                any(character.isspace() for character in self.base_url) or '%' in (parsed.hostname or '')):
            raise ValueError('Only an HTTP numeric loopback host and explicit port are allowed.')
        if not isinstance(self.voice_id, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,64}', self.voice_id):
            raise ValueError('A configured saved Breeze voice id is required.')
        if (isinstance(self.timeout_seconds, bool) or
                not isinstance(self.timeout_seconds, (int, float)) or
                not math.isfinite(self.timeout_seconds) or not 0.1 <= self.timeout_seconds <= 120):
            raise ValueError('Breeze timeout must be between 0.1 and 120 seconds.')
        for value, minimum, maximum in ((self.max_text_chars, 1, 2000),
                (self.max_frames, 1, 1500), (self.max_audio_bytes, 2, MAX_AUDIO_BYTES)):
            if type(value) is not int or not minimum <= value <= maximum:
                raise ValueError('Invalid Breeze input, frame or byte limit.')
        object.__setattr__(self, 'base_url', self.base_url.rstrip('/'))

    @property
    def pcm_byte_limit(self):
        return min(self.max_audio_bytes, self.max_frames * SAMPLES_PER_MODEL_FRAME * BYTES_PER_SAMPLE)


@asynccontextmanager
async def _http_transport(endpoint, fields, timeout):
    # No session is kept across upstream asyncio.run() calls or their event loops.
    import aiohttp
    limits = aiohttp.ClientTimeout(total=timeout, connect=min(5, timeout), sock_read=min(10, timeout))
    async with aiohttp.ClientSession(timeout=limits, trust_env=False, auto_decompress=False) as session:
        async with session.post(endpoint, data=fields, allow_redirects=False) as response:
            yield response


def _check_cancel(cancelled):
    if cancelled and cancelled():
        raise BreezeCancelled()


def wrap_pcm_as_wave(pcm):
    if not isinstance(pcm, bytes) or not pcm or len(pcm) % BYTES_PER_SAMPLE:
        raise BreezeError('invalid_audio', 'Breeze returned invalid PCM audio.')
    result = io.BytesIO()
    with wave.open(result, 'wb') as audio:
        audio.setnchannels(1)
        audio.setsampwidth(BYTES_PER_SAMPLE)
        audio.setframerate(SAMPLE_RATE)
        audio.writeframes(pcm)
    return result.getvalue()


def _check_deadline(deadline):
    if time.monotonic() >= deadline:
        raise BreezeError('timeout', 'Local Breeze speech timed out.')


def _write_wave(data, target_path, cancelled, deadline):
    target = Path(target_path)
    if target.suffix.lower() != '.wav':
        raise BreezeError('invalid_output', 'Breeze output must be a WAV file.')
    _check_cancel(cancelled)
    _check_deadline(deadline)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=target.parent, prefix='.breeze-', suffix='.wav', delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(data)
        _check_cancel(cancelled)
        _check_deadline(deadline)
        os.replace(temporary, target)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


class BreezeClient:
    def __init__(self, config=None, *, transport=None):
        self.config = config or BreezeConfig()
        self._transport = transport or _http_transport

    async def _fetch_pcm(self, text, pcm_callback=None):
        # All fields are fixed or trusted configuration, apart from plain speech
        # text. Never accept a reference upload, URL or voice from the text.
        fields = {'text': text, 'voice_id': self.config.voice_id,
                  'max_new_tokens': str(self.config.max_frames)}
        endpoint = self.config.base_url + '/v1/audio/speech'
        try:
            async with self._transport(endpoint, fields, self.config.timeout_seconds) as response:
                status = response.status
                if status == 409:
                    raise BreezeBusy()
                if status == 404:
                    raise BreezeError('voice_missing', 'The saved Breeze voice is unavailable.')
                if 300 <= status < 400:
                    raise BreezeError('redirect_rejected', 'Breeze redirects are not allowed.')
                if status != 200:
                    raise BreezeError('http_error', 'Local Breeze speech failed.')
                headers = {str(key).lower(): str(value).strip() for key, value in response.headers.items()}
                if (headers.get('content-type', '').split(';', 1)[0].lower() != 'audio/pcm' or
                        headers.get('x-sample-rate') != str(SAMPLE_RATE) or
                        headers.get('x-sample-format', '').lower() != 's16le' or
                        headers.get('content-encoding', '').lower() not in {'', 'identity'}):
                    raise BreezeError('invalid_format', 'Breeze must return mono 24 kHz s16le PCM.')
                pcm = bytearray()
                total = 0
                pending = b""
                async for chunk in response.content.iter_chunked(16384):
                    if not isinstance(chunk, bytes):
                        raise BreezeError('invalid_audio', 'Breeze returned invalid audio data.')
                    total += len(chunk)
                    if total > self.config.pcm_byte_limit:
                        raise BreezeError('audio_limit', 'Breeze audio exceeded the configured limit.')
                    if pcm_callback is None:
                        pcm.extend(chunk)
                    else:
                        pending += chunk
                        aligned = len(pending) - len(pending) % BYTES_PER_SAMPLE
                        if aligned:
                            pcm_callback(pending[:aligned])
                            pending = pending[aligned:]
                if not total or total % BYTES_PER_SAMPLE:
                    raise BreezeError('invalid_audio', 'Breeze returned empty or truncated PCM.')
                return bytes(pcm) if pcm_callback is None else total
        except BreezeError:
            raise
        except asyncio.TimeoutError:
            raise BreezeError('timeout', 'Local Breeze speech timed out.') from None
        except ImportError:
            raise BreezeError('dependency_missing', 'The local Breeze HTTP dependency is unavailable.') from None
        except Exception:
            # Do not expose response text, spoken content, URLs or request details.
            raise BreezeError('transport_error', 'Local Breeze speech transport failed.') from None

    async def _watch(self, deadline, cancelled):
        while True:
            _check_cancel(cancelled)
            if time.monotonic() >= deadline:
                raise BreezeError('timeout', 'Local Breeze speech timed out.')
            await asyncio.sleep(min(0.025, max(0.001, deadline-time.monotonic())))

    async def stream_pcm(self, text, callback, *, cancelled=None):
        """Deliver aligned PCM before EOF; callers flush codecs only on success."""
        if (not isinstance(text, str) or not text.strip() or chr(0) in text or
                len(text) > self.config.max_text_chars or not callable(callback)):
            raise BreezeError('invalid_text', 'Breeze speech text or callback is invalid.')
        _check_cancel(cancelled)
        deadline = time.monotonic() + self.config.timeout_seconds

        def deliver(pcm):
            _check_cancel(cancelled)
            _check_deadline(deadline)
            callback(pcm)
            _check_cancel(cancelled)
            _check_deadline(deadline)

        operation = asyncio.create_task(self._fetch_pcm(text, deliver))
        watcher = asyncio.create_task(self._watch(deadline, cancelled))
        try:
            await asyncio.wait((operation, watcher), return_when=asyncio.FIRST_COMPLETED)
            if not operation.done():
                await watcher
            count = await operation
            _check_cancel(cancelled)
            _check_deadline(deadline)
            return count
        finally:
            for task in (operation, watcher):
                if not task.done():
                    task.cancel()
            await asyncio.gather(operation, watcher, return_exceptions=True)

    async def synthesize(self, text, output_file=None, *, cancelled=None):
        if (not isinstance(text, str) or not text.strip() or chr(0) in text or
                len(text) > self.config.max_text_chars):
            raise BreezeError('invalid_text', 'Breeze speech text is empty or exceeds its limit.')
        _check_cancel(cancelled)
        if output_file is not None and Path(output_file).suffix.lower() != '.wav':
            raise BreezeError('invalid_output', 'Breeze output must be a WAV file.')
        deadline = time.monotonic() + self.config.timeout_seconds
        operation = asyncio.create_task(self._fetch_pcm(text))
        watcher = asyncio.create_task(self._watch(deadline, cancelled))
        try:
            await asyncio.wait((operation, watcher), return_when=asyncio.FIRST_COMPLETED)
            if not operation.done():
                await watcher  # Raises the classified timeout/cancellation.
            pcm = await operation
            _check_cancel(cancelled)
            if time.monotonic() >= deadline:
                raise BreezeError('timeout', 'Local Breeze speech timed out.')
            data = wrap_pcm_as_wave(pcm)
            _check_cancel(cancelled)
            _check_deadline(deadline)
            if output_file is not None:
                _write_wave(data, output_file, cancelled, deadline)
                return None
            return data
        finally:
            # Cancelling the HTTP task exits both context managers and closes
            # this connection. Never terminate the shared Breeze process.
            for task in (operation, watcher):
                if not task.done():
                    task.cancel()
            await asyncio.gather(operation, watcher, return_exceptions=True)
