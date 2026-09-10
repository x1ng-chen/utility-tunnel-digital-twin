"""Run browser regression against disposable data, never the local demo DB.

Usage: backend/.venv/Scripts/python tools/e2e/isolated_api.py
Set E2E_API_URL=http://127.0.0.1:18000/api when running ops.spec.cjs.
Stop with Ctrl+C; the temporary database and uploaded test models are removed.
"""
import os
import argparse
import socket
from pathlib import Path
import sys
from tempfile import TemporaryDirectory


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=18000)
    port = parser.parse_args().port
    if not 1024 <= port <= 65535:
        parser.error('port must be between 1024 and 65535')
    # Fail before seeding if another service already owns the test endpoint.
    # Otherwise a runner may silently exercise a previous run's database.
    with socket.socket() as probe:
        try:
            probe.bind(('127.0.0.1', port))
        except OSError:
            parser.error(f'127.0.0.1:{port} is already in use; choose another --port')
    backend = Path(__file__).resolve().parents[2] / 'backend'
    sys.path.insert(0, str(backend))
    # Set before importing settings; dotenv must not select a developer database.
    os.environ['DJANGO_ENV'] = 'test'
    os.environ['DATABASE_URL'] = ''
    os.environ['DJANGO_SETTINGS_MODULE'] = 'config.settings'
    os.environ['LOGIN_RATE_LIMIT'] = '100/min'
    os.environ['REGISTRATION_RATE_LIMIT'] = '100/hour'
    os.environ['PASSWORD_SETUP_RATE_LIMIT'] = '100/min'
    os.environ['PASSWORD_CHANGE_RATE_LIMIT'] = '100/hour'
    import config.settings as configuration
    import django
    from django.core.management import call_command

    with TemporaryDirectory(prefix='ut-e2e-isolated-') as directory:
        root = Path(directory)
        configuration.DATABASES = {'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': root / 'test.sqlite3'}}
        configuration.MEDIA_ROOT = root / 'media'
        configuration.ALLOWED_HOSTS = ['127.0.0.1', 'localhost']
        configuration.CORS_ALLOWED_ORIGINS = ['http://127.0.0.1:5173', 'http://localhost:5173']
        configuration.WEBSOCKET_ALLOWED_ORIGINS = list(configuration.CORS_ALLOWED_ORIGINS)
        django.setup()
        call_command('migrate', interactive=False, verbosity=0)
        call_command('seed_demo')
        print(f'Isolated browser-test data: {root}', flush=True)
        print(f'Use E2E_API_URL=http://127.0.0.1:{port}/api', flush=True)
        try:
            call_command('runserver', f'127.0.0.1:{port}', use_reloader=False)
        finally:
            from django.db import connections
            connections.close_all()


if __name__ == '__main__':
    main()
