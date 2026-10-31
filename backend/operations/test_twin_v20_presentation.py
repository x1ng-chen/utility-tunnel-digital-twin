from copy import deepcopy
from django.contrib.auth.models import User
from django.test import TestCase
from rest_framework.test import APIClient
from operations.agent_operations import location_cards, station_snapshot
from operations.models import Asset, HardwareBinding, Profile, TwinModelRelease
from operations.twin_presentation import BASE_INVENTORY, V20, runtime_inventory


class V20PresentationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('v20-operator')
        Profile.objects.create(user=self.user, role='operator')
        self.client = APIClient(); self.client.force_authenticate(self.user)
        for b in BASE_INVENTORY['bindings']:
            a = Asset.objects.create(code=b['assetCode'], name=b['physicalTag'], zone=V20['sensorStations'][b['assetCode']],
                mesh=b['targetNode'], asset_type='sensor', status='unknown')
            HardwareBinding.objects.create(asset=a, protocol='mqtt', device_identifier='test:'+a.code,
                endpoint=f'ut/v1/{b["controllerId"]}/telemetry')
        for code in V20['controllerMeshes']:
            Asset.objects.create(code=code, name=code, zone='控制器', mesh=code, asset_type='controller')
        self.release = TwinModelRelease.objects.create(version='v20-test', model_file='unused.glb',
            original_name='model.glb', sha256=V20['modelSha256'], size_bytes=100, node_count=693,
            node_inventory_available=True, node_names=list(Asset.objects.values_list('mesh', flat=True)),
            status='active', uploaded_by=self.user, is_compatible=True)

    def test_station_renumbering_preserves_all_sensor_identities_and_wire_owners(self):
        inventory = runtime_inventory()
        self.assertEqual(inventory['revision'], BASE_INVENTORY['revision'])
        self.assertEqual({b['assetCode']:b['controllerId'] for b in inventory['bindings']},
            {b['assetCode']:b['controllerId'] for b in BASE_INVENTORY['bindings']})
        report = station_snapshot('P1')
        self.assertEqual({i['assetCode'] for i in report['items']},
            {'MQ2-02','MQ4-02','CO-02','FLAME-02','ENV-02','LEVEL-L02'})
        self.assertEqual(report['controller_allocation'], {'CTRL-03':6})
        self.assertEqual(report['presentation_revision'], V20['revision'])
        self.assertEqual(station_snapshot('P3')['controller_allocation'], {'CTRL-04':7})
        self.assertEqual(station_snapshot('P5')['controller_allocation'], {'CTRL-01':5})

    def test_canonical_controller_meshes_and_current_context(self):
        self.assertEqual(runtime_inventory()['controllerLegacyMeshes'], V20['controllerMeshes'])
        response = self.client.get('/api/twin/model-readiness/').json()
        self.assertEqual(response['presentation']['revision'], V20['revision'])
        self.assertEqual(response['status'], 'ready')
        context = self.client.get('/api/assistant/context/').json()
        self.assertEqual(context['layoutVersion'], BASE_INVENTORY['revision'])
        self.assertEqual(context['modelNotice'], V20['notice'])

    def test_a_version_string_without_the_correct_model_hash_cannot_enable_adapter(self):
        self.release.sha256='0'*64; self.release.version=V20['modelVersion']
        self.release.save(update_fields=['sha256','version'])
        self.assertNotIn('presentation', runtime_inventory())
        self.assertEqual(runtime_inventory()['bindings'], BASE_INVENTORY['bindings'])

    def test_runtime_overlay_does_not_mutate_the_frozen_inventory(self):
        old = deepcopy(BASE_INVENTORY)
        changed = runtime_inventory(); changed['bindings'][0]['stationId']='P5'
        self.assertEqual(BASE_INVENTORY, old)
        self.assertEqual(runtime_inventory()['bindings'][0]['stationId'], 'P3')

    def test_historical_evidence_keeps_its_original_station_number(self):
        binding = BASE_INVENTORY['bindings'][0]
        evidence=[{'id':'E1','tool':'station_snapshot','status':'ok','data':{'items':[
            {**binding,'registry_present':True,'mapping_status':'active_model_node_verified'}]}}]
        self.assertEqual(location_cards(evidence)[0]['stationId'], 'P1')
        new = location_cards([{'id':'E2','tool':'asset_snapshot','status':'ok','data':{'asset_code':binding['assetCode']}}])[0]
        self.assertEqual(new['stationId'], 'P3')
        self.assertEqual(new['controllerId'], 'CTRL-04')

    def test_experience_scope_includes_presentation_version_without_rewriting_wire_layout(self):
        from operations.agent_experience import experience_layout_version, station_for
        old = {'layoutVersion':BASE_INVENTORY['revision']}
        new = {**old,'inventory':runtime_inventory()}
        self.assertNotEqual(experience_layout_version(old), experience_layout_version(new))
        self.assertEqual(station_for({},'SMOKE-01',new['inventory']), 'P3')
        self.assertEqual(old['layoutVersion'], new['layoutVersion'])
