"""Frozen hardware identity and evidence metadata, not a calibration certificate."""
import json
from pathlib import Path
from datetime import timedelta
from django.conf import settings
from django.utils.dateparse import parse_datetime

INVENTORY = json.loads((Path(__file__).parent / 'agent_catalog/station-inventory.json').read_text(encoding='utf-8'))
OWNERS = {b['assetCode']: b['controllerId'] for b in INVENTORY['bindings']}
OWNERS.update(INVENTORY['fanControllers'])
OWNERS.update({f'CTRL-0{i}': f'CTRL-0{i}' for i in range(1, 5)})
SPECS = {}
for b in INVENTORY['bindings']:
    kind = b['physicalTag'].split('-')[0]
    SPECS[b['assetCode']] = {
        'MQ2': {'smoke.alarm': ('bool', 0, 1)}, 'MQ4': {'methane.raw': ('adc', 0, 4095)},
        'CO': {'co.raw': ('adc', 0, 4095)}, 'FLAME': {'flame.alarm': ('bool', 0, 1)},
        'LEVEL': {'level.detected': ('bool', 0, 1)},
        'SHT': {'temperature': ('°C', -45, 130), 'humidity': ('%RH', 0, 100)},
        'O2': {'oxygen.raw': ('adc', 0, 4095), 'oxygen.voltage': ('mV', 0, 3300)},
    }[kind]
for fan in INVENTORY['fanControllers']:
    SPECS[fan] = {'rotational.speed': ('rpm', 0, 1e9), 'supply.voltage': ('V', 0, 1e9),
        'motor.current': ('mA', -1e9, 1e9), 'power': ('W', -1e9, 1e9),
        'pwm.duty': ('%', 0, 100), 'relay.commanded': ('bool', 0, 1)}
for i in range(1, 5):
    SPECS[f'CTRL-0{i}'] = {'heartbeat': ('bool', 1, 1)}


def hardware_live_enabled():
    return bool(getattr(settings, 'HARDWARE_LIVE_MODE', False))


def validate_provenance(attrs):
    p = attrs.get('provenance', {})
    if not isinstance(p, dict):
        raise ValueError('Telemetry provenance must be an object.')
    if not p:
        if hardware_live_enabled():
            raise ValueError('实物联调只接收带来源信息的四主控遥测；不接受模拟或旧格式数据。')
        return
    required = {'source', 'controllerId', 'frameId', 'layoutVersion', 'rawOnly', 'clockSource', 'sampleAgeMs', 'frameTimestamp'}
    if set(p) - (required | {'seq'}) or required - set(p):
        raise ValueError('Invalid telemetry provenance fields.')
    if (p['source'] != 'four-controller-rtu-v2' or p['layoutVersion'] != INVENTORY['revision']
            or p['rawOnly'] is not True or OWNERS.get(attrs['assetCode']) != p['controllerId']):
        raise ValueError('Telemetry source, layout or controller ownership does not match the frozen inventory.')
    import re
    if not isinstance(p['frameId'], str) or not re.fullmatch(r'[A-Za-z0-9._:-]{1,80}', p['frameId']):
        raise ValueError('Invalid frame identity.')
    if 'seq' in p and (type(p['seq']) is not int or p['seq'] < 0):
        raise ValueError('Invalid sequence.')
    if type(p['sampleAgeMs']) is not int or not 0 <= p['sampleAgeMs'] <= 700000:
        raise ValueError('Invalid sample age.')
    if p['clockSource'] not in {'gateway-ntp', 'receiver-estimated'}:
        raise ValueError('Invalid clock source.')
    frame_time = parse_datetime(p['frameTimestamp']) if isinstance(p['frameTimestamp'], str) else None
    if not frame_time or frame_time.utcoffset() is None or abs((frame_time-timedelta(milliseconds=p['sampleAgeMs'])-attrs['recordedAt']).total_seconds()) > .002:
        raise ValueError('Sample time disagrees with frame timestamp and sample age.')
    spec = SPECS.get(attrs['assetCode'], {}).get(attrs['metricKey'])
    if not spec or attrs['unit'] != spec[0] or not spec[1] <= attrs['value'] <= spec[2]:
        raise ValueError('Metric, unit or range does not match the hardware inventory.')
    if spec[0] in {'bool', 'adc'} and not attrs['value'].is_integer():
        raise ValueError('Digital and ADC values must be integers.')
    if attrs['quality'] == 'good' and (attrs['metricKey'].startswith('oxygen.')
            or p['clockSource'] != 'gateway-ntp' or p['sampleAgeMs'] > 5000
            or (attrs['metricKey'] in {'methane.raw', 'co.raw'} and attrs['value'] == 4095)):
        raise ValueError('Uncalibrated oxygen, saturated ADC or uncertain time cannot be labelled good.')
