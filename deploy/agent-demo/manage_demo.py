"""Local-only launcher and offline backup. Never selects the business database."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import socket
import sqlite3
import subprocess
import sys
import time
import zipfile
from uuid import uuid4
from urllib.request import urlopen

ROOT=Path(__file__).resolve().parents[2]
STATE=ROOT/'.agent-demo'
BACKEND=ROOT/'backend'
PYTHON=STATE/'venv'/('Scripts/python.exe' if os.name=='nt' else 'bin/python')


def checked(command,**kw):
    subprocess.run([str(x) for x in command],check=True,**kw)


def environment():
    from dotenv import dotenv_values
    env=os.environ.copy()
    for key,value in dotenv_values(STATE/'.env').items():
        if key in {'DEEPSEEK_API_KEY','DEEPSEEK_MODEL','AGENT_EMBEDDING_MODEL_PATH','DJANGO_SECRET_KEY'} and value:
            env[key]=value
    secret=STATE/'secret.key'
    if not secret.exists(): secret.write_text(secrets.token_urlsafe(48),encoding='utf-8')
    env.update(DJANGO_ENV='development',DJANGO_SETTINGS_MODULE='config.agent_demo_settings',
        DJANGO_SECRET_KEY=secret.read_text(encoding='utf-8'),PYTHONUNBUFFERED='1',PYTHONIOENCODING='utf-8')
    return env


def setup(rag):
    STATE.mkdir(exist_ok=True)
    if not PYTHON.exists(): checked([sys.executable,'-m','venv',STATE/'venv'])
    checked([PYTHON,'-m','pip','install','--require-hashes','-r',BACKEND/'requirements.lock'])
    if rag:
        checked([PYTHON,'-m','pip','install','torch==2.14.1','--index-url','https://download.pytorch.org/whl/cpu'])
        checked([PYTHON,'-m','pip','install','-r',ROOT/'deploy/agent-demo/requirements-rag.txt'])
        checked([PYTHON,ROOT/'deploy/agent-demo/setup_knowledge.py'])
    template=ROOT/'deploy/agent-demo/.env.example'
    if not (STATE/'.env').exists(): shutil.copyfile(template,STATE/'.env')
    print('Setup complete; configure .agent-demo/.env before explicit model tasks.')


def start():
    STATE.mkdir(exist_ok=True)
    if (STATE/'processes.json').exists(): raise SystemExit('Run stop first; existing launch registry retained.')
    for port in (18927,5187):
        with socket.socket() as connection:
            if connection.connect_ex(('127.0.0.1',port))==0: raise SystemExit(f'Port {port} is occupied.')
    env=environment()
    manage=BACKEND/'manage.py'
    checked([PYTHON,manage,'migrate','--noinput'],cwd=BACKEND,env=env)
    checked([PYTHON,manage,'run_agent_demo','--initialize','--once'],cwd=BACKEND,env=env)
    node=shutil.which('node')
    vite=ROOT/'frontend/node_modules/vite/bin/vite.js'
    if not node or not vite.exists(): raise SystemExit('Install Node.js and run npm ci in frontend first.')
    commands=[('api',[PYTHON,manage,'runserver','127.0.0.1:18927','--noreload']),
        ('sampler',[PYTHON,manage,'run_agent_demo']),('worker',[PYTHON,manage,'run_agent_worker','--warm-knowledge']),
        ('web',[node,vite,'--host','127.0.0.1','--port','5187','--strictPort'])]
    launched=[];children=[]
    try:
        for name,command in commands:
            child_env={**env,'VITE_API_BASE_URL':'http://127.0.0.1:18927/api'}
            with (STATE/f'{name}.log').open('ab') as log:
                p=subprocess.Popen([str(x) for x in command],cwd=ROOT/'frontend' if name=='web' else BACKEND,
                    env=child_env,stdout=log,stderr=subprocess.STDOUT,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
            launched.append({'name':name,'pid':p.pid})
            children.append(p)
        deadline=time.monotonic()+30
        while time.monotonic()<deadline:
            if any(p.poll() is not None for p in children): raise SystemExit('A demo process exited; inspect .agent-demo/*.log.')
            try:
                with urlopen('http://127.0.0.1:18927/api/health/',timeout=1) as response: assert response.status==200
                with urlopen('http://127.0.0.1:5187/',timeout=1) as response: assert response.status==200
                break
            except (OSError,AssertionError): time.sleep(.3)
        else: raise SystemExit('Demo readiness timed out; inspect logs before retrying.')
    finally:
        (STATE/'processes.json').write_text(json.dumps(launched),encoding='utf-8')
    print('http://127.0.0.1:5187/agent-workbench ; accounts: .agent-demo/users.json (keep private)')


def stop():
    registry=STATE/'processes.json'
    if not registry.exists(): print('No launcher registry.');return
    for item in json.loads(registry.read_text(encoding='utf-8')):
        pid=int(item['pid'])
        if os.name=='nt':
            root=str(ROOT).replace("'","''")
            script=f"$p=Get-CimInstance Win32_Process -Filter 'ProcessId={pid}'; if ($p -and $p.CommandLine.Contains('{root}')) {{ Stop-Process -Id {pid} -Force }}"
            checked(['powershell','-NoProfile','-NonInteractive','-Command',script])
        else:
            cmd=Path(f'/proc/{pid}/cmdline')
            if cmd.exists() and str(ROOT).encode() in cmd.read_bytes(): os.kill(pid,15)
    registry.unlink()


def offline():
    if (STATE/'processes.json').exists(): raise SystemExit('Stop launcher before offline backup/restore.')
    db=STATE/'db.sqlite3'
    if db.exists():
        with sqlite3.connect(db) as connection:
            active=connection.execute("SELECT count(*) FROM operations_agentrun WHERE status IN ('queued','running')").fetchone()[0]
            if active: raise SystemExit('Cancel or finish active tasks before backup/restore.')


def backup():
    offline();folder=STATE/'backups';folder.mkdir(exist_ok=True)
    target=folder/(time.strftime('%Y%m%d-%H%M%S')+'-'+uuid4().hex[:8]+'.zip')
    with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED) as archive:
        for name in ('db.sqlite3','users.json','scenario.json'):
            file=STATE/name
            if file.exists(): archive.write(file,name)
        for file in (STATE/'media').rglob('*'):
            if file.is_file(): archive.write(file,str(file.relative_to(STATE)))
    print(target)
    return target


def restore(source):
    offline()
    # Restore only known relative data files; never overwrite scripts, secrets or venv.
    with zipfile.ZipFile(Path(source).resolve()) as archive:
        names=archive.namelist()
        for name in names:
            path=Path(name)
            if path.is_absolute() or '..' in path.parts or '\\' in name or ':' in name or not (name in {'db.sqlite3','users.json','scenario.json'} or name.startswith('media/')):
                raise SystemExit('Unsafe backup member: '+name)
        if 'db.sqlite3' not in names: raise SystemExit('No demonstration database in backup.')
        backup() # preserve the current data before replacement
        archive.extractall(STATE)
    print('Restored local demonstration data; business/evaluation databases were not selected.')


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('command',choices=['setup','start','stop','backup','restore'])
    parser.add_argument('--rag',action='store_true');parser.add_argument('--file')
    args=parser.parse_args()
    if args.command=='setup': setup(args.rag)
    elif args.command=='start': start()
    elif args.command=='stop': stop()
    elif args.command=='backup': backup()
    elif args.command=='restore':
        if not args.file: parser.error('restore requires --file')
        restore(args.file)
