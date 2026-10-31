from collections import Counter
from copy import deepcopy
from django.contrib.auth.models import User
from django.core.management.base import CommandError
from django.test import TestCase
from rest_framework.test import APIClient
from .agent_operations import station_snapshot, location_cards
from .models import Asset, HardwareBinding, Profile, TwinModelRelease
from .twin_presentation import BASE_INVENTORY, V20, V24, runtime_inventory, presentation_for_release
from .management.commands.install_twin_v24 import validate_registry


class V24PresentationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('v24-operator')
        Profile.objects.create(user=self.user, role='operator')
        self.client = APIClient(); self.client.force_authenticate(self.user)
        for b in BASE_INVENTORY['bindings']:
            a = Asset.objects.create(code=b['assetCode'], name=b['physicalTag'], asset_type='sensor',
                zone=V24['sensorStations'][b['assetCode']], mesh=V24['sensorMeshes'][b['assetCode']])
            HardwareBinding.objects.create(asset=a, protocol='mqtt', device_identifier='test:'+a.code,
                endpoint=f'ut/v1/{b["controllerId"]}/telemetry')
        for code, mesh in V24['controllerMeshes'].items():
            Asset.objects.create(code=code, name=code, asset_type='controller', mesh=mesh)
        self.release = TwinModelRelease.objects.create(version='v24-test', model_file='unused.glb',
            original_name='v24.glb', sha256=V24['modelSha256'], size_bytes=100, node_count=755,
            node_inventory_available=True, node_names=list(Asset.objects.values_list('mesh', flat=True)),
            status='active', uploaded_by=self.user, is_compatible=True)

    def test_all_31_wire_ids_and_owners_preserved_with_unique_new_meshes(self):
        inventory = runtime_inventory()
        self.assertEqual(len(inventory['bindings']), 31)
        self.assertEqual(len({b['targetNode'] for b in inventory['bindings']}), 31)
        self.assertEqual(Counter(b['controllerId'] for b in inventory['bindings']),
            {'CTRL-01':11, 'CTRL-02':7, 'CTRL-03':6, 'CTRL-04':7})
        self.assertEqual({b['assetCode']: b['controllerId'] for b in inventory['bindings']},
            {b['assetCode']: b['controllerId'] for b in BASE_INVENTORY['bindings']})
        report = station_snapshot('all')
        self.assertTrue(all(b['mapping_status'] == 'active_model_node_verified' for b in report['items']))
        self.assertEqual(self.client.get('/api/twin/model-readiness/').data['status'], 'ready')

    def test_renumbered_flame_and_oxygen_locate_by_wire_identity(self):
        rows = {b['assetCode']: b for b in runtime_inventory()['bindings']}
        for code, station in [('FLAME-01', 'P1'), ('FLAME-02', 'P2'), ('FLAME-04', 'P4')]:
            self.assertEqual((rows[code]['targetNode'], rows[code]['stationId']), (code, station))
            self.assertEqual(rows[code]['modelPhysicalTag'], code)
        for code, target, station in [('GAS-O2-01','GAS-O2-01','P1'),
                ('GAS-O2-02','GAS-O2-05','P5'), ('GAS-O2-03','GAS-O2-02','P2')]:
            self.assertEqual((rows[code]['targetNode'], rows[code]['stationId']), (target, station))
        cards = location_cards([{'id':'E1','tool':'asset_snapshot','status':'ok','data':{'asset_code':'FLAME-02'}}])
        self.assertEqual(cards[0]['stationId'], 'P2')
        self.assertEqual(cards[0]['controllerId'], 'CTRL-03')

    def test_p5_has_no_temperature_module_and_all_five_stations_have_a_flame_sensor(self):
        for station in ('P1','P2','P3','P4','P5'):
            report = station_snapshot(station)
            self.assertEqual(sum(b['physicalTag'].startswith('FLAME') for b in report['items']), 1)
        self.assertFalse(any(b['physicalTag'].startswith('SHT') for b in station_snapshot('P5')['items']))

    def test_exact_hash_only_and_old_adapter_still_supported(self):
        self.release.sha256 = '0'*64
        self.assertIsNone(presentation_for_release(self.release))
        self.release.sha256 = V20['modelSha256']
        self.assertEqual(presentation_for_release(self.release)['revision'], V20['revision'])

    def test_overlay_does_not_mutate_wire_inventory(self):
        before = deepcopy(BASE_INVENTORY)
        runtime_inventory()['bindings'][0]['targetNode'] = 'arbitrary'
        self.assertEqual(BASE_INVENTORY, before)

    def test_registry_preflight_refuses_partial_unknown_or_wrong_controller_mapping(self):
        assets = {a.code: a for a in Asset.objects.all()}
        validate_registry(assets)
        missing = dict(assets); missing.pop('FLAME-05')
        with self.assertRaises(CommandError): validate_registry(missing)
        assets['FLAME-05'].mesh = 'UNREVIEWED'
        with self.assertRaises(CommandError): validate_registry(assets)

    def test_known_previous_flame_cycle_can_be_migrated_without_accepting_arbitrary_meshes(self):
        assets = {a.code: a for a in Asset.objects.all()}
        for code, old_mesh in {'FLAME-01':'FLAME-04', 'FLAME-02':'FLAME-01', 'FLAME-04':'FLAME-02'}.items():
            assets[code].mesh = old_mesh
        validate_registry(assets)
        assets['FLAME-02'].mesh = 'FLAME-05'
        with self.assertRaises(CommandError): validate_registry(assets)

    def test_historical_station_evidence_is_not_rewritten_by_new_presentation(self):
        b = BASE_INVENTORY['bindings'][0]
        cards = location_cards([{'id':'E1','tool':'station_snapshot','status':'ok','data':{'items':[
            {**b,'registry_present':True,'mapping_status':'active_model_node_verified'}]}}])
        self.assertEqual(cards[0]['stationId'], b['stationId'])
