import asyncio
import base64
import importlib.util
import io
import json
from pathlib import Path
import queue
import sys
import tempfile
import threading
import types
import unittest
from unittest.mock import patch
import wave

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from xiaozhi_adapter import sapi_client as sapi


def sample_wave():
    result = io.BytesIO()
    with wave.open(result, 'wb') as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(16000)
        audio.writeframes(b'\0' * 1920)
    return result.getvalue()


class FakeInput:
    def __init__(self, process):
        self.process = process
        self.writes = []
        self.closed = False

    def write(self, value):
        self.writes.append(value)
        if b'"cancel"' in value and self.process.cooperative:
            self.process.finish(1)

    async def drain(self):
        await asyncio.sleep(0)

    def close(self):
        self.closed = True


class FakeOutput:
    def __init__(self, process):
        self.process = process
        self.offset = 0

    async def read(self, limit):
        await self.process.done.wait()
        chunk = self.process.audio[self.offset:self.offset + min(limit, 4096)]
        self.offset += len(chunk)
        return chunk


class FakeProcess:
    def __init__(self, audio=None, *, exit_code=0, hanging=False, cooperative=True):
        self.audio = sample_wave() if audio is None else audio
        self.returncode = None
        self.done = asyncio.Event()
        self.killed = False
        self.cooperative = cooperative
        self.stdin = FakeInput(self)
        self.stdout = FakeOutput(self)
        if not hanging:
            asyncio.get_running_loop().call_later(0.01, self.finish, exit_code)

    def finish(self, code):
        self.returncode = code
        self.done.set()

    async def wait(self):
        await self.done.wait()
        return self.returncode

    def kill(self):
        self.killed = True
        self.finish(-9)


class ConfigTests(unittest.TestCase):
    def test_configuration_rejects_invalid_bounds(self):
        for options in ({'rate': True}, {'rate': 11}, {'volume': -1},
                        {'timeout_seconds': float('inf')}, {'timeout_seconds': 0},
                        {'voice': ''}):
            with self.subTest(options=options), self.assertRaises(ValueError):
                sapi.SapiConfig(**options)

    def test_bad_waves_fail(self):
        for data in (b'', b'RIFF' + b'0' * 50, sample_wave()[:-7]):
            with self.subTest(length=len(data)), self.assertRaises(sapi.SapiError):
                sapi.validate_wave(data)


class ClientTests(unittest.IsolatedAsyncioTestCase):
    def make_client(self, **process_options):
        calls = []
        processes = []

        async def spawn(*args, **kwargs):
            calls.append((args, kwargs))
            process = FakeProcess(**process_options)
            processes.append(process)
            return process

        return sapi.SapiClient(process_factory=spawn), calls, processes

    async def test_plain_text_only_enters_stdin_json(self):
        client, calls, processes = self.make_client()
        text = '你好 $(Remove-Item X) `whoami` " ; <audio src="https://invalid/"> 字'
        result = await client.synthesize(text)
        self.assertEqual(result, sample_wave())
        args, options = calls[0]
        decoded = base64.b64decode(args[-1]).decode('utf-16-le')
        self.assertIn('SpeakAsync(text)', decoded)
        self.assertNotIn(text, decoded)
        self.assertNotIn(text, str(args))
        self.assertEqual(json.loads(processes[0].stdin.writes[0])['text'], text)
        self.assertNotIn('shell', options)
        self.assertEqual(options['stderr'], asyncio.subprocess.DEVNULL)
        self.assertTrue(processes[0].stdin.closed)

    async def test_partial_pipe_reads_are_collected_until_eof(self):
        audio = io.BytesIO()
        with wave.open(audio, 'wb') as stream:
            stream.setnchannels(1)
            stream.setsampwidth(2)
            stream.setframerate(16000)
            stream.writeframes(b'\0' * 320000)
        client, _, _ = self.make_client(audio=audio.getvalue())
        self.assertEqual(await client.synthesize('长语音测试'), audio.getvalue())

    async def test_output_file_contract_is_atomic_wav(self):
        client, _, _ = self.make_client()
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / 'nested' / 'speech.wav'
            self.assertIsNone(await client.synthesize('管廊本地语音测试。', target))
            self.assertEqual(target.read_bytes(), sample_wave())
            self.assertEqual(list(target.parent.glob('.sapi-*')), [])

    async def test_invalid_text_fails_without_process(self):
        client, calls, _ = self.make_client()
        for text in ('', ' ', 'a' * 2001, 'a\0b', None):
            with self.subTest(text_type=type(text).__name__), self.assertRaises(sapi.SapiError):
                await client.synthesize(text)
        self.assertEqual(calls, [])

    async def test_failure_does_not_create_output_or_expose_details(self):
        client, _, _ = self.make_client(audio=b'private upstream error', exit_code=1)
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / 'speech.wav'
            with self.assertRaises(sapi.SapiError) as caught:
                await client.synthesize('测试', target)
            self.assertNotIn('private', str(caught.exception))
            self.assertFalse(target.exists())

    async def test_timeout_sends_cancel_then_kills_unresponsive_worker_once(self):
        client, calls, processes = self.make_client(hanging=True, cooperative=False)
        client.config = sapi.SapiConfig(timeout_seconds=1)
        with self.assertRaisesRegex(sapi.SapiError, 'timed out'):
            await client.synthesize('测试')
        self.assertEqual(len(calls), 1)
        self.assertTrue(processes[0].killed)
        self.assertIn(b'{"cancel":true}\n', processes[0].stdin.writes)
        self.assertTrue(processes[0].stdin.closed)

    async def test_sentence_cancel_discards_audio_and_file(self):
        client, _, processes = self.make_client(hanging=True)
        cancelled = threading.Event()
        asyncio.get_running_loop().call_later(0.03, cancelled.set)
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / 'speech.wav'
            with self.assertRaises(sapi.SapiCancelled):
                await client.synthesize('测试', target, cancelled=cancelled.is_set)
            self.assertFalse(target.exists())
        self.assertEqual(processes[0].returncode, 1)
        self.assertFalse(processes[0].killed)

    async def test_async_task_cancel_reaps_worker(self):
        client, _, processes = self.make_client(hanging=True)
        task = asyncio.create_task(client.synthesize('测试'))
        await asyncio.sleep(0.03)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertEqual(processes[0].returncode, 1)
        self.assertTrue(processes[0].stdin.closed)

    async def test_late_reply_is_rejected_before_file_write(self):
        client, _, _ = self.make_client()
        checks = 0

        def cancelled():
            nonlocal checks
            checks += 1
            return checks >= 3

        with self.assertRaises(sapi.SapiCancelled):
            await client.synthesize('测试', cancelled=cancelled)

    async def test_corrupt_audio_never_creates_target(self):
        client, _, _ = self.make_client(audio=sample_wave()[:-5])
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / 'speech.wav'
            with self.assertRaises(sapi.SapiError):
                await client.synthesize('测试', target)
            self.assertFalse(target.exists())


def load_provider():
    # The real upstream base imports torch/audio/network dependencies. Its adapter
    # contract is represented here so offline tests need only the standard library.
    modules = {name: types.ModuleType(name) for name in (
        'core', 'core.providers', 'core.providers.tts', 'core.providers.tts.dto',
        'core.providers.tts.base', 'core.providers.tts.dto.dto',
        'core.utils', 'core.utils.tts', 'core.utils.util')}

    class Base:
        def __init__(self, config, delete):
            self.conn = None
            self.tts_timeout = 15
            self.delete_audio_file = delete
            self._correct_words_pattern = None
            self.tts_audio_queue = queue.Queue()

        def handle_opus(self, packet):
            raise AssertionError('The adapter should attach its captured sentence id.')

        async def close(self):
            pass

    modules['core.providers.tts.base'].TTSProviderBase = Base
    modules['core.providers.tts.dto.dto'].SentenceType = types.SimpleNamespace(FIRST='first', MIDDLE='middle')
    modules['core.utils.tts'].MarkdownCleaner = types.SimpleNamespace(clean_markdown=lambda value: value)
    modules['core.utils.util'].audio_bytes_to_data_stream = lambda *args, **kwargs: kwargs['callback'](b'opus')
    spec = importlib.util.spec_from_file_location('xiaozhi_adapter.windows_sapi',
                                                ROOT / 'xiaozhi_adapter' / 'windows_sapi.py')
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, modules):
        spec.loader.exec_module(module)
    return module


class ProviderTests(unittest.TestCase):
    def test_timeout_is_one_attempt_for_both_upstream_paths(self):
        module = load_provider()
        provider = module.TTSProvider({}, True)
        attempts = []

        async def fail(*args, **kwargs):
            attempts.append(1)
            raise sapi.SapiError('timeout')

        provider.client.synthesize = fail
        provider.to_tts_stream('测试')
        self.assertEqual(len(attempts), 1)
        self.assertIsNone(provider.to_tts('测试'))
        self.assertEqual(len(attempts), 2)
        self.assertTrue(provider.tts_audio_queue.empty())

    def test_sentence_change_drops_completed_wave(self):
        module = load_provider()
        provider = module.TTSProvider({}, True)
        provider.conn = types.SimpleNamespace(sentence_id='old', client_abort=False,
            stop_event=threading.Event(), sample_rate=16000)

        async def late(*args, **kwargs):
            provider.conn.sentence_id = 'new'
            return sample_wave()

        provider.client.synthesize = late
        provider.to_tts_stream('测试')
        self.assertTrue(provider.tts_audio_queue.empty())

    def test_queued_old_turn_cannot_be_relabelled_as_new_turn(self):
        module = load_provider()
        provider = module.TTSProvider({}, True)
        provider.current_sentence_id = 'old'
        provider.conn = types.SimpleNamespace(sentence_id='new', client_abort=False,
            stop_event=threading.Event(), sample_rate=16000)

        async def forbidden(*args, **kwargs):
            raise AssertionError('A stale queued turn must not synthesize.')

        provider.client.synthesize = forbidden
        provider.to_tts_stream('旧问题')
        self.assertIsNone(provider.to_tts('旧问题'))
        self.assertTrue(provider.tts_audio_queue.empty())

    def test_stream_packets_carry_captured_sentence(self):
        module = load_provider()
        provider = module.TTSProvider({}, True)
        provider.conn = types.SimpleNamespace(sentence_id='sentence-1', client_abort=False,
            stop_event=threading.Event(), sample_rate=16000)

        async def success(*args, **kwargs):
            return sample_wave()

        provider.client.synthesize = success
        provider.to_tts_stream('测试', provider.handle_opus)
        self.assertEqual(provider.tts_audio_queue.get(), ('first', None, '测试', 'sentence-1'))
        self.assertEqual(provider.tts_audio_queue.get(), ('middle', b'opus', None, 'sentence-1'))


if __name__ == '__main__':
    unittest.main()
