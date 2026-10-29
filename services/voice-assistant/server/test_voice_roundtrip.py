"""Opt-in, bounded synthetic-audio test of the restricted local xiaozhi route.

Default invocation is a local fixture check only. --run is required for any
OTA/WS/ASR/LLM/TTS request. This script never starts or stops a service.
"""
import argparse,array,asyncio,difflib,hashlib,json,math,os,re,sys,time,uuid,wave
from dataclasses import dataclass,field
from datetime import datetime,timezone
from pathlib import Path
from urllib.parse import urlsplit

PRIVATE_ROOT=Path(r'D:\ut-voice\private')
DEFAULT_DEVICE_FILE=PRIVATE_ROOT/'voice-device.json'
FIXTURE_ROOT=Path(r'D:\ut-voice\tts-test')
DEFAULT_INPUT=FIXTURE_ROOT/'windows-sapi-test.wav'
OUTPUT_ROOT=Path(r'D:\ut-voice\integration-output')
OTA_URL='http://127.0.0.1:8942/xiaozhi/ota/'
WS_URL='ws://127.0.0.1:8941/xiaozhi/v1/'
EXPECTED_TEXT='你好这是管廊本地语音测试'
FRAME_MS=60
INPUT_RATE=16000
FRAME_SAMPLES=960
FRAME_BYTES=1920
MAX_PACKET_BYTES=2048
MAX_REPLY_PACKETS=1000
MAX_JSON_BYTES=65536


class RoundtripError(Exception):
    def __init__(self,code):
        super().__init__(code)
        self.code=code


def bounded_path(path,root,suffix=None):
    try:
        root=Path(root).resolve()
        result=Path(path).resolve()
        result.relative_to(root)
        if result==root or (suffix and result.suffix.lower()!=suffix):
            raise ValueError
        return result
    except (ValueError,OSError):
        raise RoundtripError('path_outside_expected_directory') from None


def fixture_pcm(path=DEFAULT_INPUT):
    path=bounded_path(path,FIXTURE_ROOT,'.wav')
    try:
        if path.stat().st_size>1024*1024:
            raise RoundtripError('input_fixture_too_large')
        with wave.open(str(path),'rb') as audio:
            if (audio.getframerate(),audio.getnchannels(),audio.getsampwidth(),audio.getcomptype())!=(16000,1,2,'NONE'):
                raise RoundtripError('input_must_be_16k_mono_pcm16')
            count=audio.getnframes()
            if not 1600<=count<=16000*15:
                raise RoundtripError('input_duration_outside_test_limit')
            pcm=audio.readframes(count)
            if len(pcm)!=count*2:
                raise RoundtripError('input_wav_truncated')
    except (OSError,wave.Error,EOFError):
        raise RoundtripError('input_fixture_unavailable') from None
    return pcm,{'file':path.name,'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
                'sample_rate':16000,'channels':1,'sample_width_bytes':2,
                'duration_seconds':round(count/16000,4)}


def pcm_frames(pcm):
    if not isinstance(pcm,bytes) or not pcm or len(pcm)%2:
        raise RoundtripError('invalid_input_pcm')
    return [pcm[offset:offset+FRAME_BYTES].ljust(FRAME_BYTES,b'\0')
            for offset in range(0,len(pcm),FRAME_BYTES)]


def hello_message():
    return {'type':'hello','version':1,'transport':'websocket',
            'features':{'mcp':False,'aec':False},
            'audio_params':{'format':'opus','sample_rate':16000,'channels':1,'frame_duration':60}}


def validate_hello(message):
    if not isinstance(message,dict) or message.get('type')!='hello':
        raise RoundtripError('server_hello_missing')
    audio=message.get('audio_params')
    if (not isinstance(audio,dict) or audio.get('format')!='opus'
            or audio.get('sample_rate')!=16000 or audio.get('channels')!=1
            or audio.get('frame_duration')!=60):
        raise RoundtripError('server_audio_contract_mismatch')
    session_id=message.get('session_id')
    if not isinstance(session_id,str) or not 1<=len(session_id)<=128:
        raise RoundtripError('server_session_missing')
    return session_id


def parse_json_message(message):
    if not isinstance(message,str) or len(message.encode('utf-8'))>MAX_JSON_BYTES:
        raise RoundtripError('server_json_too_large_or_wrong_type')
    try:
        data=json.loads(message)
        if not isinstance(data,dict):raise ValueError
        return data
    except (ValueError,TypeError):
        raise RoundtripError('server_json_invalid') from None


def normalized(value):
    return ''.join(c.lower() for c in value if c.isalnum())


class Capture:
    def __init__(self,session_id,decode):
        self._session_id=session_id
        self._decode=decode
        self.pcm=bytearray()
        self.packet_count=0
        self.json_count=0
        self.stt=[]
        self.llm_signals=[]
        self.sentences=[]
        self.tts_states=[]
        self.started=False
        self.stopped=False
        self.unknown_messages=0

    def feed(self,message):
        if self.stopped:raise RoundtripError('message_after_tts_stop')
        if isinstance(message,bytes):
            if not self.started or not 1<=len(message)<=MAX_PACKET_BYTES:
                raise RoundtripError('unexpected_audio_packet')
            if self.packet_count>=MAX_REPLY_PACKETS:
                raise RoundtripError('reply_audio_limit_exceeded')
            try:pcm=bytes(self._decode(message))
            except Exception:raise RoundtripError('reply_opus_decode_failed') from None
            if len(pcm)!=FRAME_BYTES:
                raise RoundtripError('reply_frame_duration_mismatch')
            self.pcm.extend(pcm)
            self.packet_count+=1
            return
        data=parse_json_message(message)
        self.json_count+=1
        if self.json_count>1000:raise RoundtripError('too_many_control_messages')
        kind=data.get('type')
        if kind in {'stt','llm','tts'} and data.get('session_id')!=self._session_id:
            raise RoundtripError('server_session_changed')
        if kind=='stt':
            text=data.get('text')
            if not isinstance(text,str) or not 1<=len(text.strip())<=2000:
                raise RoundtripError('stt_text_invalid')
            self.stt.append(text.strip())
            if len(self.stt)>1:raise RoundtripError('multiple_stt_turns_received')
        elif kind=='llm':
            text=data.get('text','')
            emotion=data.get('emotion','')
            if not isinstance(text,str) or len(text)>200 or not isinstance(emotion,str) or len(emotion)>40:
                raise RoundtripError('llm_signal_invalid')
            self.llm_signals.append({'text':text,'emotion':emotion})
            if len(self.llm_signals)>20:raise RoundtripError('too_many_llm_signals')
        elif kind=='tts':
            state=data.get('state')
            if state not in {'start','sentence_start','sentence_end','stop'}:
                raise RoundtripError('tts_state_invalid')
            self.tts_states.append(state)
            if state=='start':
                if self.started:raise RoundtripError('duplicate_tts_start')
                self.started=True
            elif not self.started:
                raise RoundtripError('tts_not_started')
            if state=='sentence_start':
                text=data.get('text')
                if not isinstance(text,str) or not text.strip() or len(text)>2000:
                    raise RoundtripError('reply_text_invalid')
                self.sentences.append(text)
                if sum(map(len,self.sentences))>8192:
                    raise RoundtripError('reply_text_limit_exceeded')
            elif state=='stop':
                self.stopped=True
        elif kind in {'mcp','iot','server','error','alert'}:
            raise RoundtripError('unexpected_capability_or_error_message')
        else:
            self.unknown_messages+=1
            if self.unknown_messages>20:raise RoundtripError('too_many_unknown_messages')

    def summary(self,expected_text=EXPECTED_TEXT):
        stt=''.join(self.stt)
        reply=''.join(self.sentences)
        match=difflib.SequenceMatcher(a=normalized(expected_text),b=normalized(stt)).ratio()
        samples=array.array('h',self.pcm)
        if sys.byteorder!='little':samples.byteswap()
        peak=max((abs(x) for x in samples),default=0)/32768
        rms=math.sqrt(sum(x*x for x in samples)/len(samples))/32768 if samples else 0
        fallback=any(text in reply for text in ['语音查询会话暂不可用','语音查询凭据已失效',
            '语音查询需要独立的查看者账号','管廊智能体尚未就绪','暂时连接不上管廊服务',
            '语音查询次数已达限制','管廊查询失败','管廊返回内容无效','管廊回答格式无效','需要处置工单时，请到管廊网页'])
        success=(self.stopped and self.started and bool(self.stt) and match>=0.85
                 and bool(self.llm_signals) and bool(reply.strip()) and self.packet_count>0
                 and rms>0.001 and not fallback)
        return {'stt_text':stt,'expected_stt_text':expected_text,
                'asr_similarity':round(match,4),'reply_text':reply,
                'llm_signals':self.llm_signals,'llm_signal_semantics':'upstream emotion signal; spoken reply is tts sentence text',
                'tts_states':self.tts_states,'reply_opus_packets':self.packet_count,
                'reply_duration_seconds':round(len(self.pcm)/(16000*2),4),
                'reply_peak':round(peak,6),'reply_rms':round(rms,6),
                'tts_stop_received':self.stopped,'fallback_error_reply_detected':fallback,
                'roundtrip_passed':bool(success)}


class NativeOpus:
    def __init__(self):
        self.encoder=None
        self.decoder=None
        self._dll_directory=None
        try:
            scripts=Path(sys.executable).parent
            os.environ['PATH']=str(scripts)+os.pathsep+os.environ.get('PATH','')
            if hasattr(os,'add_dll_directory'):
                self._dll_directory=os.add_dll_directory(str(scripts))
            import opuslib_next
            self.opus=opuslib_next
            self.encoder=opuslib_next.Encoder(16000,1,opuslib_next.APPLICATION_AUDIO)
            self.encoder.bitrate=24000
            self.encoder.signal=opuslib_next.SIGNAL_VOICE
            self.decoder=opuslib_next.Decoder(16000,1)
        except Exception:
            self.close()
            raise RoundtripError('native_opus_unavailable') from None

    def encode(self,pcm):
        result=bytes(self.encoder.encode(pcm,FRAME_SAMPLES))
        if not 1<=len(result)<=MAX_PACKET_BYTES:
            raise RoundtripError('input_opus_packet_invalid')
        return result

    def decode(self,packet):
        return bytes(self.decoder.decode(packet,FRAME_SAMPLES))

    def close(self):
        ok=True
        for codec,attribute,api in [
                (self.encoder,'encoder_state','encoder'),
                (self.decoder,'decoder_state','decoder')]:
            if codec is not None and hasattr(codec,attribute):
                try:getattr(self.opus.api,api).destroy(getattr(codec,attribute))
                except Exception:ok=False
                finally:delattr(codec,attribute)
        self.encoder=None;self.decoder=None
        if self._dll_directory is not None:
            try:self._dll_directory.close()
            except Exception:ok=False
            finally:self._dll_directory=None
        return ok


async def send_manual_turn(ws,packets):
    # Hello acknowledgement precedes the upstream's asynchronous per-connection setup.
    await asyncio.sleep(1.0)
    await ws.send(json.dumps({'type':'listen','state':'start','mode':'manual'}))
    loop=asyncio.get_running_loop()
    due=loop.time()
    for packet in packets:
        await ws.send(packet)
        due+=0.060
        await asyncio.sleep(max(0,due-loop.time()))
    # Give the independently consumed ASR queue a small trailing drain period.
    await asyncio.sleep(.300)
    await ws.send(json.dumps({'type':'listen','state':'stop','mode':'manual'}))


def write_wave(path,pcm):
    with wave.open(str(path),'wb') as target:
        target.setnchannels(1);target.setsampwidth(2);target.setframerate(16000)
        target.writeframes(pcm)
    with wave.open(str(path),'rb') as source:
        if (source.getnchannels(),source.getsampwidth(),source.getframerate())!=(1,2,16000):
            raise RoundtripError('output_wav_contract_failed')
        if source.readframes(source.getnframes())!=pcm:
            raise RoundtripError('output_wav_content_mismatch')
    return {'file':path.name,'bytes':path.stat().st_size,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}

@dataclass(frozen=True,repr=False)
class DeviceCredentials:
    device_id:str
    client_id:str
    token:str

    def headers(self,websocket=False):
        headers={'Device-Id':self.device_id,'Client-Id':self.client_id,
                 'Authorization':'Bearer '+self.token}
        if websocket:headers['Protocol-Version']='1'
        return headers


def load_device_credentials(path=DEFAULT_DEVICE_FILE,private_root=PRIVATE_ROOT):
    path=bounded_path(path,private_root,'.json')
    try:
        if path.stat().st_size>16384:raise ValueError
        value=json.loads(path.read_text(encoding='utf-8'))
        if set(value)!={'schema','devices'} or value['schema']!='ut.voice.devices.v1':
            raise ValueError
        devices=value['devices']
        if not isinstance(devices,list) or len(devices)!=1:
            raise ValueError
        device=devices[0]
        if not isinstance(device,dict) or set(device)!={'device_id','client_id','token'}:
            raise ValueError
        device_id=device['device_id'];client_id=device['client_id'];token=device['token']
        if (not isinstance(device_id,str) or not re.fullmatch(r'(?:[a-fA-F0-9]{2}:){5}[a-fA-F0-9]{2}',device_id)
                or not isinstance(client_id,str) or str(uuid.UUID(client_id))!=client_id.lower()
                or not isinstance(token,str) or not re.fullmatch(r'[a-fA-F0-9]{64}',token)):
            raise ValueError
        return DeviceCredentials(device_id.lower(),client_id.lower(),token)
    except (OSError,ValueError,KeyError,TypeError,AttributeError):
        raise RoundtripError('private_device_configuration_invalid') from None


def validate_ota(data,credentials):
    if not isinstance(data,dict):raise RoundtripError('ota_json_invalid')
    websocket=data.get('websocket')
    firmware=data.get('firmware')
    if (not isinstance(websocket,dict) or websocket.get('url')!=WS_URL
            or websocket.get('token')!=credentials.token
            or type(websocket.get('version')) is not int or websocket.get('version')!=1):
        raise RoundtripError('ota_websocket_contract_rejected')
    if not isinstance(firmware,dict) or firmware.get('url')!='':
        raise RoundtripError('unexpected_firmware_update_offer')
    return WS_URL


async def fetch_ota(credentials):
    import aiohttp
    timeout=aiohttp.ClientTimeout(total=10,connect=5)
    async with aiohttp.ClientSession(timeout=timeout,trust_env=False) as client:
        async with client.post(OTA_URL,headers=credentials.headers(),
                json={'application':{'version':'0.0.0'},'board':{'type':'utility-tunnel-s3'}},
                allow_redirects=False) as response:
            if response.status!=200:
                raise RoundtripError('restricted_ota_rejected')
            raw=await response.content.read(MAX_JSON_BYTES+1)
            if len(raw)>MAX_JSON_BYTES:
                raise RoundtripError('ota_response_too_large')
            try:data=json.loads(raw)
            except (ValueError,TypeError,UnicodeError):
                raise RoundtripError('ota_json_invalid') from None
    return validate_ota(data,credentials)


async def run_roundtrip(report,pcm,credentials,run_directory,timeout):
    from websockets.asyncio.client import connect
    codecs=None
    capture=None
    sender=None
    owned_ws=None
    began=time.monotonic()
    report['phase']='initialize_codec'
    try:
        async with asyncio.timeout(timeout):
            codecs=NativeOpus()
            encoded=[codecs.encode(frame) for frame in pcm_frames(pcm)]
            # Explicit trailing silence aids queue drainage; no synthetic question/text shortcut.
            encoded.extend(codecs.encode(b'\0'*FRAME_BYTES) for _ in range(5))
            report['input_opus_packets']=len(encoded)
            report['input_trailing_silence_ms']=300
            report['phase']='restricted_ota'
            url=await fetch_ota(credentials)
            report['restricted_ota_accepted']=True
            report['ota_ws_version']=1
            report['firmware_update_offered']=False
            report['phase']='websocket_hello'
            async with connect(url,additional_headers=credentials.headers(websocket=True),
                    open_timeout=10,close_timeout=3,ping_interval=20,ping_timeout=10,
                    max_size=MAX_JSON_BYTES,max_queue=32,compression=None) as ws:
                owned_ws=ws
                await ws.send(json.dumps(hello_message()))
                ack=await asyncio.wait_for(ws.recv(),timeout=10)
                session_id=validate_hello(parse_json_message(ack))
                report['hello_verified']=True
                report['negotiated_audio']={'format':'opus','sample_rate':16000,'channels':1,'frame_duration':60}
                capture=Capture(session_id,codecs.decode)
                report['phase']='manual_audio_turn'
                sender=asyncio.create_task(send_manual_turn(ws,encoded))
                try:
                    while not capture.stopped:
                        capture.feed(await ws.recv())
                    await sender
                    report['phase']='tts_stopped'
                finally:
                    if sender is not None and not sender.done():
                        sender.cancel()
                    if sender is not None:
                        await asyncio.gather(sender,return_exceptions=True)
            report['owned_websocket_closed']=True
    finally:
        try:
            if owned_ws is not None:
                try:
                    await owned_ws.close()
                    report['owned_websocket_closed']=True
                except Exception:
                    report['owned_websocket_closed']=False
            if capture is not None:
                report.update(capture.summary())
                if capture.pcm:
                    filename='reply.wav' if capture.stopped else 'reply.partial.wav'
                    report['audio_artifact']=write_wave(run_directory/filename,bytes(capture.pcm))
                    report['output_wav_verified']=True
                    report['all_received_opus_frames_decoded']=True
        finally:
            if codecs is not None:
                report['owned_native_codecs_released']=codecs.close()
                if not report['owned_native_codecs_released']:
                    report.update(roundtrip_passed=False,error_code='codec_cleanup_failed')
            report['elapsed_seconds']=round(time.monotonic()-began,3)


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run',action='store_true',help='Explicitly perform one authenticated OTA/WS synthetic-audio turn.')
    parser.add_argument('--device-file',default=str(DEFAULT_DEVICE_FILE))
    parser.add_argument('--input',default=str(DEFAULT_INPUT))
    parser.add_argument('--output-root',default=str(OUTPUT_ROOT))
    parser.add_argument('--timeout',type=int,default=120)
    args=parser.parse_args(argv)
    report={'date':datetime.now().astimezone().date().isoformat(),'scope':'synthetic_audio_restricted_ws_asr_llm_tts_roundtrip',
            'credentials_printed_or_recorded':False,'physical_esp32_tested':False,
            'physical_microphone_tested':False,'server_started_or_stopped':False,
            'network_requests_started':False,'roundtrip_passed':False}
    run_directory=None
    try:
        if not 30<=args.timeout<=180:
            raise RoundtripError('timeout_outside_test_limit')
        pcm,fixture=fixture_pcm(args.input)
        report['input_fixture']=fixture
        if not args.run:
            report.update(check_only=True,fixture_check_passed=True,
                          private_device_file_present=Path(args.device_file).is_file(),
                          required_explicit_execution_flag='--run',
                          planned_hello=hello_message())
            print(json.dumps(report,ensure_ascii=True))
            return 0
        credentials=load_device_credentials(args.device_file)
        output=Path(args.output_root).resolve()
        # The output root itself is allowed; child locations remain inside the fixed integration area.
        try:output.relative_to(OUTPUT_ROOT.resolve())
        except ValueError:raise RoundtripError('output_outside_integration_directory') from None
        output.mkdir(parents=True,exist_ok=True)
        stamp=datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')
        run_directory=output/('roundtrip-'+stamp+'-'+uuid.uuid4().hex[:8])
        run_directory.mkdir()
        report['network_requests_started']=True
        import logging
        logging.getLogger('websockets.client').setLevel(logging.CRITICAL)
        logging.getLogger('aiohttp.client').setLevel(logging.CRITICAL)
        asyncio.run(run_roundtrip(report,pcm,credentials,run_directory,args.timeout))
    except RoundtripError as exc:
        report.update(roundtrip_passed=False,error_code=exc.code)
    except (TimeoutError,asyncio.TimeoutError):
        report.update(roundtrip_passed=False,error_code='roundtrip_deadline_exceeded')
    except Exception as exc:
        # Never print request/response/headers, exception text, IDs, tokens or traceback.
        report.update(roundtrip_passed=False,error_type=type(exc).__name__)
    if run_directory is not None:
        destination=run_directory/'report.json'
        destination.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        report['report_path']=str(destination)
    print(json.dumps(report,ensure_ascii=True))
    return 0 if report.get('roundtrip_passed') else 2


if __name__=='__main__':
    raise SystemExit(main())
