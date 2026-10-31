from collections import Counter
from copy import deepcopy
from django.contrib.auth.models import User
from django.test import TestCase
from rest_framework.test import APIClient
from .agent_operations import station_snapshot, location_cards
from .models import Asset, HardwareBinding, Profile, TwinModelRelease
from .twin_presentation import BASE_INVENTORY, V24, V24_UNIFIED, runtime_inventory, presentation_for_release
from .management.commands.install_twin_v24 import validate_registry


class UnifiedSensorPresentationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('unified-operator')
        Profile.objects.create(user=self.user, role='operator')
        self.client = APIClient(); self.client.force_authenticate(self.user)
        for b in BASE_INVENTORY['bindings']:
            a = Asset.objects.create(code=b['assetCode'], name=b['physicalTag'], asset_type='sensor',
                mesh=V24_UNIFIED['sensorMeshes'][b['assetCode']], zone=V24_UNIFIED['sensorStations'][b['assetCode']])
            HardwareBinding.objects.create(asset=a, protocol='mqtt', device_identifier='test:'+a.code,
                endpoint=f'ut/v1/{b["controllerId"]}/telemetry')
        for code, mesh in V24_UNIFIED['controllerMeshes'].items():
            Asset.objects.create(code=code, name=code, mesh=mesh, asset_type='controller')
        self.release = TwinModelRelease.objects.create(version='unified-test', model_file='unused.glb',
            original_name='unified.glb', sha256=V24_UNIFIED['modelSha256'], size_bytes=100, node_count=755,
            node_inventory_available=True, node_names=list(Asset.objects.values_list('mesh', flat=True)),
            status='active', uploaded_by=self.user, is_compatible=True)

    def test_every_physical_tag_and_unique_target_aligns_without_changing_wire_owners(self):
        before = deepcopy(BASE_INVENTORY)
        rows = runtime_inventory()['bindings']
        self.assertEqual(len(rows), 31)
        self.assertEqual(len({b['targetNode'] for b in rows}), 31)
        self.assertTrue(all(b['physicalTag'] == b['modelPhysicalTag'] for b in rows))
        self.assertEqual(Counter(b['controllerId'] for b in rows), {'CTRL-01':11,'CTRL-02':7,'CTRL-03':6,'CTRL-04':7})
        self.assertEqual(BASE_INVENTORY, before)
        validate_registry({a.code:a for a in Asset.objects.all()})
        self.assertEqual(self.client.get('/api/twin/model-readiness/').data['status'], 'ready')

    def test_all_four_primary_sensor_families_share_station_suffix_and_resolve_correct_cards(self):
        report = station_snapshot('all')
        for b in report['items']:
            self.assertEqual(b['mapping_status'], 'active_model_node_verified')
            if b['physicalTag'].startswith(('MQ2-', 'MQ4-', 'CO-', 'FLAME-')):
                self.assertEqual(b['stationId'], 'P'+str(int(b['physicalTag'][-2:])))
                cards = location_cards([{'id':'E1','tool':'asset_snapshot','status':'ok','data':{'asset_code':b['assetCode']}}])
                self.assertEqual((cards[0]['assetCode'], cards[0]['stationId']), (b['assetCode'], b['stationId']))

    def test_oxygen_is_01_02_03_and_module_locations_remain_explicit(self):
        rows = {b['assetCode']:b for b in runtime_inventory()['bindings']}
        for code, station in [('GAS-O2-01','P1'), ('GAS-O2-02','P2'), ('GAS-O2-03','P5')]:
            self.assertEqual((rows[code]['targetNode'], rows[code]['stationId']), (code, station))
        for n in range(1,5):
            for code in (f'ENV-{n:02}', f'LEVEL-L{n:02}'):
                self.assertEqual(V24_UNIFIED['sensorMeshes'][code], V24['sensorMeshes'][code])
                self.assertEqual(V24_UNIFIED['sensorStations'][code], V24['sensorStations'][code])

    def test_original_model_has_its_original_descriptor_and_hash_mismatch_does_not_claim_unified(self):
        self.release.sha256 = V24['modelSha256']
        self.assertEqual(presentation_for_release(self.release)['revision'], V24['revision'])
        self.release.sha256 = '0'*64
        self.assertIsNone(presentation_for_release(self.release))
