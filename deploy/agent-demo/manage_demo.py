"""Local software demonstrator: explicit isolated profiles, no implicit paid calls."""
import argparse
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import socket
import sqlite3
import stat
import subprocess
import sys
import tempfile
import time
import zipfile
from uuid import uuid4
from urllib.request import ProxyHandler, build_opener

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / 'backend'
PROFILES = {'capabilities': ('.agent-capabilities', 'config.agent_capability_settings', 'agent-capabilities'),
            'demo': ('.agent-demo', 'config.agent_demo_settings', 'agent-demo')}
PROFILE = 'capabilities'
STATE = ROOT / PROFILES[PROFILE][0]
PYTHON = STATE / 'venv' / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
EXTERNAL_PYTHON = False
API_PORT, WEB_PORT = 18927, 5187
PRIVATE_FIELDS = {'DEEPSEEK_API_KEY', 'DEEPSEEK_MODEL', 'AGENT_EMBEDDING_MODEL_PATH',
                  'AGENT_EXPERIENCE_ENABLED', 'ANYJEV_URL', 'ANYJEV_TOKEN'}


def configure(profile='capabilities', python=None):
    global PROFILE, STATE, PYTHON, EXTERNAL_PYTHON
    if profile not in PROFILES:
        raise ValueError('Unknown software profile.')
    PROFILE = profile
    STATE = ROOT / PROFILES[profile][0]
    EXTERNAL_PYTHON = python is not None
    PYTHON = Path(python).resolve() if python else STATE / 'venv' / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')


def checked(command, **kwargs):
    subprocess.run([str(x) for x in command], check=True, **kwargs)


def guard_state():
    # Do not accept caller-provided state directories, symlinks, or a business DB.
    expected = ROOT.resolve() / PROFILES[PROFILE][0]
    if STATE.resolve() != expected or STATE.is_symlink():
        raise SystemExit('The launcher only selects its exact isolated software directory.')


def environment(*, allow_paid_model=False, no_paid_model=False, enable_router=False, key_env_file=None):
    from dotenv import dotenv_values
    guard_state()
    STATE.mkdir(exist_ok=True)
    env = os.environ.copy()
    private = dotenv_values(STATE / '.env')
    for key, value in private.items():
        if key in PRIVATE_FIELDS and value:
            env[key] = value
    if key_env_file:
        # Read only the model key. Never import settings, hardware keys or DB URLs.
        selected = dotenv_values(Path(key_env_file))
        env['DEEPSEEK_API_KEY'] = selected.get('DEEPSEEK_API_KEY', '') or ''
        if selected.get('DEEPSEEK_MODEL'):
            env['DEEPSEEK_MODEL'] = selected['DEEPSEEK_MODEL']
    if not allow_paid_model or no_paid_model:
        env['DEEPSEEK_API_KEY'] = ''
    env['ANYJEV_ENABLED'] = 'true' if enable_router else 'false'
    if not enable_router:
        env['ANYJEV_TOKEN'] = ''
    secret = STATE / 'secret.key'
    if not secret.exists():
        secret.write_text(secrets.token_urlsafe(48), encoding='utf-8')
    env.update(DJANGO_ENV='development', DJANGO_SETTINGS_MODULE=PROFILES[PROFILE][1],
               DJANGO_SECRET_KEY=secret.read_text(encoding='utf-8'),
               PYTHONUNBUFFERED='1', PYTHONIOENCODING='utf-8',
               DJANGO_DEBUG='false', DJANGO_ALLOWED_HOSTS='127.0.0.1,localhost')
    return env


def setup(rag=False):
    guard_state()
    STATE.mkdir(exist_ok=True)
    if EXTERNAL_PYTHON:
        if rag:
            raise SystemExit('--rag installation requires the dedicated venv; an external Python is never modified.')
        checked([PYTHON, '-c', 'import django,dotenv; print("Existing Python dependencies available")'])
    else:
        if not PYTHON.exists():
            checked([sys.executable, '-m', 'venv', STATE / 'venv'])
        checked([PYTHON, '-m', 'pip', 'install', '--require-hashes', '-r', BACKEND / 'requirements.lock'])
        if rag:
            checked([PYTHON, '-m', 'pip', 'install', 'torch==2.14.1', '--index-url', 'https://download.pytorch.org/whl/cpu'])
            checked([PYTHON, '-m', 'pip', 'install', '-r', ROOT / 'deploy/agent-demo/requirements-rag.txt'])
            checked([PYTHON, ROOT / 'deploy/agent-demo/setup_knowledge.py'])
    if not (STATE / '.env').exists():
        shutil.copyfile(ROOT / 'deploy/agent-demo/.env.example', STATE / '.env')
    print(f'Setup complete for {PROFILE}; private configuration: {STATE.name}/.env. Paid calls remain disabled by default.')


def process_identity(pid):
    if type(pid) is not int or pid <= 0:
        return None
    if os.name == 'nt':
        script = (f'$p=Get-CimInstance Win32_Process -Filter "ProcessId={pid}"; '
                  'if($p){[pscustomobject]@{created=$p.CreationDate.ToUniversalTime().Ticks;'
                  'command=$p.CommandLine}|ConvertTo-Json -Compress}')
        completed = subprocess.run(['powershell', '-NoProfile', '-NonInteractive', '-Command', script],
                                   capture_output=True, text=True, check=True, timeout=10)
        text = completed.stdout.strip()
        if not text:
            return None
        data = json.loads(text)
        command, marker = data.get('command') or '', str(data['created'])
    else:
        proc = Path('/proc') / str(pid)
        try:
            command = (proc / 'cmdline').read_bytes().replace(b'\x00', b' ').decode('utf-8')
            # comm may contain spaces; fields following the final ')' begin at field 3.
            marker = (proc / 'stat').read_text().rsplit(')', 1)[1].split()[19]
        except FileNotFoundError:
            return None
    if str(ROOT.resolve()).casefold() not in command.casefold():
        return {'startMarker': marker, 'commandHash': None, 'owned': False}
    return {'startMarker': marker, 'commandHash': hashlib.sha256(command.encode()).hexdigest(), 'owned': True}


def identity_matches(record, actual):
    identity = record.get('identity')
    return bool(actual and actual.get('owned') and isinstance(identity, dict)
                and identity.get('owned') and actual.get('startMarker') == identity.get('startMarker')
                and actual.get('commandHash') == identity.get('commandHash') and actual.get('commandHash'))


def terminate_record(record):
    actual = process_identity(record['pid'])
    if actual is None:
        return True
    if not identity_matches(record, actual):
        return False
    if os.name == 'nt':
        # Repeat both checks inside the same native operation before stopping.
        identity = record['identity']
        root = str(ROOT.resolve()).replace("'", "''")
        marker = int(identity['startMarker'])
        digest = identity['commandHash']
        script = (f'$p=Get-CimInstance Win32_Process -Filter "ProcessId={record["pid"]}"; '
                  'if($p){$sha=[Security.Cryptography.SHA256]::Create();'
                  '$hash=([BitConverter]::ToString($sha.ComputeHash([Text.Encoding]::UTF8.GetBytes($p.CommandLine)))).Replace("-", "").ToLower();'
                  f'if($p.CreationDate.ToUniversalTime().Ticks -ne {marker} -or $hash -ne \'{digest}\' '
                  f'-or -not $p.CommandLine.Contains(\'{root}\')){{exit 9}}; Stop-Process -Id {record["pid"]} -ErrorAction Stop}}')
        checked(['powershell', '-NoProfile', '-NonInteractive', '-Command', script])
    else:
        os.kill(record['pid'], 15)
    return True


def write_registry(records):
    (STATE / 'processes.json').write_text(json.dumps({'schemaVersion': 2, 'profile': PROFILE,
        'settings': PROFILES[PROFILE][1], 'processes': records}, indent=2), encoding='utf-8')


def fetch_json(url):
    with build_opener(ProxyHandler({})).open(url, timeout=1) as response:
        if response.status != 200:
            raise OSError('Readiness unavailable.')
        return json.load(response)


def start(no_paid_model=False, *, allow_paid_model=False, enable_router=False, key_env_file=None):
    guard_state()
    STATE.mkdir(exist_ok=True)
    if (STATE / 'processes.json').exists():
        raise SystemExit(f'Run stop --profile {PROFILE} first; the existing registry is retained.')
    for port in (API_PORT, WEB_PORT):
        with socket.socket() as connection:
            if connection.connect_ex(('127.0.0.1', port)) == 0:
                raise SystemExit(f'Port {port} is occupied; no existing process was stopped.')
    if not PYTHON.is_file():
        raise SystemExit('Run setup or specify --python with an existing configured interpreter.')
    node = shutil.which('node')
    vite = ROOT / 'frontend/node_modules/vite/bin/vite.js'
    if not node or not vite.exists():
        raise SystemExit('Install Node.js and run npm ci in frontend first.')
    env = environment(allow_paid_model=allow_paid_model, no_paid_model=no_paid_model,
                      enable_router=enable_router, key_env_file=key_env_file)
    manage = BACKEND / 'manage.py'
    checked([PYTHON, manage, 'migrate', '--noinput'], cwd=BACKEND, env=env)
    # Upgrades exact V24 without flushing existing tasks, cases or scene history.
    checked([PYTHON, manage, 'prepare_agent_release'], cwd=BACKEND, env=env)
    commands = [('api', [PYTHON, manage, 'runserver', f'127.0.0.1:{API_PORT}', '--noreload']),
                ('sampler', [PYTHON, manage, 'run_agent_demo']),
                ('worker', [PYTHON, manage, 'run_agent_worker', '--warm-knowledge']),
                ('web', [node, vite, '--host', '127.0.0.1', '--port', str(WEB_PORT), '--strictPort'])]
    launched, children = [], []
    try:
        for name, command in commands:
            child_env = {**env, 'VITE_API_BASE_URL': f'http://127.0.0.1:{API_PORT}/api'}
            with (STATE / f'{name}.log').open('ab') as log:
                process = subprocess.Popen([str(x) for x in command],
                    cwd=ROOT / 'frontend' if name == 'web' else BACKEND,
                    env=child_env, stdout=log, stderr=subprocess.STDOUT,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
            children.append(process)
            identity = process_identity(process.pid)
            if identity is None or not identity['owned']:
                raise SystemExit('A launcher child exited or its identity could not be verified.')
            launched.append({'name': name, 'pid': process.pid, 'identity': identity})
        write_registry(launched)
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            if any(process.poll() is not None for process in children):
                raise SystemExit(f'A software demo process exited; inspect {STATE.name}/*.log.')
            try:
                ready = fetch_json(f'http://127.0.0.1:{API_PORT}/api/ready/')
                if ready.get('profile') != PROFILES[PROFILE][2]:
                    raise SystemExit('Readiness profile differs from the requested software sandbox.')
                with build_opener(ProxyHandler({})).open(f'http://127.0.0.1:{WEB_PORT}/', timeout=1) as response:
                    if response.status != 200:
                        raise OSError('Frontend unavailable.')
                break
            except OSError:
                time.sleep(.3)
        else:
            raise SystemExit('Readiness timed out; no existing service was stopped.')
    except BaseException:
        # Popen handles identify children from this attempt; never terminate existing apps.
        for process in children:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
        (STATE / 'processes.json').unlink(missing_ok=True)
        raise
    print(f'http://127.0.0.1:{WEB_PORT}/agent-workbench ; profile={PROFILE}; accounts: {STATE.name}/users.json (keep private)')
    print('Paid model transport: ' + ('explicitly enabled for submitted tasks' if env.get('DEEPSEEK_API_KEY') else 'disabled'))
    print('Local decision routing: ' + ('explicitly enabled' if enable_router else 'disabled'))


def stop():
    guard_state()
    registry = STATE / 'processes.json'
    if not registry.exists():
        print('No launcher registry.'); return
    saved = json.loads(registry.read_text(encoding='utf-8'))
    if not isinstance(saved, dict) or saved.get('profile') != PROFILE or saved.get('schemaVersion') != 2:
        raise SystemExit('Legacy or foreign process registry: inspect identity manually; no processes stopped.')
    refused = []
    for item in saved['processes']:
        if not terminate_record(item):
            refused.append(item)
    if refused:
        write_registry(refused)
        raise SystemExit('Process identity mismatch; unrelated processes were not stopped. Registry retained.')
    registry.unlink()
    print(f'Stopped only verified {PROFILE} launcher processes.')


def offline():
    guard_state()
    if (STATE / 'processes.json').exists():
        raise SystemExit('Stop this software launcher before offline backup/restore.')
    db = STATE / 'db.sqlite3'
    if db.exists():
        with closing(sqlite3.connect(db.as_uri() + '?mode=ro', uri=True)) as connection:
            active = connection.execute("SELECT count(*) FROM operations_agentrun WHERE status IN ('queued','running')").fetchone()[0]
            if active:
                raise SystemExit('Cancel or finish active tasks before backup/restore.')


def backup():
    offline()
    db = STATE / 'db.sqlite3'
    if not db.is_file():
        raise SystemExit('No initialized software database to back up.')
    folder = STATE / 'backups'; folder.mkdir(exist_ok=True)
    target = folder / (time.strftime('%Y%m%d-%H%M%S') + '-' + uuid4().hex[:8] + '.zip')
    with zipfile.ZipFile(target, 'w', zipfile.ZIP_DEFLATED) as archive:
        # SQLite backup includes committed WAL content, unlike copying db.sqlite3.
        with tempfile.TemporaryDirectory(prefix='backup-', dir=STATE) as temporary:
            standalone = Path(temporary) / 'db.sqlite3'
            with closing(sqlite3.connect(db.as_uri() + '?mode=ro', uri=True)) as original, \
                    closing(sqlite3.connect(standalone)) as saved:
                original.backup(saved)
                saved.execute('PRAGMA journal_mode=DELETE')
            archive.write(standalone, 'db.sqlite3')
        archive.writestr('backup-manifest.json', json.dumps({'schemaVersion': 1, 'profile': PROFILE,
            'settings': PROFILES[PROFILE][1], 'includesCredentials': True, 'excludesSecrets': True}))
        for name in ('users.json', 'scenario.json'):
            file = STATE / name
            if file.is_file(): archive.write(file, name)
        for file in (STATE / 'media').rglob('*'):
            if file.is_symlink():
                raise SystemExit('Media symlinks are not accepted in a software backup.')
            if file.is_file(): archive.write(file, file.relative_to(STATE).as_posix())
    print(target)
    return target


def validate_archive(archive):
    entries = archive.infolist(); names = [entry.filename for entry in entries]
    if len(names) != len(set(names)) or sum(entry.file_size for entry in entries) > 1024 ** 3:
        raise SystemExit('Duplicate or oversized software backup.')
    for entry in entries:
        name = entry.filename; path = Path(name)
        if (not name or path.is_absolute() or '..' in path.parts or '\\' in entry.orig_filename or ':' in name
                or stat.S_ISLNK(entry.external_attr >> 16)
                or not (name in {'db.sqlite3', 'users.json', 'scenario.json', 'backup-manifest.json'} or name.startswith('media/'))
                or not (STATE.resolve() / path).resolve().is_relative_to(STATE.resolve())):
            raise SystemExit('Unsafe backup member: ' + name)
    if 'db.sqlite3' not in names:
        raise SystemExit('No software database in backup.')
    if 'backup-manifest.json' in names:
        manifest = json.loads(archive.read('backup-manifest.json'))
        if manifest.get('profile') != PROFILE or manifest.get('settings') != PROFILES[PROFILE][1]:
            raise SystemExit('Backup belongs to a different software profile.')
    elif PROFILE != 'demo':
        raise SystemExit('A capabilities backup must have its profile manifest; legacy demo archives stay in demo.')
    with closing(sqlite3.connect(':memory:')) as memory:
        memory.deserialize(archive.read('db.sqlite3'))
        if memory.execute('PRAGMA quick_check').fetchone()[0] != 'ok':
            raise SystemExit('Backup SQLite integrity check failed.')
        memory.execute('SELECT count(*) FROM operations_agentrun').fetchone()


def restore(source):
    offline()
    with zipfile.ZipFile(Path(source).resolve()) as archive:
        validate_archive(archive)
        if (STATE / 'db.sqlite3').exists():
            backup()  # preserve displaced state before replacement
        with tempfile.TemporaryDirectory(prefix='restore-', dir=STATE) as temporary:
            archive.extractall(temporary)
            staged = Path(temporary)
            for name in ('db.sqlite3-wal', 'db.sqlite3-shm'):
                (STATE / name).unlink(missing_ok=True)
            for file in staged.rglob('*'):
                if file.is_file() and file.name != 'backup-manifest.json':
                    destination = STATE / file.relative_to(staged)
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    file.replace(destination)
    print(f'Restored only {PROFILE} software data; business, hardware and other evaluation databases were not selected.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['setup', 'start', 'stop', 'backup', 'restore'])
    parser.add_argument('--profile', choices=PROFILES, default='capabilities')
    parser.add_argument('--python', help='Use an existing configured Python without installing into it.')
    parser.add_argument('--rag', action='store_true'); parser.add_argument('--file')
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--no-paid-model', action='store_true')
    group.add_argument('--allow-paid-model', action='store_true')
    parser.add_argument('--enable-router', action='store_true')
    parser.add_argument('--key-env-file', help='Read only DEEPSEEK_API_KEY/MODEL from this private file for an explicit paid launch.')
    args = parser.parse_args()
    if args.key_env_file and not args.allow_paid_model:
        parser.error('--key-env-file requires --allow-paid-model')
    configure(args.profile, args.python)
    if args.command == 'setup': setup(args.rag)
    elif args.command == 'start':
        start(args.no_paid_model, allow_paid_model=args.allow_paid_model, enable_router=args.enable_router, key_env_file=args.key_env_file)
    elif args.command == 'stop': stop()
    elif args.command == 'backup': backup()
    else:
        if not args.file: parser.error('restore requires --file')
        restore(args.file)


if __name__ == '__main__':
    main()
