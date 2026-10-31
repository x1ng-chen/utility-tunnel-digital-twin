"""Local SAPI process client; standard-library imports only."""
import asyncio
import base64
from dataclasses import dataclass
import io
import json
import math
import os
from pathlib import Path
import subprocess
import tempfile
import time
import wave

MAX_WAVE_BYTES = 16 * 1024 * 1024


class SapiError(RuntimeError):
    pass


class SapiCancelled(SapiError):
    pass


@dataclass(frozen=True)
class SapiConfig:
    voice: str = 'Microsoft Huihui Desktop'
    rate: int = 0
    volume: int = 100
    timeout_seconds: float = 15

    def __post_init__(self):
        if not isinstance(self.voice, str) or not self.voice.strip() or len(self.voice) > 160:
            raise ValueError('A local Chinese voice name is required.')
        for value, low, high in ((self.rate, -10, 10), (self.volume, 0, 100)):
            if type(value) is not int or not low <= value <= high:
                raise ValueError('Invalid local speech rate or volume.')
        if (isinstance(self.timeout_seconds, bool) or
                not isinstance(self.timeout_seconds, (int, float)) or
                not math.isfinite(self.timeout_seconds) or not 1 <= self.timeout_seconds <= 90):
            raise ValueError('Local speech timeout must be between 1 and 90 seconds.')


def worker_command():
    script = Path(__file__).with_name('sapi_worker.ps1').read_text(encoding='utf-8-sig')
    encoded = base64.b64encode(script.encode('utf-16-le')).decode('ascii')
    executable = str(Path(os.environ.get('SystemRoot', r'C:\Windows')) /
                     'System32/WindowsPowerShell/v1.0/powershell.exe')
    # Only fixed, checked-in code enters EncodedCommand. Speech enters stdin.
    return [executable, '-NoLogo', '-NoProfile', '-NonInteractive', '-STA',
            '-EncodedCommand', encoded]


def validate_wave(data):
    if not isinstance(data, bytes) or not 44 <= len(data) <= MAX_WAVE_BYTES:
        raise SapiError('Local speech returned invalid audio.')
    try:
        with wave.open(io.BytesIO(data), 'rb') as audio:
            if (audio.getnchannels() != 1 or audio.getsampwidth() != 2 or
                    audio.getframerate() != 16000 or audio.getcomptype() != 'NONE' or
                    audio.getnframes() <= 0 or
                    len(audio.readframes(audio.getnframes())) != audio.getnframes() * 2):
                raise ValueError('invalid PCM')
    except (wave.Error, EOFError, ValueError):
        raise SapiError('Local speech returned invalid audio.') from None
    return data


def _check_cancel(cancelled):
    if cancelled and cancelled():
        raise SapiCancelled('Local speech was cancelled.')


def _write_wave(data, output_file, cancelled):
    target = Path(output_file)
    if target.suffix.lower() != '.wav':
        raise SapiError('Local speech output must be a WAV file.')
    _check_cancel(cancelled)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=target.parent, prefix='.sapi-', suffix='.wav', delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(data)
        _check_cancel(cancelled)
        os.replace(temporary, target)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


async def _read_wave_stream(stream):
    data = bytearray()
    while True:
        chunk = await stream.read(min(65536, MAX_WAVE_BYTES + 1 - len(data)))
        if not chunk:
            return bytes(data)
        data.extend(chunk)
        if len(data) > MAX_WAVE_BYTES:
            raise SapiError('Local speech returned oversized audio.')


class SapiClient:
    def __init__(self, config=None, *, process_factory=None, command=None):
        self.config = config or SapiConfig()
        self._factory = process_factory or asyncio.create_subprocess_exec
        self._command = command
        self._injected_factory = process_factory is not None

    async def _stop(self, process):
        if process.returncode is not None:
            return
        try:
            process.stdin.write(b'{"cancel":true}\n')
            await asyncio.wait_for(process.stdin.drain(), 0.2)
        except (BrokenPipeError, ConnectionResetError, RuntimeError, asyncio.TimeoutError):
            pass
        try:
            await asyncio.wait_for(process.wait(), 1)
        except asyncio.TimeoutError:
            try:
                process.kill()
            except ProcessLookupError:
                pass
            await process.wait()

    async def synthesize(self, text, output_file=None, *, cancelled=None):
        if not isinstance(text, str) or not text.strip() or len(text) > 2000 or chr(0) in text:
            raise SapiError('Local speech requires 1 to 2000 text characters.')
        _check_cancel(cancelled)
        if os.name != 'nt' and not self._injected_factory:
            raise SapiError('Local SAPI speech requires Windows.')
        deadline = time.monotonic() + self.config.timeout_seconds
        command = self._command if self._command is not None else worker_command()
        process = None
        reader = None
        waiter = None
        try:
            # Avoid copying platform credentials into the speech worker.
            allowed = {'systemroot', 'windir', 'temp', 'tmp', 'userprofile', 'localappdata',
                       'appdata', 'programfiles', 'programfiles(x86)', 'commonprogramfiles',
                       'processor_architecture', 'path'}
            environment = {key: value for key, value in os.environ.items() if key.lower() in allowed}
            process = await asyncio.wait_for(self._factory(
                *command, stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0), env=environment),
                timeout=max(0.01, deadline - time.monotonic()))
            reader = asyncio.create_task(_read_wave_stream(process.stdout))
            waiter = asyncio.create_task(process.wait())
            request = {'text': text, 'voice': self.config.voice, 'rate': self.config.rate,
                       'volume': self.config.volume,
                       'timeout_ms': max(500, int((deadline - time.monotonic()) * 1000))}
            process.stdin.write(json.dumps(request, ensure_ascii=True).encode('ascii') + b'\n')
            await asyncio.wait_for(process.stdin.drain(), max(0.01, deadline - time.monotonic()))
            # Keep stdin open. A later control line or EOF cancels the worker.
            while not waiter.done():
                _check_cancel(cancelled)
                if time.monotonic() >= deadline:
                    raise asyncio.TimeoutError()
                if reader.done() and len(reader.result()) > MAX_WAVE_BYTES:
                    raise SapiError('Local speech returned oversized audio.')
                await asyncio.sleep(min(0.025, max(0.001, deadline - time.monotonic())))
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise asyncio.TimeoutError()
            data = await asyncio.wait_for(reader, remaining)
            _check_cancel(cancelled)
            if process.returncode != 0:
                raise SapiError('Local Chinese speech is unavailable; verify the installed voice.')
            data = validate_wave(data)
            if output_file is not None:
                _write_wave(data, output_file, cancelled)
                return None
            return data
        except asyncio.TimeoutError:
            raise SapiError('Local speech synthesis timed out.') from None
        except (OSError, UnicodeError):
            raise SapiError('Local speech worker could not be started.') from None
        finally:
            if process is not None:
                await asyncio.shield(self._stop(process))
                if process.stdin is not None:
                    process.stdin.close()
            for task in (reader, waiter):
                if task is not None and not task.done():
                    task.cancel()
            await asyncio.gather(*(task for task in (reader, waiter) if task is not None),
                                 return_exceptions=True)
