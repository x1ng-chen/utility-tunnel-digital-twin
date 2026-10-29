"""Static local voice prerequisites. Never starts a server or calls an API."""
import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import re
import sys
import wave

VOICE_ID='guanlang_playful_girl'
BREEZE_URL='http://127.0.0.1:7861'
SAPI_FILES=('windows_sapi.py','sapi_client.py','sapi_worker.ps1')
BREEZE_FILES=('breeze_local.py','breeze_client.py')


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream,'sha256').hexdigest()


def inside(root,relative):
    relative=Path(relative)
    if relative.is_absolute():
        raise ValueError('An asset must remain inside the Breeze directory.')
    target=(Path(root)/relative).resolve()
    target.relative_to(Path(root).resolve())
    return target


def preferred_assets(preferred,breeze_root,verify_model_hash=False):
    checks={}
    paths={}
    try:
        voice_id=preferred['voice_id']
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,64}',voice_id):
            raise ValueError('Invalid saved voice id.')
        checks['preferred_voice_id']=voice_id==VOICE_ID
        checks['preferred_loopback_endpoint']=preferred.get('base_url')==BREEZE_URL
        runtime=preferred['runtime']
        model=preferred['model']
        paths['executable']=inside(breeze_root,runtime['server_relative_path'])
        paths['model']=inside(breeze_root,model['relative_path'])
        paths['voices']=Path(breeze_root).resolve()/'voices'
        voice_file=paths['voices']/(voice_id+'.breeze')
        checks['breeze_executable_hash']=paths['executable'].is_file() and digest(paths['executable'])==runtime['server_sha256']
        checks['breeze_model_present']=paths['model'].is_file() and paths['model'].stat().st_size==model['bytes']
        if verify_model_hash:
            checks['breeze_model_hash']=checks['breeze_model_present'] and digest(paths['model'])==model['sha256']
        checks['preferred_saved_voice_hash']=voice_file.is_file() and digest(voice_file)==preferred['saved_voice']['sha256']
        for label in ('reference_sample','ack_sample'):
            asset=preferred[label]
            sample=inside(breeze_root,asset['relative_path'])
            valid=sample.is_file() and digest(sample)==asset['sha256']
            if valid:
                with wave.open(str(sample),'rb') as audio:
                    valid=(audio.getframerate(),audio.getnchannels(),audio.getsampwidth())==(24000,1,2) and audio.getnframes()>0
            checks[label+'_verified']=valid
    except (OSError,ValueError,KeyError,TypeError,wave.Error):
        checks['preferred_asset_manifest_valid']=False
    return checks,paths


def inspect_configuration(config,server,scripts,manifest,preferred,breeze_root):
    bind=config.get('server',{})
    auth=bind.get('auth',{})
    selected=config.get('selected_module',{})
    expected={'VAD':'SileroVAD','ASR':'SherpaParaformerASR','LLM':'UtilityTunnel','Memory':'nomem','Intent':'nointent'}
    chosen=selected.get('TTS')
    checks={
        'loopback_only':bind.get('ip')=='127.0.0.1',
        'dedicated_ports':bind.get('port')==8941 and bind.get('http_port')==8942,
        'websocket_loopback':bind.get('websocket')=='ws://127.0.0.1:8941/xiaozhi/v1/',
        'authentication_enabled':auth.get('enabled') is True,
        'no_auth_bypass_devices':auth.get('allowed_devices')==[],
        'private_auth_key_present':isinstance(bind.get('auth_key'),str) and len(bind['auth_key'])>=32,
        'no_manager_api':not config.get('manager-api',{}).get('url'),
        'no_external_mcp':config.get('mcp_endpoint') is None,
        'no_context_sources':config.get('context_providers')==[],
        'no_voiceprint':not config.get('voiceprint'),
        'no_vision_model':selected.get('VLLM') is None,
        'selected_local_providers':all(selected.get(key)==value for key,value in expected.items()),
        'supported_local_tts':chosen in {'WindowsSAPI','BreezeLocal'},
        'no_greeting_or_cache':config.get('enable_greeting') is False and config.get('enable_wakeup_words_response_cache') is False,
        'wake_word':config.get('wakeup_words')==['你好小管','小管'],
        'ffmpeg_available':(scripts/'ffmpeg.exe').is_file(),
        'opus_available':(scripts/'opus.dll').is_file(),
        'asr_model_present':all((server/'models/sherpa-onnx-paraformer-zh-small-2024-03-09'/name).is_file() for name in ('model.int8.onnx','tokens.txt')),
        'vad_model_present':(server/'models/snakers4_silero-vad/src/silero_vad/data/silero_vad.onnx').is_file(),
    }
    template=server/config.get('prompt_template','')
    checks['prompt_has_no_remote_enhancement']=template.is_file() and template.read_text(encoding='utf-8').strip()=='{{ base_prompt }}'
    deployed=manifest.get('deployed_adapters',{})
    required={f'core/providers/tts/{name}' for name in (BREEZE_FILES if chosen=='BreezeLocal' else SAPI_FILES)}
    checks['deployment_manifest_nonempty']=isinstance(deployed,dict) and bool(deployed) and required.issubset(deployed)
    checks['deployed_adapter_hashes_match']=checks['deployment_manifest_nonempty'] and all(
        (server/path).is_file() and digest(server/path)==expected_hash for path,expected_hash in deployed.items())
    tts=config.get('TTS',{}).get(chosen,{})
    if chosen=='WindowsSAPI':
        checks['sapi_provider_type']=tts.get('type')=='windows_sapi'
        checks['sapi_voice_configured']=isinstance(tts.get('voice'),str) and bool(tts['voice'].strip())
    elif chosen=='BreezeLocal':
        sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
        from xiaozhi_adapter.breeze_client import BreezeConfig
        try:
            BreezeConfig(base_url=tts.get('base_url',''),voice_id=tts.get('voice_id',''),
                timeout_seconds=tts.get('tts_timeout',config.get('tts_timeout',15)),
                max_frames=tts.get('max_frames',750),max_text_chars=tts.get('max_text_chars',2000),
                max_audio_bytes=tts.get('max_audio_bytes',8388608))
            checks['breeze_configuration_valid']=True
        except ValueError:
            checks['breeze_configuration_valid']=False
        try:
            checks['breeze_streaming_resampler_installed']=importlib.metadata.version('soxr')=='1.1.0'
        except importlib.metadata.PackageNotFoundError:
            checks['breeze_streaming_resampler_installed']=False
        checks['breeze_native_pcm_streaming']=tts.get('stream_pcm',True) is True
        checks['breeze_provider_type']=tts.get('type')=='breeze_local'
        checks['breeze_preferred_selection']=tts.get('base_url')==BREEZE_URL and tts.get('voice_id')==preferred.get('voice_id')==VOICE_ID
        asset_checks,_=preferred_assets(preferred,breeze_root)
        checks.update(asset_checks)
    return checks,chosen


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--server-root',default=r'D:\ut-voice\server')
    parser.add_argument('--venv-root',default=r'D:\ut-voice\voice-server-venv')
    parser.add_argument('--breeze-root',default=r'D:\ut-voice\breeze-tts2')
    parser.add_argument('--require-agent-token','--require-agent-auth',dest='require_agent_token',action='store_true')
    args=parser.parse_args()
    try:
        server=Path(args.server_root)
        text=(server/'data/.config.yaml').read_text(encoding='utf-8')
        try:
            config=json.loads(text)
        except json.JSONDecodeError:
            import yaml
            config=yaml.safe_load(text)
        directory=Path(__file__).parent
        manifest=read_json(directory/'sources.lock.json')
        preferred=read_json(directory/'preferred-voice.json') if (directory/'preferred-voice.json').is_file() else {}
        checks,chosen=inspect_configuration(config,server,Path(args.venv_root)/'Scripts',manifest,preferred,Path(args.breeze_root))
        ready=all(checks.values())
        token_ready=bool(re.fullmatch(r'[a-fA-F0-9]{40}',os.environ.get('UT_VOICE_API_TOKEN','')))
        credentials_path=os.environ.get('UT_VOICE_VIEWER_CREDENTIALS_FILE','').strip()
        credentials_ready=False
        if credentials_path:
            from viewer_session import load_credentials,ViewerSessionError
            try:
                load_credentials(credentials_path)
                credentials_ready=True
            except ViewerSessionError:
                credentials_ready=False
        authentication_ready=credentials_ready if credentials_path else token_ready
        print(json.dumps({'checks':checks,'selected_tts':chosen,'preferred_voice_id':preferred.get('voice_id'),
            'local_components_ready':ready,'agent_token_configured':token_ready,
            'agent_credentials_file_configured':credentials_ready,'agent_authentication_mode':'renewing_viewer' if credentials_path else 'fixed_token',
            'agent_startup_prerequisites_present':ready and authentication_ready,'agent_identity_verified':False,
            'tts_runtime_verified':False,'device_admission_verified':False,'service_started':False},ensure_ascii=True))
        return 0 if ready and (authentication_ready or not args.require_agent_token) else 2
    except Exception as exc:
        print(json.dumps({'local_components_ready':False,'error_type':type(exc).__name__,'credentials_printed':False,'service_started':False}))
        return 2


if __name__=='__main__':
    raise SystemExit(main())
