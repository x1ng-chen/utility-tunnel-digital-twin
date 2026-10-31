"""Software bootstrap contracts use a marked synthetic GLB, never paid models."""
import hashlib
import json
from pathlib import Path
import struct
import tempfile
from unittest.mock import patch
from django.conf import settings
from django.contrib.auth.models import User
from django.core.management.base import CommandError
from django.test import TestCase, SimpleTestCase, override_settings
from django.utils import timezone
from rest_framework.response import Response
from rest_framework.test import APIClient
from .agent_model_release import install_v24_demo_model, sandbox_root, v24_model_file
from .models import Asset, HardwareBinding, Profile, Telemetry, TwinModelRelease
from .sprint_models import AgentRun, DemoSession, InvestigationCase
from .twin_presentation import BASE_INVENTORY, V24, runtime_inventory


class SoftwareModelRootTests(SimpleTestCase):
    @override_settings(HARDWARE_LIVE_MODE=False)
    def test_only_named_sandboxes_after_exact_database_guard(self):
        for name in ('.agent-demo', '.agent-capabilities', '.agent-eval', '.agent-eval-sprint', '.agent-eval-guards'):
            with self.subTest(name=name), patch('operations.agent_model_release.require_evaluation_database', return_value=Path('/tmp')/name):
                self.assertEqual(sandbox_root().name, name)
        for name in ('.hardware-live', 'business', '.agent-capabilities-other'):
            with self.subTest(name=name), patch('operations.agent_model_release.require_evaluation_database', return_value=Path('/tmp')/name):
                with self.assertRaises(CommandError): sandbox_root()

    @override_settings(HARDWARE_LIVE_MODE=True)
    def test_hardware_profile_cannot_bypass_named_sandbox_rule(self):
        with patch('operations.agent_model_release.require_evaluation_database', return_value=Path('/tmp/.agent-capabilities')):
            with self.assertRaises(CommandError): sandbox_root()


@override_settings(ALLOWED_HOSTS=['127.0.0.1', 'testserver'])
class SoftwareModelBootstrapTests(TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.media = override_settings(MEDIA_ROOT=self.root/'media'); self.media.enable(); self.addCleanup(self.media.disable)
        self.admin = User.objects.create_user('agent-eval-administrator')
        Profile.objects.create(user=self.admin, role='administrator')
        self.operator = User.objects.create_user('agent-eval-operator')
        Profile.objects.create(user=self.operator, role='operator')
        for b in BASE_INVENTORY['bindings']:
            a = Asset.objects.create(code=b['assetCode'], name=b['physicalTag'], zone=b['stationId'],
                mesh=b['targetNode'], asset_type='sensor')
            HardwareBinding.objects.create(asset=a, protocol='manual', device_identifier='sim:'+a.code,
                endpoint='SIMULATED_TEST:'+b['controllerId'])
        for code, mesh in BASE_INVENTORY['controllerLegacyMeshes'].items():
            Asset.objects.create(code=code, name=code, mesh=mesh, asset_type='controller')
        for code in ('FAN-01', 'FAN-02'):
            Asset.objects.create(code=code, name=code, mesh=code, asset_type='fan')
        names = set(V24['sensorMeshes'].values()) | set(V24['controllerMeshes'].values()) | {'FAN-01', 'FAN-02'}
        scene = json.dumps({'asset':{'version':'2.0','generator':'EXPLICIT_UNIT_TEST_FIXTURE_NOT_REAL_V24'},
            'nodes':[{'name':n} for n in sorted(names)]}, separators=(',',':')).encode()
        scene += b' '*(-len(scene)%4)
        chunk = struct.pack('<I4s',len(scene),b'JSON')+scene
        self.data = struct.pack('<4sII',b'glTF',2,12+len(chunk))+chunk
        self.file = self.root/'synthetic-v24-contract.glb'; self.file.write_bytes(self.data)
        self.hash_patch = patch.dict(V24, {'modelSha256':hashlib.sha256(self.data).hexdigest()})
        self.hash_patch.start(); self.addCleanup(self.hash_patch.stop)
        for target, value in (('sandbox_root',self.root), ('data_context',{'mode':'simulated_test','scenarioId':'INS-01'})):
            module = 'operations.agent_model_release' if target=='sandbox_root' else 'operations.agent_context'
            p = patch(module+'.'+target, return_value=value); p.start(); self.addCleanup(p.stop)

    def install(self):
        return install_v24_demo_model(self.admin, self.file)

    def test_cyclic_upgrade_preserves_wire_owners_and_produces_all_31_unique_targets(self):
        ids = list(Asset.objects.order_by('id').values_list('id','code'))
        bindings = list(HardwareBinding.objects.order_by('id').values())
        result = self.install()
        inventory = runtime_inventory()
        self.assertEqual(result['presentationRevision'], V24['revision'])
        self.assertEqual(len({b['targetNode'] for b in inventory['bindings']}),31)
        self.assertEqual(Asset.objects.get(code='FLAME-02').mesh,'FLAME-02')
        self.assertEqual(Asset.objects.get(code='GAS-O2-02').mesh,'GAS-O2-05')
        self.assertEqual(list(Asset.objects.order_by('id').values_list('id','code')),ids)
        self.assertEqual(list(HardwareBinding.objects.order_by('id').values()),bindings)
        for code in V24['controllerMeshes']:
            self.assertEqual(Asset.objects.get(code=code).mesh,code)

    def test_existing_task_case_and_observation_history_survive_upgrade(self):
        case = InvestigationCase.objects.create(owner=self.operator, title='旧调查',station_id='P5',
            source={'mode':'simulated_test'},layout_version='old-layout',presentation_version='old-presentation',
            state={'hypotheses':[{'label':'旧候选，不是新事实'}]})
        run = AgentRun.objects.create(owner=self.operator,request_key='old-completed',case=case,status='completed',
            snapshot={'sha256':'preserve-old','presentationVersion':'old-presentation'},result={'summary':'旧判断'})
        row = Telemetry.objects.create(asset=Asset.objects.get(code='FLAME-05'),metric='flame.alarm',metric_key='flame.alarm',
            value=1,unit='bool',event_id='simulation:preserve',recorded_at=timezone.now())
        self.install(); run.refresh_from_db(); case.refresh_from_db(); row.refresh_from_db()
        self.assertEqual(run.snapshot['sha256'],'preserve-old')
        self.assertEqual(case.presentation_version,'old-presentation')
        self.assertEqual(row.value,1)

    def test_repeat_install_is_idempotent_without_version_or_timestamp_churn(self):
        self.install()
        state = list(Asset.objects.order_by('id').values())
        release = list(TwinModelRelease.objects.values())
        self.assertEqual(self.install()['changedAssets'],0)
        self.assertEqual(list(Asset.objects.order_by('id').values()),state)
        self.assertEqual(list(TwinModelRelease.objects.values()),release)

    def test_missing_or_pointer_model_fails_before_mappings_change(self):
        before=list(Asset.objects.order_by('id').values())
        pointer=self.root/'pointer.glb';pointer.write_text('version https://git-lfs.github.com/spec/v1\n')
        for path in (pointer,self.root/'absent.glb'):
            with self.subTest(path=path),self.assertRaises(CommandError): install_v24_demo_model(self.admin,path)
        self.assertEqual(list(Asset.objects.order_by('id').values()),before)
        self.assertFalse(TwinModelRelease.objects.exists())

    def test_unknown_mapping_is_not_silently_rewritten(self):
        Asset.objects.filter(code='FLAME-05').update(mesh='MANUAL_UNKNOWN_TARGET')
        with self.assertRaises(CommandError): self.install()
        self.assertEqual(Asset.objects.get(code='FLAME-05').mesh,'MANUAL_UNKNOWN_TARGET')

    def test_activation_failure_rolls_back_identity_and_removes_new_orphan_file(self):
        before=list(Asset.objects.order_by('id').values()); original=APIClient.post
        def reject_activate(client,path,*args,**kwargs):
            return Response(status=409) if path.endswith('/activate/') else original(client,path,*args,**kwargs)
        with patch.object(APIClient,'post',new=reject_activate),self.assertRaises(CommandError): self.install()
        self.assertEqual(list(Asset.objects.order_by('id').values()),before)
        self.assertFalse(TwinModelRelease.objects.exists())
        self.assertFalse(any((self.root/'media').rglob('*.glb')))

    def test_existing_v24_storage_corruption_fails_without_remapping(self):
        self.install(); release=TwinModelRelease.objects.get()
        Path(release.model_file.path).write_bytes(b'corrupt')
        before=list(Asset.objects.order_by('id').values())
        with self.assertRaises(CommandError): self.install()
        self.assertEqual(list(Asset.objects.order_by('id').values()),before)

    def test_active_task_blocks_version_upgrade(self):
        AgentRun.objects.create(owner=self.operator,request_key='queued',status='queued',snapshot={'old':True})
        with self.assertRaises(CommandError): self.install()
        self.assertFalse(TwinModelRelease.objects.exists())

    def test_demo_initialize_upgrades_existing_database_without_flush(self):
        from .sprint_demo import initialize
        run=AgentRun.objects.create(owner=self.operator,request_key='keep',status='completed',snapshot={'old':True})
        original=v24_model_file
        with patch('operations.sprint_demo.guard'),patch('operations.agent_model_release.v24_model_file',
                side_effect=lambda model_file=None: original(self.file)):
            initialize(with_model=True)
        self.assertTrue(AgentRun.objects.filter(pk=run.pk,snapshot={'old':True}).exists())
        self.assertEqual(runtime_inventory()['presentationRevision'],V24['revision'])

    def test_demo_reset_restores_v24_targets_and_keeps_prior_runs(self):
        from .sprint_demo import control
        self.install(); DemoSession.objects.create()
        run=AgentRun.objects.create(owner=self.operator,request_key='keep-reset',status='completed',snapshot={'old':True})
        with patch('operations.sprint_demo.guard'):
            control('reset','INS-04')
            self.assertEqual(Asset.objects.get(code='MQ4-05').mesh,'')
            control('reset','INS-01')
        self.assertEqual(Asset.objects.get(code='MQ4-05').mesh,V24['sensorMeshes']['MQ4-05'])
        self.assertEqual(Asset.objects.get(code='FLAME-02').mesh,'FLAME-02')
        self.assertTrue(AgentRun.objects.filter(pk=run.pk).exists())

    def test_default_scenario_installer_uses_v24_not_legacy_v17(self):
        from .agent_scenarios import install_model
        with patch('operations.agent_model_release.install_v24_demo_model',return_value={'explicit':'V24'}) as current:
            self.assertEqual(install_model(self.admin),{'explicit':'V24'})
            current.assert_called_once_with(self.admin)

    def test_seed_model_preflight_occurs_before_reset_flush(self):
        from .agent_scenarios import seed_scenario
        with patch('operations.agent_scenarios.require_evaluation_database',return_value=self.root),\
             patch('operations.agent_model_release.v24_model_file',side_effect=CommandError('pointer')),\
             patch('operations.agent_scenarios.call_command') as command:
            with self.assertRaises(CommandError): seed_scenario('INS-01',reset=True,with_model=True)
            command.assert_not_called()
