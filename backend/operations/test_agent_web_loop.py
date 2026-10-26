import io
import json
from collections import Counter
from datetime import timedelta
from unittest.mock import patch
from django.contrib.auth.models import User
from django.core.management import CommandError, call_command
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient
from .agent_operations import BINDINGS, INVENTORY, SENSOR_METRICS, station_snapshot, diagnose_station
from .agent_context import require_evaluation_database
from .models import Asset, HardwareBinding, Telemetry, Profile, Alert
from .test_ai_agent import upstream, tool_call


class AgentWebLoopTests(TestCase):
    def setUp(self):
        self.now = timezone.now()
        self.user = User.objects.create_user(username='web-agent-operator')
        Profile.objects.update_or_create(user=self.user, defaults={'role': 'operator'})
        self.client = APIClient(); self.client.force_authenticate(self.user)
        units = {'temperature': 'C', 'humidity': '%', 'smoke.alarm': 'bool', 'flame.alarm': 'bool', 'level.detected': 'bool'}
        for b in BINDINGS:
            a = Asset.objects.create(code=b['assetCode'], name=b['physicalTag'], zone=b['stationId'], asset_type='sensor', mesh=b['targetNode'])
            HardwareBinding.objects.create(asset=a, protocol='manual', device_identifier=a.code, endpoint='simulation',
                status='connected', expected_interval_seconds=60, last_heartbeat_at=self.now)
            for group in SENSOR_METRICS[b['physicalTag'].split('-')[0]]:
                key = group[0]
                Telemetry.objects.create(asset=a, event_id=f'simulation:{a.code}:{key}', metric_key=key, metric=key,
                    value=0, unit=units.get(key, 'adc'), recorded_at=self.now)

    def post(self):
        return self.client.post('/api/assistant/chat/', {'messages': [{'role': 'user', 'content': '巡检P5'}]}, format='json')

    def test_latest_layout_is_31_unique_and_controller_ownership_matches_wiring(self):
        self.assertEqual(Counter(b['controllerId'] for b in BINDINGS), {'CTRL-01': 11, 'CTRL-02': 7, 'CTRL-03': 6, 'CTRL-04': 7})
        self.assertEqual(len({b['assetCode'] for b in BINDINGS}), 31)
        self.assertEqual({b['controllerId'] for b in BINDINGS if b['stationId'] == 'P5'}, {'CTRL-01'})
        self.assertEqual(INVENTORY['fanControllers'], {'FAN-01': 'CTRL-04', 'FAN-02': 'CTRL-02'})

    def test_simulation_is_unusable_in_production_logic(self):
        report = station_snapshot()
        self.assertEqual(report['usable_observation_sensor_count'], 0)
        self.assertEqual(report['scenario_usable_sensor_count'], 0)

    @override_settings(AGENT_EVALUATION_MODE=True)
    def test_scenario_count_does_not_inflate_live_count_and_respects_quality(self):
        report = station_snapshot()
        self.assertEqual(report['usable_observation_sensor_count'], 0)
        self.assertEqual(report['scenario_usable_sensor_count'], 31)
        Telemetry.objects.filter(asset__code='MQ4-05').update(quality='bad')
        Telemetry.objects.filter(asset__code='CO-05').update(recorded_at=self.now + timedelta(minutes=1))
        report = station_snapshot()
        self.assertEqual(report['scenario_usable_sensor_count'], 29)
        self.assertEqual(report['usable_observation_sensor_count'], 0)

    def test_reset_refuses_existing_business_database(self):
        before = Asset.objects.count()
        with self.assertRaises(CommandError):
            call_command('seed_agent_eval', reset=True)
        self.assertEqual(Asset.objects.count(), before)
        with self.assertRaises(CommandError):
            require_evaluation_database()

    @override_settings(AGENT_EVALUATION_MODE=True)
    def test_context_and_inspection_expose_source_and_legacy_model_notice(self):
        context = self.client.get('/api/assistant/context/').json()
        self.assertEqual(context['dataContext']['mode'], 'simulated_test')
        self.assertIn('旧编号', context['modelNotice'])
        body = self.client.get('/api/assistant/inspection/').json()
        self.assertIn('模拟测试', body['reply'])
        self.assertEqual(body['inspection']['scenarioUsable'], 31)

    @override_settings(AGENT_EVALUATION_MODE=True)
    @patch('operations.views.publish_controller_command')
    def test_sandbox_blocks_hardware_even_for_authenticated_operator(self, publish):
        response = self.client.post('/api/controllers/CTRL-01/commands/', {'action': 'relay_on'}, format='json')
        self.assertEqual(response.status_code, 403)
        publish.assert_not_called()

    @override_settings(DEEPSEEK_API_KEY='mock', AGENT_EVALUATION_MODE=True)
    @patch('operations.ai_assistant.urlopen')
    def test_missing_usage_is_unknown_and_citations_are_checked(self, mocked):
        mocked.side_effect = [upstream({'tool_calls': [tool_call('station_snapshot', {'station_id': 'P5'})]}),
            upstream({'content': '[E99] 所有设备正常'})]
        response = self.post()
        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.data['error'], 'assistant_invalid_citation')
        self.assertIsNone(response.data['details']['runtime']['tokens'])

    @override_settings(DEEPSEEK_API_KEY='mock')
    @patch('operations.ai_assistant.urlopen')
    def test_provider_usage_and_actual_model_are_recorded(self, mocked):
        from unittest.mock import MagicMock
        response = MagicMock()
        response.__enter__.return_value = io.BytesIO(json.dumps({'model': 'provider-actual-model',
            'usage': {'prompt_tokens': 20, 'completion_tokens': 10, 'total_tokens': 30},
            'choices': [{'message': {'content': '仅说明页面用法，未查询现场。'}, 'finish_reason': 'stop'}]}).encode())
        mocked.return_value = response
        body = self.post().json()
        self.assertEqual(body['runtime']['providerModels'], ['provider-actual-model'])
        self.assertEqual(body['runtime']['tokens']['total_tokens'], 30)
        self.assertIn('requestId', body['runtime'])

    @override_settings(DEEPSEEK_API_KEY='mock')
    @patch('operations.ai_assistant.urlopen')
    def test_truncated_provider_reply_is_not_reported_as_success(self, mocked):
        from unittest.mock import MagicMock
        response = MagicMock()
        response.__enter__.return_value = io.BytesIO(json.dumps({'choices': [{'message': {'content': 'partial'}, 'finish_reason': 'length'}]}).encode())
        mocked.return_value = response
        self.assertEqual(self.post().data['error'], 'assistant_truncated_response')

    @override_settings(AGENT_EVALUATION_MODE=True)
    def test_four_diagnosis_variants_keep_hypotheses_and_evidence_gaps(self):
        fan = Asset.objects.create(code='FAN-01', name='模拟风机', zone='P1', asset_type='fan')
        HardwareBinding.objects.create(asset=fan, protocol='manual', device_identifier='sim:fan', endpoint='simulation',
            status='connected', last_heartbeat_at=self.now, expected_interval_seconds=60)
        Telemetry.objects.create(asset=fan, event_id='simulation:power', metric_key='supply.voltage', metric='voltage', value=0, unit='V', recorded_at=self.now)
        Telemetry.objects.create(asset=fan, event_id='simulation:current', metric_key='motor.current', metric='current', value=300, unit='mA', recorded_at=self.now)
        Alert.objects.create(code='SIM-TEST-ALERT', asset=Asset.objects.get(code='MQ4-05'), title='模拟单点告警', detail='模拟', severity='warning', category='test', opened_at=self.now)
        HardwareBinding.objects.filter(asset__code='MQ4-02').update(last_heartbeat_at=self.now-timedelta(hours=1))
        result = diagnose_station('P5')['diagnosis']
        codes = {c['code'] for c in result['candidates']}
        self.assertTrue({'power_evidence_abnormal', 'tach_feedback_missing', 'single_sensor_anomaly', 'neighbor_evidence_incomplete'} <= codes)
        self.assertEqual(result['state'], 'hypotheses_only')
        for c in result['candidates']:
            self.assertIn('nextCheck', c); self.assertIn('counterevidence', c)
        self.assertAlmostEqual(result['facts'][0]['currentA'], .3)

    def test_inventory_source_hash_and_station_controller_mapping_are_current(self):
        from pathlib import Path
        import hashlib
        path = Path(__file__).resolve().parents[2] / INVENTORY['layoutSource']
        layout = json.loads(path.read_text(encoding='utf-8'))
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), INVENTORY['layoutSourceSha256'])
        for b in BINDINGS:
            self.assertEqual(b['controllerId'], layout['layout']['stations'][b['stationId']]['node'])

    def test_client_cannot_enable_evaluation_context(self):
        response = self.client.get('/api/assistant/context/?evaluation=true').json()
        self.assertEqual(response['dataContext']['mode'], 'database_observation')

    @override_settings(DEEPSEEK_API_KEY='mock')
    @patch('operations.ai_assistant.urlopen')
    def test_invalid_task_rejected_before_model_call(self, mocked):
        response = self.client.post('/api/assistant/chat/', {'messages': [{'role': 'user', 'content': '查设备'}],
            'task': {'kind': 'draft', 'asset_code': 'MQ4-05', 'eval': True}}, format='json')
        self.assertEqual(response.status_code, 400)
        mocked.assert_not_called()

    @override_settings(DEEPSEEK_API_KEY='mock')
    @patch('operations.ai_assistant.urlopen')
    def test_text_only_draft_cannot_pretend_to_complete_explicit_task(self, mocked):
        mocked.return_value = upstream({'content': '工单草案已准备，请确认。'})
        response = self.client.post('/api/assistant/chat/', {'messages': [{'role': 'user', 'content': '生成MQ4-05草案'}],
            'task': {'kind': 'draft', 'asset_code': 'MQ4-05'}}, format='json')
        self.assertEqual(response.data['error'], 'assistant_task_incomplete')

    @override_settings(DEEPSEEK_API_KEY='mock')
    @patch('operations.ai_assistant.urlopen')
    def test_wrong_station_cannot_complete_explicit_diagnosis(self, mocked):
        mocked.side_effect = [upstream({'tool_calls': [tool_call('diagnose_station', {'station_id': 'P1'})]}),
            upstream({'content': '已核查P5。'})]
        response = self.client.post('/api/assistant/chat/', {'messages': [{'role': 'user', 'content': '排查P5'}],
            'task': {'kind': 'diagnosis', 'station_id': 'P5'}}, format='json')
        self.assertEqual(response.data['error'], 'assistant_task_incomplete')

    @override_settings(DEEPSEEK_API_KEY='mock')
    @patch('operations.ai_assistant.urlopen')
    def test_viewer_draft_rejected_before_spending_model_tokens(self, mocked):
        self.user.profile.role = 'viewer'; self.user.profile.save()
        response = self.client.post('/api/assistant/chat/', {'messages': [{'role': 'user', 'content': '建草案'}],
            'task': {'kind': 'draft', 'asset_code': 'MQ4-05'}}, format='json')
        self.assertEqual(response.status_code, 403)
        mocked.assert_not_called()
