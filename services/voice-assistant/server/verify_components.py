"""Offline component verification for the pinned Windows voice server.

Never starts app.main, opens microphone input, plays audio or calls the Agent.
"""
import argparse
import asyncio
from collections import deque
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timezone
import hashlib
import importlib
import io
import ipaddress
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
from types import SimpleNamespace
import wave


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_pcm(path):
    import numpy as np
    with wave.open(str(path), 'rb') as audio:
        if audio.getnchannels() != 1 or audio.getsampwidth() != 2:
            raise ValueError('Fixture must be mono 16-bit PCM.')
        return np.frombuffer(audio.readframes(audio.getnframes()), dtype='<i2').astype(np.float32) / 32768, audio.getframerate()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--server-root', default=r'D:\ut-voice\server')
    parser.add_argument('--venv-root', default=r'D:\ut-voice\voice-server-venv')
    parser.add_argument('--report', default=r'D:\ut-voice\voice-components-test.json')
    args = parser.parse_args()
    server = Path(args.server_root).resolve()
    scripts = Path(args.venv_root).resolve() / 'Scripts'
    os.environ['PATH'] = str(scripts) + os.pathsep + os.environ.get('PATH', '')
    os.environ.update({'HF_HUB_OFFLINE': '1', 'MODELSCOPE_OFFLINE': '1',
                       'TRANSFORMERS_OFFLINE': '1', 'PYTHONDONTWRITEBYTECODE': '1'})
    dll_context = os.add_dll_directory(str(scripts)) if hasattr(os, 'add_dll_directory') else None
    os.chdir(server)
    sys.path.insert(0, str(server))
    report = {'schema': 'ut.voice.components.v1', 'tested_at': datetime.now(timezone.utc).isoformat(),
              'python': sys.version.split()[0], 'server_commit': 'a377d89dcd58e6e18417a57e9357c0dd23657746',
              'server_started': False, 'external_network_calls_allowed': False, 'microphone_used': False,
              'computer_audio_played': False, 'agent_called': False, 'checks': {}}

    def check(name, function):
        started = time.monotonic()
        try:
            value = function()
            report['checks'][name] = {'ok': True, 'elapsed_seconds': round(time.monotonic()-started, 3),
                                     'details': value}
        except Exception as exc:
            # Do not export configuration values or exception text.
            entry = {'ok': False, 'error_type': type(exc).__name__,
                     'elapsed_seconds': round(time.monotonic()-started, 3)}
            if isinstance(exc, ModuleNotFoundError):
                entry['missing_module'] = exc.name
            report['checks'][name] = entry
        print(json.dumps({'check': name, **report['checks'][name]}, ensure_ascii=True))

    def pip_check():
        process = subprocess.run([sys.executable, '-m', 'pip', 'check'], capture_output=True, text=True, timeout=60)
        if process.returncode:
            raise RuntimeError('Package dependency check failed.')
        return {'exit_code': 0}

    check('pip_check', pip_check)

    def local_address(address):
        host = address[0] if isinstance(address, tuple) else address
        if host is None or host == 'localhost':
            return True
        try:
            return ipaddress.ip_address(host).is_loopback
        except ValueError:
            return False

    def guarded(original):
        def call(first, address, *values, **options):
            if not local_address(address):
                raise RuntimeError('External network is disabled for component verification.')
            return original(first, address, *values, **options)
        return call

    original_getaddrinfo = socket.getaddrinfo
    def local_getaddrinfo(host, *values, **options):
        if not local_address(host):
            raise RuntimeError('External DNS is disabled for component verification.')
        return original_getaddrinfo(host, *values, **options)

    original_create_connection = socket.create_connection
    def local_create_connection(address, *values, **options):
        if not local_address(address):
            raise RuntimeError('External network is disabled for component verification.')
        return original_create_connection(address, *values, **options)

    # Windows asyncio requires an internal loopback socket pair. No remote host
    # or DNS lookup is permitted; these probes never call the Django API.
    socket.socket.connect = guarded(socket.socket.connect)
    socket.socket.connect_ex = guarded(socket.socket.connect_ex)
    socket.create_connection = local_create_connection
    socket.getaddrinfo = local_getaddrinfo

    def ffmpeg():
        executable = scripts / 'ffmpeg.exe'
        result = subprocess.run([str(executable), '-version'], capture_output=True, timeout=15)
        if result.returncode:
            raise RuntimeError('FFmpeg failed.')
        return {'sha256': sha256(executable), 'version_line': result.stdout.decode('utf-8', 'replace').splitlines()[0]}

    check('ffmpeg', ffmpeg)

    def opus():
        import ctypes
        import numpy as np
        import opuslib_next
        library = ctypes.CDLL(str(scripts / 'opus.dll'))
        library.opus_get_version_string.restype = ctypes.c_char_p
        version = library.opus_get_version_string().decode('ascii')
        encoder = opuslib_next.Encoder(16000, 1, opuslib_next.APPLICATION_AUDIO)
        decoder = opuslib_next.Decoder(16000, 1)
        pcm = (np.sin(np.arange(960) * 2 * np.pi * 440 / 16000) * 6000).astype('<i2').tobytes()
        packet = encoder.encode(pcm, 960)
        decoded = decoder.decode(packet, 960)
        if len(decoded) != 1920 or not packet or not any(decoded):
            raise ValueError('Invalid Opus round trip.')
        return {'version': version, 'dll_sha256': sha256(scripts/'opus.dll'),
                'encoded_bytes': len(packet), 'decoded_samples': len(decoded)//2}

    check('opus_roundtrip', opus)

    model_dir = server / 'models/sherpa-onnx-paraformer-zh-small-2024-03-09'
    recognizer = None

    def asr_model():
        nonlocal recognizer
        import sherpa_onnx
        recognizer = sherpa_onnx.OfflineRecognizer.from_paraformer(
            paraformer=str(model_dir/'model.int8.onnx'), tokens=str(model_dir/'tokens.txt'),
            num_threads=2, sample_rate=16000, feature_dim=80, decoding_method='greedy_search', debug=False)
        return {'model_sha256': sha256(model_dir/'model.int8.onnx'),
                'tokens_sha256': sha256(model_dir/'tokens.txt')}

    check('asr_model_load', asr_model)

    def recognize(path):
        if recognizer is None:
            raise RuntimeError('ASR model not loaded.')
        samples, sample_rate = read_pcm(path)
        stream = recognizer.create_stream()
        stream.accept_waveform(sample_rate, samples)
        recognizer.decode_stream(stream)
        text = stream.result.text
        if not text.strip():
            raise ValueError('No transcription.')
        return {'fixture': Path(path).name, 'sha256': sha256(path), 'recognized_text': text,
                'sample_rate': sample_rate, 'duration_seconds': round(len(samples)/sample_rate,3)}

    fixtures = sorted((model_dir/'test_wavs').glob('*.wav'))
    check('asr_official_fixture', lambda: recognize(fixtures[0]))
    sapi_wav = Path(r'D:\ut-voice\tts-test\windows-sapi-test.wav')
    check('asr_sapi_fixture', lambda: recognize(sapi_wav))

    def vad():
        import numpy as np
        import onnxruntime
        model = server/'models/snakers4_silero-vad/src/silero_vad/data/silero_vad.onnx'
        options = onnxruntime.SessionOptions()
        options.inter_op_num_threads = 1
        options.intra_op_num_threads = 1
        session = onnxruntime.InferenceSession(str(model), providers=['CPUExecutionProvider'], sess_options=options)

        def probabilities(samples):
            state = np.zeros((2,1,128),dtype=np.float32)
            context = np.zeros((1,64),dtype=np.float32)
            output = []
            for start in range(0,len(samples)-511,512):
                chunk = np.asarray(samples[start:start+512],dtype=np.float32).reshape(1,-1)
                data = np.concatenate([context,chunk],axis=1).astype(np.float32)
                probability,state = session.run(None,{'input':data,'state':state,'sr':np.array(16000,dtype=np.int64)})
                output.append(float(probability.item()))
                context=data[:,-64:]
            return output

        silence = probabilities(np.zeros(16000,dtype=np.float32))
        speech,sample_rate=read_pcm(sapi_wav)
        if sample_rate != 16000:
            raise ValueError('Expected 16kHz speech.')
        voiced = probabilities(speech)
        if max(silence) >= 0.2 or max(voiced) < 0.5:
            raise ValueError('VAD classification did not separate test speech and silence.')
        return {'model_sha256':sha256(model),'providers':session.get_providers(),
                'silence_max_probability':round(max(silence),6),
                'speech_max_probability':round(max(voiced),6),
                'speech_frames_above_half':sum(probability>=0.5 for probability in voiced)}

    check('vad_model_and_samples', vad)

    def app_import():
        # No app.main(), server constructor or listener is called.
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            importlib.import_module('app')
        return {'imported':True,'main_called':False}

    check('app_import', app_import)

    def provider_imports():
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            tts = importlib.import_module('core.providers.tts.windows_sapi')
            importlib.import_module('core.providers.llm.utility_tunnel.utility_tunnel')
            asr = importlib.import_module('core.providers.asr.sherpa_onnx_local')
            vad_module = importlib.import_module('core.providers.vad.silero')
        return {'tts':tts.TTSProvider.__name__,'asr':asr.ASRProvider.__name__,
                'vad':vad_module.VADProvider.__name__,'agent_constructed':False}

    check('selected_provider_imports', provider_imports)

    def provider_contracts():
        from config.config_loader import load_config
        from core.utils.modules_initialize import initialize_asr, initialize_tts
        from core.providers.vad.silero import VADProvider
        config = asyncio.run(load_config())
        asr = initialize_asr(config)
        actual_text, _ = asyncio.run(asr.speech_to_text(
            [], 'offline-component-test', artifacts=SimpleNamespace(file_path=str(sapi_wav))))
        if not actual_text.strip():
            raise ValueError('The selected ASR provider returned no text.')
        tts = initialize_tts(config)
        data = asyncio.run(tts.text_to_speak('你好，这是管廊本地语音测试。', None))
        with wave.open(io.BytesIO(data), 'rb') as audio:
            if audio.getframerate() != 16000 or audio.getnchannels() != 1:
                raise ValueError('Selected TTS provider returned invalid format.')
            seconds = round(audio.getnframes()/audio.getframerate(),3)
        vad_instance = VADProvider(config['VAD']['SileroVAD'])
        connection = SimpleNamespace(client_listen_mode='auto',client_audio_buffer=bytearray(),
            last_is_voice=False,client_voice_window=deque(maxlen=5),client_have_voice=False,
            vad_last_voice_time=0,client_voice_stop=False)
        import numpy as np
        silent = [bool(vad_instance.is_vad(connection,b'\\x00'*1024)) for _ in range(10)]
        samples,_ = read_pcm(sapi_wav)
        pcm = (samples*32768).astype('<i2').tobytes()
        decisions = [bool(vad_instance.is_vad(connection,pcm[start:start+1024]))
                     for start in range(0,len(pcm)-1023,1024)]
        vad_instance.release_conn_resources(connection)
        asyncio.run(tts.close())
        if any(silent) or not any(decisions):
            raise ValueError('Selected VAD provider did not separate the samples.')
        return {'asr_text':actual_text,'tts_wav_bytes':len(data),'tts_seconds':seconds,
                'vad_silence_detected':any(silent),'vad_speech_detected':any(decisions),
                'agent_constructed':False}

    check('selected_provider_contracts', provider_contracts)
    report['all_component_checks_passed'] = all(check['ok'] for check in report['checks'].values())
    report['not_verified'] = ['live_microphone_ASR', 'ESP32_network_audio', 'device_admission',
        'Django_DeepSeek_agent_response', 'viewer_token_provisioning', 'end_to_end_conversation',
        'physical_speaker_TTS_playback', 'persistent_service_operation']
    destination = Path(args.report)
    destination.parent.mkdir(parents=True,exist_ok=True)
    destination.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    if dll_context is not None:
        dll_context.close()
    return 0 if report['all_component_checks_passed'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
