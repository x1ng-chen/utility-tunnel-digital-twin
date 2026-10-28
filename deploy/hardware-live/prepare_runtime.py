"""Create private configuration without copying any business credentials/data."""
import argparse
import json
import secrets
from pathlib import Path
from dotenv import dotenv_values

root = Path(__file__).resolve().parents[2]
parser = argparse.ArgumentParser()
parser.add_argument('--mqtt-url', default='mqtt://127.0.0.1:1884')
options = parser.parse_args()
runtime = root / '.hardware-live'
runtime.mkdir(parents=True, exist_ok=True)
config_path = runtime / '.env'
existing = dotenv_values(config_path) if config_path.exists() else {}
config = {
    'DJANGO_ENV': 'development', 'DJANGO_DEBUG': 'false',
    'DJANGO_ALLOWED_HOSTS': '127.0.0.1,localhost',
    'DJANGO_SECRET_KEY': existing.get('DJANGO_SECRET_KEY') or secrets.token_urlsafe(48),
    'DJANGO_INGEST_API_KEY': existing.get('DJANGO_INGEST_API_KEY') or secrets.token_urlsafe(48),
    'CONNECTIVITY_MONITOR_TOKEN': existing.get('CONNECTIVITY_MONITOR_TOKEN') or secrets.token_urlsafe(48),
    'LOCAL_MQTT_URL': options.mqtt_url, 'LOCAL_DEVICE_ID': 'CTRL-01',
    'LOCAL_DEVICE_IDS': 'CTRL-01,CTRL-02,CTRL-03,CTRL-04',
    'REQUIRE_FOUR_CONTROLLER_TELEMETRY': 'true', 'IOTDA_ENABLED': 'false',
    'DJANGO_API_URL': 'http://127.0.0.1:8000',
    'DJANGO_QUEUE_DB': (runtime / 'outbox.sqlite').as_posix(),
    'DEEPSEEK_API_KEY': '',
}
if '\n' in options.mqtt_url or '\r' in options.mqtt_url or not options.mqtt_url.startswith(('mqtt://', 'mqtts://')):
    raise SystemExit('Invalid MQTT URL.')
config_path.write_text(''.join(f'{k}={v}\n' for k, v in config.items()), encoding='utf-8')
print(json.dumps({'profile': 'hardware-live', 'privateConfig': str(config_path),
    'businessDatabaseTouched': False, 'hardwareCommandsEnabled': False, 'paidModelCallsEnabled': False}))
