import asyncio
from contextlib import asynccontextmanager
import importlib.util
import io
from pathlib import Path
import queue
import sys
import tempfile
import threading
import types
import unittest
from unittest.mock import patch
import wave

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from xiaozhi_adapter import breeze_client as breeze

PCM=b'\x00\x01'*480
HEADERS={'Content-Type':'audio/pcm','X-Sample-Rate':'24000','X-Sample-Format':'s16le'}


class Response:
    def __init__(self,chunks=None,status=200,headers=None,delay=0):
        self.status=status
        self.headers=dict(HEADERS if headers is None else headers)
        self.chunks=[PCM] if chunks is None else chunks
        self.delay=delay
        self.content=self

    async def iter_chunked(self,size):
        for chunk in self.chunks:
            if self.delay:
                await asyncio.sleep(self.delay)
            if isinstance(chunk,Exception):
                raise chunk
            yield chunk


class Transport:
    def __init__(self,response=None,connect_delay=0):
        self.response=response or Response()
        self.connect_delay=connect_delay
        self.calls=[]
        self.started=asyncio.Event()
        self.closed=False

    @asynccontextmanager
    async def __call__(self,url,fields,timeout):
        self.calls.append((url,dict(fields),timeout))
        self.started.set()
        try:
            if self.connect_delay:
                await asyncio.sleep(self.connect_delay)
            yield self.response
        finally:
            self.closed=True


def read_wave(data):
    with wave.open(io.BytesIO(data),'rb') as audio:
        return audio.getframerate(),audio.getnchannels(),audio.getsampwidth(),audio.readframes(audio.getnframes())


class ConfigurationTests(unittest.TestCase):
    def test_only_numeric_loopback_with_explicit_port(self):
        for url in ('http://127.0.0.1:7861/','http://[::1]:7861','http://127.0.0.2:7861'):
            self.assertEqual(breeze.BreezeConfig(base_url=url).base_url,url.rstrip('/'))
        for url in ('http://localhost:7861','http://192.168.1.2:7861','http://0.0.0.0:7861',
                    'http://127.0.0.1.evil:7861','http://2130706433:7861','http://127.0.0.1',
                    'http://a:b@127.0.0.1:7861','http://127.0.0.1:7861/other',
                    'http://127.0.0.1:7861?x=1','http://127.0.0.1:7861#x',
                    'https://127.0.0.1:7861','http://[::1%25scope]:7861',None):
            with self.subTest(url=url),self.assertRaises(ValueError):
                breeze.BreezeConfig(base_url=url)

    def test_voice_and_limits_are_checked(self):
        for config in ({'voice_id':'../bad'},{'voice_id':''},{'voice_id':'字'},
                       {'timeout_seconds':True},{'timeout_seconds':float('inf')},{'timeout_seconds':121},
                       {'max_frames':0},{'max_frames':True},{'max_text_chars':2001},
                       {'max_audio_bytes':breeze.MAX_AUDIO_BYTES+1}):
            with self.subTest(config=config),self.assertRaises(ValueError):
                breeze.BreezeConfig(**config)
        self.assertEqual(breeze.BreezeConfig().pcm_byte_limit,2880000)

    def test_import_and_configuration_do_not_require_aiohttp(self):
        with patch.dict(sys.modules,{'aiohttp':None}):
            self.assertEqual(breeze.BreezeClient().config.voice_id,'guanlang_playful_girl')


class ClientTests(unittest.IsolatedAsyncioTestCase):
    async def test_native_form_and_odd_network_chunks_become_correct_24k_wave(self):
        transport=Transport(Response(chunks=[PCM[:1],PCM[1:8],PCM[8:]]))
        client=breeze.BreezeClient(transport=transport)
        text='自然女声 $(whoami) `echo` <xml>我在。</xml>'
        result=await client.synthesize(text)
        self.assertEqual(read_wave(result),(24000,1,2,PCM))
        self.assertEqual(len(transport.calls),1)
        self.assertEqual(transport.calls[0][0],'http://127.0.0.1:7861/v1/audio/speech')
        self.assertEqual(transport.calls[0][1],{'text':text,'voice_id':'guanlang_playful_girl','max_new_tokens':'750'})
        self.assertTrue(transport.closed)

    async def test_pcm_stream_emits_aligned_audio_before_http_eof(self):
        seen=[]
        class StreamingResponse(Response):
            async def iter_chunked(self,size):
                yield PCM[:1]
                self_outer.assertEqual(seen,[])
                yield PCM[1:9]
                self_outer.assertTrue(seen)
                yield PCM[9:]
        self_outer=self
        transport=Transport(StreamingResponse())
        count=await breeze.BreezeClient(transport=transport).stream_pcm('我在。',seen.append)
        self.assertEqual(count,len(PCM))
        self.assertEqual(b''.join(seen),PCM)
        self.assertTrue(all(len(part)%2==0 for part in seen))
        self.assertTrue(transport.closed)

    async def test_pcm_stream_checks_format_before_delivering_any_audio(self):
        transport=Transport(Response(headers={**HEADERS,'X-Sample-Rate':'16000'}))
        seen=[]
        with self.assertRaises(breeze.BreezeError) as caught:
            await breeze.BreezeClient(transport=transport).stream_pcm('我在。',seen.append)
        self.assertEqual(caught.exception.code,'invalid_format')
        self.assertEqual(seen,[])
        self.assertTrue(transport.closed)

    async def test_pcm_stream_cancellation_closes_http_without_replay(self):
        transport=Transport(Response(chunks=[PCM,PCM]))
        seen=[];cancelled=threading.Event()
        def receive(pcm):
            seen.append(pcm)
            cancelled.set()
        with self.assertRaises(breeze.BreezeCancelled):
            await breeze.BreezeClient(transport=transport).stream_pcm('我在。',receive,cancelled=cancelled.is_set)
        self.assertEqual(len(seen),1)
        self.assertEqual(len(transport.calls),1)
        self.assertTrue(transport.closed)

    async def test_pcm_stream_rejects_truncated_eof_and_enforces_audio_budget(self):
        for config,chunks,code in (
                (breeze.BreezeConfig(),[PCM,b'x'],'invalid_audio'),
                (breeze.BreezeConfig(max_audio_bytes=len(PCM)),[PCM,PCM],'audio_limit')):
            seen=[];transport=Transport(Response(chunks=chunks))
            with self.subTest(code=code),self.assertRaises(breeze.BreezeError) as caught:
                await breeze.BreezeClient(config,transport=transport).stream_pcm('我在。',seen.append)
            self.assertEqual(caught.exception.code,code)
            self.assertEqual(b''.join(seen),PCM)
            self.assertTrue(transport.closed)

    async def test_pcm_stream_total_timeout_closes_stalled_response(self):
        transport=Transport(Response(chunks=[PCM],delay=1))
        seen=[]
        with self.assertRaises(breeze.BreezeError) as caught:
            await breeze.BreezeClient(breeze.BreezeConfig(timeout_seconds=0.1),transport=transport).stream_pcm('我在。',seen.append)
        self.assertEqual(caught.exception.code,'timeout')
        self.assertEqual(seen,[])
        self.assertTrue(transport.closed)

    async def test_file_contract_and_temporary_cleanup(self):
        transport=Transport()
        with tempfile.TemporaryDirectory() as directory:
            target=Path(directory)/'nested/speech.wav'
            self.assertIsNone(await breeze.BreezeClient(transport=transport).synthesize('我在。',target))
            self.assertEqual(read_wave(target.read_bytes()),(24000,1,2,PCM))
            self.assertEqual(list(target.parent.glob('.breeze-*')),[])

    async def test_busy_is_one_request_without_retry_or_body_replay(self):
        transport=Transport(Response(status=409))
        with self.assertRaises(breeze.BreezeBusy) as caught:
            await breeze.BreezeClient(transport=transport).synthesize('我在。')
        self.assertEqual(caught.exception.code,'busy')
        self.assertEqual(len(transport.calls),1)
        self.assertTrue(transport.closed)

    async def test_missing_voice_never_falls_back(self):
        transport=Transport(Response(status=404,chunks=[b'private response']))
        with self.assertRaises(breeze.BreezeError) as caught:
            await breeze.BreezeClient(transport=transport).synthesize('我在。')
        self.assertEqual(caught.exception.code,'voice_missing')
        self.assertNotIn('private',str(caught.exception))
        self.assertEqual(len(transport.calls),1)

    async def test_invalid_input_never_sends_http(self):
        transport=Transport()
        client=breeze.BreezeClient(transport=transport)
        for text in ('',' ','a'*2001,'x'+chr(0),None):
            with self.subTest(type=type(text).__name__),self.assertRaises(breeze.BreezeError):
                await client.synthesize(text)
        self.assertEqual(transport.calls,[])

    async def test_bad_output_suffix_is_rejected_before_http(self):
        transport=Transport()
        with self.assertRaises(breeze.BreezeError):
            await breeze.BreezeClient(transport=transport).synthesize('我在。','speech.mp3')
        self.assertEqual(transport.calls,[])

    async def test_response_format_is_verified(self):
        for changed in ({'X-Sample-Rate':'16000'},{'X-Sample-Format':'f32le'},
                        {'Content-Type':'audio/wav'},{'Content-Encoding':'gzip'}):
            headers={**HEADERS,**changed}
            transport=Transport(Response(headers=headers))
            with self.subTest(changed=changed),self.assertRaises(breeze.BreezeError) as caught:
                await breeze.BreezeClient(transport=transport).synthesize('我在。')
            self.assertEqual(caught.exception.code,'invalid_format')
            self.assertTrue(transport.closed)

    async def test_empty_and_odd_final_pcm_are_rejected(self):
        for chunks in ([],[b'1'],[PCM,b'1']):
            transport=Transport(Response(chunks=chunks))
            with self.subTest(chunks=len(chunks)),self.assertRaises(breeze.BreezeError):
                await breeze.BreezeClient(transport=transport).synthesize('我在。')

    async def test_frame_and_byte_caps_close_response(self):
        for config,chunks in ((breeze.BreezeConfig(max_frames=1),[b'0'*3842]),
                              (breeze.BreezeConfig(max_audio_bytes=10),[b'0'*12])):
            transport=Transport(Response(chunks=chunks))
            with self.subTest(limit=config.pcm_byte_limit),self.assertRaises(breeze.BreezeError) as caught:
                await breeze.BreezeClient(config,transport=transport).synthesize('我在。')
            self.assertEqual(caught.exception.code,'audio_limit')
            self.assertEqual(len(transport.calls),1)
            self.assertTrue(transport.closed)

    async def test_transport_truncation_preserves_existing_target(self):
        transport=Transport(Response(chunks=[PCM,RuntimeError('private upstream error')]))
        with tempfile.TemporaryDirectory() as directory:
            target=Path(directory)/'speech.wav'
            target.write_bytes(b'previous file')
            with self.assertRaises(breeze.BreezeError) as caught:
                await breeze.BreezeClient(transport=transport).synthesize('我在。',target)
            self.assertEqual(caught.exception.code,'transport_error')
            self.assertNotIn('private',str(caught.exception))
            self.assertEqual(target.read_bytes(),b'previous file')
            self.assertEqual(list(target.parent.glob('.breeze-*')),[])
        self.assertTrue(transport.closed)

    async def test_total_timeout_closes_connecting_request_once(self):
        transport=Transport(connect_delay=60)
        client=breeze.BreezeClient(breeze.BreezeConfig(timeout_seconds=0.1),transport=transport)
        with self.assertRaises(breeze.BreezeError) as caught:
            await client.synthesize('我在。')
        self.assertEqual(caught.exception.code,'timeout')
        self.assertEqual(len(transport.calls),1)
        self.assertTrue(transport.closed)

    async def test_cancel_while_reading_closes_response_and_discards_file(self):
        transport=Transport(Response(chunks=[PCM,PCM],delay=0.05))
        cancelled=threading.Event()
        asyncio.get_running_loop().call_later(0.06,cancelled.set)
        with tempfile.TemporaryDirectory() as directory:
            target=Path(directory)/'speech.wav'
            with self.assertRaises(breeze.BreezeCancelled):
                await breeze.BreezeClient(transport=transport).synthesize('我在。',target,cancelled=cancelled.is_set)
            self.assertFalse(target.exists())
        self.assertTrue(transport.closed)

    async def test_async_task_cancel_closes_request_during_connect(self):
        transport=Transport(connect_delay=60)
        task=asyncio.create_task(breeze.BreezeClient(transport=transport).synthesize('我在。'))
        await transport.started.wait()
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertTrue(transport.closed)

    async def test_cancel_before_request_sends_nothing(self):
        transport=Transport()
        with self.assertRaises(breeze.BreezeCancelled):
            await breeze.BreezeClient(transport=transport).synthesize('我在。',cancelled=lambda:True)
        self.assertEqual(transport.calls,[])

    async def test_late_cancellation_before_file_commit_discards_wave(self):
        transport=Transport()
        cancelled=threading.Event()
        original=breeze.wrap_pcm_as_wave
        def late(pcm):
            result=original(pcm)
            cancelled.set()
            return result
        with tempfile.TemporaryDirectory() as directory:
            target=Path(directory)/'speech.wav'
            with patch.object(breeze,'wrap_pcm_as_wave',late),self.assertRaises(breeze.BreezeCancelled):
                await breeze.BreezeClient(transport=transport).synthesize('我在。',target,cancelled=cancelled.is_set)
            self.assertFalse(target.exists())

    async def test_deadline_crossed_during_wave_wrap_rejects_late_success(self):
        clock={'now':0.0}
        timer=types.SimpleNamespace(monotonic=lambda:clock['now'])
        original=breeze.wrap_pcm_as_wave
        def slow_wrap(pcm):
            result=original(pcm)
            clock['now']=1.0
            return result
        transport=Transport()
        with patch.object(breeze,'time',timer),patch.object(breeze,'wrap_pcm_as_wave',slow_wrap):
            with self.assertRaises(breeze.BreezeError) as caught:
                await breeze.BreezeClient(breeze.BreezeConfig(timeout_seconds=0.1),transport=transport).synthesize('我在。')
        self.assertEqual(caught.exception.code,'timeout')
        self.assertTrue(transport.closed)

    async def test_deadline_crossed_during_disk_write_preserves_previous_file(self):
        clock={'now':0.0}
        timer=types.SimpleNamespace(monotonic=lambda:clock['now'])
        original=breeze.tempfile.NamedTemporaryFile
        def slow_temporary(*args,**kwargs):
            stream=original(*args,**kwargs)
            class Slow:
                name=stream.name
                def __enter__(self):
                    return self
                def write(self,data):
                    stream.write(data)
                    clock['now']=1.0
                def __exit__(self,*values):
                    return stream.__exit__(*values)
            return Slow()
        with tempfile.TemporaryDirectory() as directory:
            target=Path(directory)/'speech.wav'
            target.write_bytes(b'previous file')
            with patch.object(breeze,'time',timer),patch.object(breeze.tempfile,'NamedTemporaryFile',slow_temporary):
                with self.assertRaises(breeze.BreezeError) as caught:
                    await breeze.BreezeClient(breeze.BreezeConfig(timeout_seconds=0.1),transport=Transport()).synthesize('我在。',target)
            self.assertEqual(caught.exception.code,'timeout')
            self.assertEqual(target.read_bytes(),b'previous file')
            self.assertEqual(list(target.parent.glob('.breeze-*')),[])

    async def test_default_http_disables_proxies_redirects_and_decompression(self):
        settings={}
        response=Response(status=307,headers={'Location':'http://external.invalid/target'})
        class Request:
            async def __aenter__(self):
                return response
            async def __aexit__(self,*args):
                settings['response_closed']=True
        class Session:
            def __init__(self,**kwargs):
                settings['session']=kwargs
            async def __aenter__(self):
                return self
            async def __aexit__(self,*args):
                settings['session_closed']=True
            def post(self,url,**kwargs):
                settings.setdefault('posts',[]).append((url,kwargs))
                return Request()
        fake=types.SimpleNamespace(ClientTimeout=lambda **kwargs:kwargs,ClientSession=Session)
        with patch.dict(sys.modules,{'aiohttp':fake}),self.assertRaises(breeze.BreezeError) as caught:
            await breeze.BreezeClient().synthesize('我在。')
        self.assertEqual(caught.exception.code,'redirect_rejected')
        self.assertIs(settings['session']['trust_env'],False)
        self.assertIs(settings['session']['auto_decompress'],False)
        self.assertIs(settings['posts'][0][1]['allow_redirects'],False)
        self.assertEqual(len(settings['posts']),1)
        self.assertTrue(settings['session_closed'] and settings['response_closed'])


def load_provider():
    names=('core','core.providers','core.providers.tts','core.providers.tts.dto',
           'core.providers.tts.base','core.providers.tts.dto.dto',
           'core.utils','core.utils.tts','core.utils.util')
    modules={name:types.ModuleType(name) for name in names}
    class Base:
        def __init__(self,config,delete):
            self.conn=None
            self.delete_audio_file=delete
            self.tts_timeout=config.get('tts_timeout',45)
            self._correct_words_pattern=None
            self.tts_audio_queue=queue.Queue()
        def handle_opus(self,packet):
            raise AssertionError('Capture the queued sentence id instead.')
        async def close(self):
            pass
    modules['core.providers.tts.base'].TTSProviderBase=Base
    modules['core.providers.tts.dto.dto'].SentenceType=types.SimpleNamespace(FIRST='first',MIDDLE='middle')
    modules['core.utils.tts'].MarkdownCleaner=types.SimpleNamespace(clean_markdown=lambda text:text)
    modules['core.utils.util'].audio_bytes_to_data_stream=lambda *args,**kwargs:kwargs['callback'](b'opus')
    spec=importlib.util.spec_from_file_location('xiaozhi_adapter.breeze_local',ROOT/'xiaozhi_adapter/breeze_local.py')
    module=importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules,modules):
        spec.loader.exec_module(module)
    return module


class ProviderTests(unittest.TestCase):
    def connection(self,provider,sentence='current'):
        provider.conn=types.SimpleNamespace(sentence_id=sentence,client_abort=False,
            stop_event=threading.Event(),sample_rate=24000)

    def test_busy_and_timeout_are_not_replayed_by_either_base_path(self):
        for error in (breeze.BreezeBusy(),breeze.BreezeError('timeout','fixed safe failure')):
            module=load_provider()
            provider=module.TTSProvider({'stream_pcm':False},True)
            attempts=[]
            async def fail(*args,**kwargs):
                attempts.append(1)
                raise error
            provider.client.synthesize=fail
            with self.subTest(code=error.code),self.assertLogs('xiaozhi_adapter.breeze_local',level='WARNING') as logs:
                provider.to_tts_stream('private speech content')
                self.assertIsNone(provider.to_tts('private speech content'))
            self.assertEqual(len(attempts),2)
            self.assertTrue(all('private speech content' not in message for message in logs.output))
            self.assertTrue(provider.tts_audio_queue.empty())

    def test_old_queued_turn_is_not_relabelled_or_synthesized(self):
        provider=load_provider().TTSProvider({'stream_pcm':False},True)
        self.connection(provider,'new')
        provider.current_sentence_id='old'
        async def forbidden(*args,**kwargs):
            raise AssertionError('A stale turn must not send HTTP.')
        provider.client.synthesize=forbidden
        provider.to_tts_stream('old speech')
        self.assertIsNone(provider.to_tts('old speech'))
        self.assertTrue(provider.tts_audio_queue.empty())

    def test_new_turn_during_request_discards_old_result(self):
        provider=load_provider().TTSProvider({'stream_pcm':False},True)
        self.connection(provider)
        async def late(*args,**kwargs):
            provider.conn.sentence_id='new'
            return breeze.wrap_pcm_as_wave(PCM)
        provider.client.synthesize=late
        provider.to_tts_stream('old speech')
        self.assertTrue(provider.tts_audio_queue.empty())

    def test_stream_packets_preserve_captured_sentence_id(self):
        provider=load_provider().TTSProvider({'stream_pcm':False},True)
        self.connection(provider)
        async def succeed(*args,**kwargs):
            return breeze.wrap_pcm_as_wave(PCM)
        provider.client.synthesize=succeed
        provider.to_tts_stream('我在。',provider.handle_opus)
        self.assertEqual(provider.tts_audio_queue.get(),('first',None,'我在。','current'))
        self.assertEqual(provider.tts_audio_queue.get(),('middle',b'opus',None,'current'))

    def test_long_reply_preserved_and_audio_queued_before_next_synthesis(self):
        module=load_provider()
        provider=module.TTSProvider({'stream_pcm':False},True)
        self.connection(provider)
        text='以下依据管廊数据库快照回答。P1站目前无法判定为在线。快照显示应有7个传感器，但台账中登记0个。数据时间06:55:58，内容为空。不能给出现场安全结论。'
        calls=[]
        async def synthesize(segment,*args,**kwargs):
            if calls:
                self.assertTrue(any(item[0]=='middle' for item in provider.tts_audio_queue.queue))
            calls.append(segment)
            return breeze.wrap_pcm_as_wave(PCM)
        provider.client.synthesize=synthesize
        provider.to_tts_stream(text)
        self.assertEqual(''.join(calls),text)
        self.assertLessEqual(len(calls[0]),24)
        self.assertTrue(all(len(part)<=36 for part in calls))
        items=list(provider.tts_audio_queue.queue)
        self.assertEqual(''.join(item[2] for item in items if item[0]=='first'),text)
        self.assertTrue(all(item[3]=='current' for item in items))

    def test_cancel_after_first_segment_skips_every_remaining_synthesis(self):
        module=load_provider()
        provider=module.TTSProvider({'stream_pcm':False},True)
        self.connection(provider)
        calls=[]
        async def synthesize(segment,*args,**kwargs):
            calls.append(segment)
            return breeze.wrap_pcm_as_wave(PCM)
        def emit_then_abort(*args,**kwargs):
            kwargs['callback'](b'opus')
            provider.conn.client_abort=True
        provider.client.synthesize=synthesize
        with patch.object(module,'audio_bytes_to_data_stream',emit_then_abort):
            provider.to_tts_stream('这是第一句简短结论。'+'后续证据必须保留。'*8)
        self.assertEqual(len(calls),1)
        self.assertEqual(len(list(provider.tts_audio_queue.queue)),2)

    def test_leading_whitespace_does_not_prevent_spoken_content(self):
        provider=load_provider().TTSProvider({'stream_pcm':False},True)
        self.connection(provider)
        calls=[]
        async def synthesize(segment,*args,**kwargs):
            self.assertTrue(segment.strip())
            calls.append(segment)
            return breeze.wrap_pcm_as_wave(PCM)
        provider.client.synthesize=synthesize
        provider.to_tts_stream(' '*80+'你好。')
        self.assertEqual(''.join(calls).strip(),'你好。')
        self.assertFalse(provider.tts_audio_queue.empty())

    def test_segmented_speech_retains_whole_input_limit(self):
        provider=load_provider().TTSProvider({'stream_pcm':False},True)
        self.connection(provider)
        async def forbidden(*args,**kwargs):
            raise AssertionError('Oversized input must not send HTTP.')
        provider.client.synthesize=forbidden
        with self.assertLogs('xiaozhi_adapter.breeze_local',level='WARNING'):
            provider.to_tts_stream('长'*2001)
        self.assertTrue(provider.tts_audio_queue.empty())

    def test_native_stream_queues_audio_while_body_open_then_flushes_and_releases(self):
        module=load_provider()
        provider=module.TTSProvider({},True)
        self.connection(provider)
        state={'finished':False,'closed':False,'queued_before_eof':False}
        class Codec:
            def __init__(self,rate,callback,cancelled):self.callback=callback
            def feed(self,pcm):self.callback(b'opus')
            def finish(self):state['finished']=True;self.callback(b'tail')
            def close(self):state['closed']=True
        class StreamingResponse(Response):
            async def iter_chunked(self,size):
                yield PCM
                state['queued_before_eof']=not provider.tts_audio_queue.empty()
                yield PCM
        provider.client=breeze.BreezeClient(transport=Transport(StreamingResponse()))
        with patch.object(module,'PcmOpusStream',Codec):
            provider.to_tts_stream('完整回应。')
        items=list(provider.tts_audio_queue.queue)
        self.assertTrue(state['queued_before_eof'] and state['finished'] and state['closed'])
        self.assertEqual(items[0],('first',None,'完整回应。','current'))
        self.assertEqual([i[1] for i in items[1:]],[b'opus',b'opus',b'tail'])
        self.assertTrue(all(i[3]=='current' for i in items))

    def test_native_stream_stale_turn_discards_tail_and_releases_own_codec(self):
        module=load_provider();provider=module.TTSProvider({},True)
        self.connection(provider)
        state={'finished':False,'closed':False}
        class Codec:
            def __init__(self,rate,callback,cancelled):self.callback=callback
            def feed(self,pcm):
                self.callback(b'opus')
                provider.conn.sentence_id='next'
            def finish(self):state['finished']=True
            def close(self):state['closed']=True
        transport=Transport(Response(chunks=[PCM,PCM]))
        provider.client=breeze.BreezeClient(transport=transport)
        with patch.object(module,'PcmOpusStream',Codec):
            provider.to_tts_stream('旧的回应。')
        self.assertTrue(state['closed'] and transport.closed)
        self.assertFalse(state['finished'])
        self.assertTrue(all(item[3]=='current' for item in provider.tts_audio_queue.queue))
        self.assertEqual(len(transport.calls),1)

    def test_closed_provider_does_not_send_more_speech(self):
        provider=load_provider().TTSProvider({'stream_pcm':False},True)
        asyncio.run(provider.close())
        async def forbidden(*args,**kwargs):
            raise AssertionError('Closed providers must not send HTTP.')
        provider.client.synthesize=forbidden
        provider.to_tts_stream('我在。')
        self.assertTrue(provider.tts_audio_queue.empty())


class NativeStreamingCodecTests(unittest.TestCase):
    def setUp(self):
        import importlib.util
        if any(importlib.util.find_spec(name) is None for name in ('numpy','soxr','opuslib_next')):
            self.skipTest('Native audio dependencies are installed in the voice runtime.')
        self.module=load_provider()

    def test_continuous_resampling_real_opus_packets_and_final_partial_frame(self):
        import math
        import numpy as np
        from opuslib_next import Decoder
        count=24312
        pcm=(np.sin(np.arange(count)*2*np.pi*440/24000)*12000).astype('<i2').tobytes()
        packets=[]
        codec=self.module.PcmOpusStream(16000,packets.append,lambda:False)
        try:
            for offset in range(0,len(pcm),1024):
                codec.feed(pcm[offset:offset+1024])
            self.assertTrue(packets,'At least one packet must precede EOF.')
            codec.finish()
            self.assertEqual(len(packets),math.ceil(round(count*16000/24000)/960))
            decoder=Decoder(16000,1)
            decoded=b''.join(decoder.decode(packet,960) for packet in packets)
            self.assertEqual(len(decoded),len(packets)*960*2)
            samples=np.frombuffer(decoded,dtype='<i2').astype(float)
            spectrum=np.abs(np.fft.rfft(samples))
            frequency=int(np.argmax(spectrum))*16000/len(samples)
            self.assertAlmostEqual(frequency,440,delta=3)
            self.assertTrue(all(0<len(packet)<=2048 for packet in packets))
        finally:
            codec.close()
        self.assertIsNone(codec.encoder)
        self.assertEqual(codec.pending,bytearray())

    def test_cancelled_codec_never_flushes_pending_samples(self):
        packets=[];cancelled=threading.Event()
        codec=self.module.PcmOpusStream(16000,packets.append,cancelled.is_set)
        codec.feed(b'\0\1'*10)
        cancelled.set()
        with self.assertRaises(breeze.BreezeCancelled):
            codec.finish()
        codec.close()
        self.assertEqual(packets,[])
        self.assertEqual(codec.pending,bytearray())
        self.assertIsNone(codec.encoder)


if __name__=='__main__':
    unittest.main()
