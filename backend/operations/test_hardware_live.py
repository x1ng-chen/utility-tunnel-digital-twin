import json
import tempfile
from copy import deepcopy
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch
from django.contrib.auth.models import User
from django.core.management import call_command, CommandError
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient
from operations.models import Asset, HardwareBinding, Profile, Telemetry


@override_settings(HARDWARE_LIVE_MODE=True, CONTROLLER_COMMAND_PROTOCOL='four-controller-v2')
class HardwareLiveTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('operator', password='test-only-password')
        Profile.objects.create(user=self.user, role='operator')
        self.client = APIClient(); self.client.force_authenticate(self.user)
        self.ingest = User.objects.create_user('hardware-ingest')
        Profile.objects.create(user=self.ingest, role='ingest')
        self.ingest_client = APIClient(); self.ingest_client.force_authenticate(self.ingest)
        self.asset = Asset.objects.create(code='MQ4-05', name='P5', zone='P5', asset_type='sensor', status='unknown')
        self.binding = HardwareBinding.objects.create(asset=self.asset, protocol='mqtt', device_identifier='test-p5',
            endpoint='ut/v1/CTRL-01/telemetry', expected_interval_seconds=2, status='reserved')
        at = timezone.now()-timedelta(milliseconds=200)
        self.row = {'eventId': 'gw:CTRL-01:test:0', 'assetCode': 'MQ4-05', 'metricKey': 'methane.raw',
            'metric': '甲烷原始ADC', 'value': 321, 'unit': 'adc', 'quality': 'good',
            'recordedAt': (at-timedelta(milliseconds=100)).isoformat(), 'provenance': {
                'source': 'four-controller-rtu-v2', 'controllerId': 'CTRL-01', 'frameId': 'boot:1:2:3',
                'layoutVersion': 'four-controller-20261026.1', 'rawOnly': True, 'clockSource': 'gateway-ntp',
                'sampleAgeMs': 100, 'frameTimestamp': at.isoformat(), 'seq': 3}}

    def post(self, row=None):
        return self.ingest_client.post('/api/telemetry/', {'readings': [row or self.row]}, format='json')

    def test_real_metadata_roundtrip_and_redelivery_deduplication(self):
        self.assertEqual(self.post().status_code, 201)
        self.assertEqual(self.post().json()['duplicates'], 1)
        self.assertEqual(Telemetry.objects.count(), 1)
        self.assertEqual(self.client.get('/api/telemetry/').json()['items'][0]['provenance'], self.row['provenance'])
        self.binding.refresh_from_db(); self.assertEqual(self.binding.status, 'connected')

    def test_owner_layout_time_and_unknown_fields_rejected_without_heartbeat(self):
        for key, value in [('controllerId', 'CTRL-02'), ('layoutVersion', 'old'),
                ('frameTimestamp', timezone.now().isoformat()), ('sampleAgeMs', True),
                ('frameId', []), ('rawOnly', False), ('extra', 'private text')]:
            row = deepcopy(self.row); row['provenance'][key] = value
            self.assertEqual(self.post(row).status_code, 400, key)
        self.binding.refresh_from_db()
        self.assertEqual(self.binding.status, 'reserved'); self.assertEqual(Telemetry.objects.count(), 0)

    def test_simulation_and_legacy_payload_do_not_enter_hardware_db(self):
        row = deepcopy(self.row); del row['provenance']
        self.assertEqual(self.post(row).status_code, 400)
        row = deepcopy(self.row); row['provenance']['source'] = 'SIMULATED_TEST'
        self.assertEqual(self.post(row).status_code, 400)

    def test_changed_provenance_is_idempotency_conflict(self):
        self.post()
        row = deepcopy(self.row); row['provenance']['seq'] = 4
        self.assertEqual(self.post(row).status_code, 409)

    def test_missing_zero_does_not_renew_sensor_heartbeat(self):
        row = deepcopy(self.row); row.update(quality='missing', value=0)
        self.assertEqual(self.post(row).status_code, 201)
        self.binding.refresh_from_db(); self.assertIsNone(self.binding.last_heartbeat_at)
        self.assertEqual(Telemetry.objects.get().quality, 'missing')

    def test_saturation_unknown_clock_units_and_oxygen_not_good(self):
        for mutation in ('saturated', 'clock', 'unit', 'oxygen'):
            row = deepcopy(self.row)
            if mutation == 'saturated': row['value'] = 4095
            if mutation == 'clock': row['provenance']['clockSource'] = 'receiver-estimated'
            if mutation == 'unit': row['unit'] = 'ppm'
            if mutation == 'oxygen': row.update(assetCode='GAS-O2-02', metricKey='oxygen.raw')
            self.assertEqual(self.post(row).status_code, 400, mutation)
        row = deepcopy(self.row); row.update(value=4095, quality='suspect')
        self.assertEqual(self.post(row).status_code, 201)

    def test_expired_data_stays_stale_until_fresh_observation_returns(self):
        self.post()
        from operations.connectivity import reconcile_connectivity
        from operations.agent_operations import snapshots
        now = timezone.now()+timedelta(seconds=30)
        reconcile_connectivity(now=now)
        result = snapshots(['MQ4-05'], now=now)['MQ4-05']
        self.assertEqual(result['connection']['state'], 'offline')
        self.assertEqual(result['readings'][0]['freshness'], 'stale')
        self.assertFalse(result['readings'][0]['usable'])
        row = deepcopy(self.row); row['eventId'] += 'new'
        row['provenance']['frameId'] += 'new'
        self.assertEqual(self.post(row).status_code, 201)
        self.binding.refresh_from_db(); self.assertEqual(self.binding.status, 'connected')

    def test_controls_blocked_even_for_superuser_and_mock_publisher_never_called(self):
        self.user.is_superuser = True; self.user.save()
        with patch('operations.views.publish_controller_command') as publish:
            for path in ('confirmations/', ''):
                self.assertEqual(self.client.post(f'/api/controllers/CTRL-01/commands/{path}', {'action':'relay_on'}, format='json').status_code, 403)
            publish.assert_not_called()
        self.assertTrue(self.client.get('/api/controllers/command-capabilities/').json()['controlDisabled'])

    def test_seed_refuses_business_database(self):
        with self.assertRaises(CommandError): call_command('prepare_hardware_live')

    def test_context_cannot_enable_demo_or_paid_model(self):
        result = self.client.get('/api/assistant/context/').json()['dataContext']
        self.assertTrue(result['hardwareLive']); self.assertFalse(result['demoControlsAvailable'])

    def test_model_tasks_fail_clearly_without_entering_worker_queue(self):
        from operations.sprint_models import AgentRun
        response = self.client.post('/api/assistant/runs/', {'kind':'inspection', 'station_id':'all'}, format='json')
        self.assertEqual(response.status_code, 503)
        self.assertEqual(AgentRun.objects.count(), 0)

    def test_interactive_user_cannot_forge_hardware_observations(self):
        self.assertEqual(self.client.post('/api/telemetry/', {'readings':[self.row]}, format='json').status_code, 403)
        self.assertEqual(Telemetry.objects.count(), 0)

    def test_missing_placeholder_is_not_used_in_numeric_summary(self):
        self.post()
        row = deepcopy(self.row); row.update(eventId='missing:test', quality='missing', value=0)
        self.post(row)
        result = self.client.get('/api/telemetry/summary/', {'assetCode':'MQ4-05', 'metricKey':'methane.raw'}).json()
        self.assertEqual(result['sampleCount'], 2)
        self.assertEqual(result['average'], 321)
        self.assertEqual(result['minimum'], 321)

    def test_one_expired_controller_does_not_expire_other_controller(self):
        self.post()
        asset = Asset.objects.create(code='CTRL-02', name='CTRL-02', zone='控制器', asset_type='controller')
        HardwareBinding.objects.create(asset=asset, protocol='mqtt', device_identifier='test-ctrl02',
            endpoint='ut/v1/CTRL-02/telemetry', expected_interval_seconds=2, status='connected', last_heartbeat_at=timezone.now())
        HardwareBinding.objects.filter(pk=self.binding.pk).update(last_heartbeat_at=timezone.now()-timedelta(seconds=30))
        from operations.connectivity import reconcile_connectivity
        reconcile_connectivity()
        from operations.agent_operations import snapshots
        results = snapshots(['MQ4-05', 'CTRL-02'])
        self.assertEqual(results['MQ4-05']['connection']['state'], 'offline')
        self.assertEqual(results['CTRL-02']['connection']['state'], 'online')

    def test_smoke_alarm_targets_its_own_asset_and_requires_new_valid_zero_to_recover(self):
        self._assert_digital_alarm('MQ2-05', 'MQ2-04', 'smoke.alarm')

    def test_flame_alarm_targets_its_own_asset_and_requires_new_valid_zero_to_recover(self):
        self._assert_digital_alarm('FLAME-05', 'FLAME-04', 'flame.alarm')

    def _assert_digital_alarm(self, code, other_code, metric):
        from operations.models import Alert, Threshold, WorkOrder
        asset=Asset.objects.create(code=code,name='P5数字告警',zone='P5',mesh=code,asset_type='sensor')
        Asset.objects.create(code=other_code,name='另一站数字告警',zone='P2',mesh=other_code,asset_type='sensor')
        HardwareBinding.objects.create(asset=asset,protocol='mqtt',device_identifier='flame05',
            endpoint='ut/v1/CTRL-01/telemetry',expected_interval_seconds=2)
        Threshold.objects.create(key=metric,label='数字输入',warning=.5,alarm=1,unit='bool')
        def send(value, phase, quality='good', age=0):
            row=deepcopy(self.row)
            at=timezone.now()-timedelta(seconds=age)
            row.update(assetCode=code,metricKey=metric,metric='数字告警',unit='bool',
                value=value,quality=quality,eventId='flame:'+phase,recordedAt=(at-timedelta(milliseconds=100)).isoformat())
            row['provenance'].update(frameId='flame:'+phase,frameTimestamp=at.isoformat())
            self.assertEqual(self.post(row).status_code,201)
        send(0,'normal');self.assertFalse(Alert.objects.exists())
        send(1,'active')
        alert=Alert.objects.get(rule_key=metric)
        self.assertEqual((alert.asset.code,alert.status,alert.severity),(code,'open','critical'))
        self.assertFalse(Alert.objects.filter(asset__code=other_code).exists())
        send(0,'bad-zero',quality='bad');alert.refresh_from_db();self.assertEqual(alert.status,'open')
        send(0,'old-zero',age=60);alert.refresh_from_db();self.assertEqual(alert.status,'open')
        send(0,'fresh-zero');alert.refresh_from_db();self.assertEqual(alert.status,'resolved')
        self.assertEqual(WorkOrder.objects.count(),0)
