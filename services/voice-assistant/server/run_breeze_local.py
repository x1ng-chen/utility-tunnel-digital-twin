"""Foreground, loopback-only Breeze lifecycle. --check-only never starts a process."""
import argparse
from datetime import datetime,timezone
import json
import socket
import subprocess
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import HTTPRedirectHandler,ProxyHandler,Request,build_opener
from preflight import BREEZE_URL,preferred_assets,read_json


def port_free(port=7861):
    try:
        with socket.socket(socket.AF_INET,socket.SOCK_STREAM) as probe:
            probe.setsockopt(socket.SOL_SOCKET,socket.SO_EXCLUSIVEADDRUSE,1)
            probe.bind(('127.0.0.1',port))
        return True
    except OSError:
        return False


def cli_running():
    import psutil
    for process in psutil.process_iter(['name']):
        try:
            if (process.info.get('name') or '').lower()=='breeze-cli.exe':
                return True
        except (psutil.NoSuchProcess,psutil.AccessDenied):
            continue
    return False


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):
        raise RuntimeError('A loopback service must not redirect.')


def stop_owned(process):
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=10)


def launch(paths,breeze_root,voice_id,cpu=False):
    # This function is reached only after an explicit invocation without CheckOnly.
    if not port_free() or cli_running():
        raise RuntimeError('Port 7861 is occupied or Breeze CLI is active.')
    directory=Path(breeze_root)/'service-logs'
    directory.mkdir(parents=True,exist_ok=True)
    stamp=datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')
    args=[str(paths['executable']),str(paths['model']),'--host','127.0.0.1','--port','7861',
          '--ws-port','-1','--voices-dir',str(paths['voices'])]
    if cpu:
        args.append('--cpu')
    process=None
    log_path=directory/(stamp+'.log')
    opener=build_opener(ProxyHandler({}),NoRedirect())
    def get(path):
        with opener.open(Request(BREEZE_URL+path,headers={'Accept':'application/json'}),timeout=2) as response:
            raw=response.read(65537)
            if response.status!=200 or len(raw)>65536:
                raise RuntimeError('Invalid loopback readiness response.')
            return json.loads(raw)
    try:
        with log_path.open('wb') as log:
            process=subprocess.Popen(args,cwd=paths['executable'].parent,stdin=subprocess.DEVNULL,
                stdout=log,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW)
            print(json.dumps({'state':'starting','owned_pid':process.pid,'url':BREEZE_URL,'voice_id':voice_id,'log':str(log_path)}),flush=True)
            deadline=time.monotonic()+120
            while True:
                if process.poll() is not None:
                    raise RuntimeError('Breeze exited before readiness; inspect the local log.')
                try:
                    health=get('/health')
                    break
                except (URLError,OSError,TimeoutError):
                    if time.monotonic()>=deadline:
                        raise TimeoutError('Breeze readiness timed out.')
                    time.sleep(0.25)
            if health.get('status')!='ok' or health.get('sample_rate')!=24000 or health.get('ws_port')!=0:
                raise RuntimeError('Expected a 24kHz HTTP-only loopback service.')
            voice=get('/v1/voices/'+voice_id)
            if voice.get('id')!=voice_id or voice.get('saved') is not True:
                raise RuntimeError('Preferred saved voice is not loaded.')
            print(json.dumps({'state':'ready','url':BREEZE_URL,'voice_id':voice_id,'websocket_enabled':False,'stop':'Ctrl+C'}),flush=True)
            while process.poll() is None:
                time.sleep(0.25)
            if process.returncode:
                raise RuntimeError('Breeze stopped unexpectedly; inspect the local log.')
    finally:
        if process is not None:
            stop_owned(process)
            print(json.dumps({'state':'stopped','owned_pid':process.pid,'owned_process_stopped':process.poll() is not None}),flush=True)


def main(argv=None):
    parser=argparse.ArgumentParser()
    parser.add_argument('--breeze-root',default=r'D:\ut-voice\breeze-tts2')
    parser.add_argument('--preferred-manifest',default=str(Path(__file__).with_name('preferred-voice.json')))
    parser.add_argument('--check-only',action='store_true')
    parser.add_argument('--verify-model-hash',action='store_true')
    parser.add_argument('--cpu',action='store_true')
    args=parser.parse_args(argv)
    try:
        preferred=read_json(args.preferred_manifest)
        checks,paths=preferred_assets(preferred,Path(args.breeze_root),args.verify_model_hash)
        checks['http_port_available']=port_free()
        checks['no_parallel_breeze_cli']=not cli_running()
        ready=bool(checks) and all(checks.values())
        print(json.dumps({'checks':checks,'ready_to_start_breeze':ready,
            'voice_id':preferred.get('voice_id'),'model_full_hash_checked':args.verify_model_hash,
            'server_started':False},ensure_ascii=True),flush=True)
        if not ready:
            return 2
        if args.check_only:
            return 0
        launch(paths,Path(args.breeze_root),preferred['voice_id'],args.cpu)
        return 0
    except KeyboardInterrupt:
        return 0
    except Exception as exc:
        print(json.dumps({'ready_to_start_breeze':False,'error_type':type(exc).__name__,
                          'credentials_printed':False}),flush=True)
        return 2


if __name__=='__main__':
    raise SystemExit(main())
