from io import StringIO
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone
from .models import Asset, HardwareBinding, Telemetry


@override_settings(IS_PRODUCTION=False)
class LevelStationSeedTests(TestCase):
    def seed(self):
        call_command('seed_demo', stdout=StringIO())

    def test_five_independent_unconnected_stations(self):
        self.seed()
        stations = ['排水段', '吸水段', '泵入口', '阀后段', '回水段']
        for i, station in enumerate(stations, 1):
            asset = Asset.objects.get(code=f'LEVEL-L{i:02}')
            self.assertIn(station, asset.name)
            self.assertEqual(asset.mesh, f'MESH_V12-FSIR02_L{i:02}_PROBE')
            self.assertEqual(asset.status, Asset.Status.UNKNOWN)
            self.assertEqual(asset.integration_status, Asset.IntegrationStatus.PENDING_VERIFICATION)
            self.assertIsNone(asset.last_seen_at)
            self.assertIsNone(asset.latitude)
            self.assertEqual(asset.location_source, Asset.LocationSource.UNASSIGNED)
            self.assertFalse(Telemetry.objects.filter(asset=asset).exists())
            binding = HardwareBinding.objects.get(asset=asset)
            self.assertEqual(binding.status, HardwareBinding.Status.RESERVED)
            self.assertIsNone(binding.last_heartbeat_at)
            self.assertIn(asset.code.lower(), binding.endpoint)
        self.assertFalse(Asset.objects.filter(code='BT-01').exists())
        self.assertTrue(Asset.objects.filter(code='NET-01').exists())
        positions = Asset.objects.filter(code__startswith='LEVEL-L').values_list('position', flat=True)
        self.assertEqual(len({(p['x'], p['y']) for p in positions}), 5)

    def test_reseed_preserves_commissioned_level_sensor(self):
        self.seed()
        asset = Asset.objects.get(code='LEVEL-L01')
        asset.name = '现场确认测点'
        asset.status = Asset.Status.NORMAL
        asset.last_seen_at = timezone.now()
        asset.save()
        binding = HardwareBinding.objects.get(asset=asset)
        binding.endpoint = 'site/approved/level1'
        binding.save()
        self.seed()
        asset.refresh_from_db()
        binding.refresh_from_db()
        self.assertEqual(asset.name, '现场确认测点')
        self.assertEqual(asset.status, Asset.Status.NORMAL)
        self.assertIsNotNone(asset.last_seen_at)
        self.assertEqual(binding.endpoint, 'site/approved/level1')
        self.assertEqual(Asset.objects.filter(code__startswith='LEVEL-L').count(), 5)
