"""Register the physical two-node bench sensor channels without demo data."""

from django.core.management.base import BaseCommand
from django.db import transaction

from operations.models import Asset


def sensor_specs():
    specs = []

    sht_pins = [
        ('PB6/PB7 I2C 0x44', '01'),
        ('PB6/PB7 I2C 0x45', '02'),
        ('PB10/PB11 I2C 0x44', '04'),
        ('PB10/PB11 I2C 0x45', '05'),
    ]
    for number, (pins, model_station) in enumerate(sht_pins, 1):
        specs.append((
            f'SHT-{number:02}', f'温湿度 {number:02}', 'UT-ZA', '温湿度传感器',
            f'Node A {pins}', ['temperature', 'humidity'],
            Asset.IntegrationStatus.FIRMWARE_CONNECTED,
            f'Physical model station {model_station}; SHT-03 model station is empty. Firmware channel numbering is consecutive.',
        ))

    level_pins = ['Node A PC0', 'Node A PC12', 'Node A PC13', 'Node B PC10']
    for number, pins in enumerate(level_pins, 1):
        specs.append((
            f'LEVEL-L{number:02}', f'液位 {number:02}', 'UT-ZB', '管道液位测点',
            f'{pins} / DO', ['level.detected'],
            Asset.IntegrationStatus.FIRMWARE_CONNECTED,
            'Physical level channel; LEVEL-L05 was removed and must not be registered.',
        ))

    flame_pins = ['Node A PB14', 'Node A PC8', 'Node A PC9', 'Node B PC6', 'Node B PC7']
    for number, pins in enumerate(flame_pins, 1):
        specs.append((
            f'FLAME-{number:02}', f'火焰 {number:02}', 'UT-ZC', '火焰传感器',
            f'{pins} / DO active low', ['flame.alarm'],
            Asset.IntegrationStatus.FIRMWARE_CONNECTED,
            'Physical digital flame channel.',
        ))

    mq2_pins = ['Node A PB12', 'Node A PB13', 'Node A PC11', 'Node B PC8', 'Node B PC9']
    for number, pins in enumerate(mq2_pins, 1):
        specs.append((
            f'MQ2-{number:02}', f'MQ-2 烟雾 {number:02}', 'UT-ZC', '烟雾传感器',
            f'{pins} / DO', ['smoke.alarm'],
            Asset.IntegrationStatus.FIRMWARE_CONNECTED,
            'Digital comparator output; alarm state is not a calibrated smoke concentration.',
        ))

    mq4_pins = ['Node A PC2', 'Node A PA4', 'Node B PA0', 'Node B PA1', 'Node B PA4']
    for number, pins in enumerate(mq4_pins, 1):
        specs.append((
            f'MQ4-{number:02}', f'MQ-4 甲烷 {number:02}', 'UT-ZC', '甲烷传感器',
            f'{pins} / ADC', ['raw', 'voltage'],
            Asset.IntegrationStatus.CALIBRATION_REQUIRED,
            'ADC and voltage only; no calibrated methane concentration.',
        ))

    co_pins = ['Node A PC1', 'Node A PA0', 'Node A PB1', 'Node B PB0', 'Node B PB1']
    for number, pins in enumerate(co_pins, 1):
        specs.append((
            f'CO-{number:02}', f'MQ-7 一氧化碳 {number:02}', 'UT-ZC', '一氧化碳传感器',
            f'{pins} / ADC', ['raw', 'voltage'],
            Asset.IntegrationStatus.CALIBRATION_REQUIRED,
            'MQ-7 ADC and voltage only; no calibrated CO concentration.',
        ))

    o2_pins = [('Node A PC3', '01'), ('Node A PA5', '03'), ('Node B PA6', '05')]
    for number, (pins, model_station) in enumerate(o2_pins, 1):
        specs.append((
            f'O2-{number:02}', f'氧气探头 {number:02}', 'UT-ZC', '氧气传感器',
            f'{pins} / ADC', ['raw', 'voltage'],
            Asset.IntegrationStatus.CALIBRATION_REQUIRED,
            f'Physical model station {model_station}. No signal-conditioning circuit is installed; raw ADC/voltage is not an oxygen concentration or a safety alarm.',
        ))

    return specs


class Command(BaseCommand):
    help = 'Idempotently register fitted Node A/B sensor channels; never create readings or removed channels.'

    def handle(self, *args, **options):
        created = []
        existing = []
        with transaction.atomic():
            for code, name, zone, asset_type, interface, capabilities, integration_status, note in sensor_specs():
                _, was_created = Asset.objects.get_or_create(
                    code=code,
                    defaults={
                        'name': name,
                        'zone': zone,
                        'asset_type': asset_type,
                        'status': Asset.Status.UNKNOWN,
                        'integration_status': integration_status,
                        'interface': interface,
                        'capabilities': capabilities,
                        'mesh': '',
                        'position': {},
                        'latitude': None,
                        'longitude': None,
                        'location_source': Asset.LocationSource.UNASSIGNED,
                        'installation_note': note,
                        'is_active': True,
                    },
                )
                (created if was_created else existing).append(code)
        self.stdout.write(f'Created {len(created)} sensor assets: {", ".join(created)}')
        self.stdout.write(f'Preserved {len(existing)} existing sensor assets: {", ".join(existing)}')
