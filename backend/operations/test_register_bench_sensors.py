from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from .models import Asset, Telemetry


class RegisterBenchSensorsTests(TestCase):
    def test_registers_only_fitted_channels_without_overwriting_existing_assets(self):
        existing = Asset.objects.create(
            code='FLAME-05', name='现场确认的火焰五号', zone='UT-ZC',
            asset_type='火焰传感器', integration_status=Asset.IntegrationStatus.VERIFIED,
        )

        call_command('register_bench_sensors', stdout=StringIO())
        self.assertEqual(Asset.objects.count(), 31)
        self.assertFalse(Asset.objects.filter(code__in=['SHT-05', 'LEVEL-L05', 'O2-04', 'O2-05']).exists())
        self.assertEqual(Asset.objects.get(code='FLAME-05').pk, existing.pk)
        self.assertEqual(Asset.objects.get(code='FLAME-05').name, '现场确认的火焰五号')
        self.assertEqual(Asset.objects.get(code='SHT-03').location_source, Asset.LocationSource.UNASSIGNED)
        self.assertEqual(Asset.objects.get(code='O2-03').integration_status, Asset.IntegrationStatus.CALIBRATION_REQUIRED)
        self.assertEqual(Telemetry.objects.count(), 0)

        call_command('register_bench_sensors', stdout=StringIO())
        self.assertEqual(Asset.objects.count(), 31)
