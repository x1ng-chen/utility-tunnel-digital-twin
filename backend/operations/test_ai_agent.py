import io
import json
from datetime import timedelta
from unittest.mock import MagicMock, patch

from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from .ai_assistant import _execute, _validate
from .models import Alert, Asset, AuditLog, HardwareBinding, Profile, Telemetry, WorkOrder


def tool_call(name, args, identifier='tool-1'):
    return {'id': identifier, 'type': 'function', 'function': {
        'name': name, 'arguments': json.dumps(args, ensure_ascii=False)}}


def upstream(message):
    response = MagicMock()
    response.__enter__.return_value = io.BytesIO(json.dumps({'choices': [{'message': message}]}).encode())
    return response


@override_settings(DEEPSEEK_API_KEY='fake-secret', DEEPSEEK_MODEL='deepseek-flash')
class AgentTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.user = User.objects.create_user(username='agent-test', password='test-password')
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {Token.objects.create(user=self.user).key}')
        self.asset = Asset.objects.create(code='CTRL-01', name='节点 A', zone='测试舱', asset_type='controller')
        self.now = timezone.now()
        self.binding = HardwareBinding.objects.create(asset=self.asset, protocol='mqtt', device_identifier='test-node',
            endpoint='ut/v1/CTRL-01/telemetry', expected_interval_seconds=10, status='connected',
            last_heartbeat_at=self.now)
        self.payload = {'messages': [{'role': 'user', 'content': '查询 CTRL-01 的当前数据'}], 'page': '运行总览'}
        self.context = {'can_write': True, 'snapshots': set(), 'orders_checked': set(), 'proposals': []}

    def reading(self, value=31, quality='good', unit='C', seconds=0, key='temperature', label='温度'):
        return Telemetry.objects.create(asset=self.asset, metric_key=key, metric=label, value=value, unit=unit,
            quality=quality, recorded_at=self.now - timedelta(seconds=seconds))

    @patch('operations.ai_assistant.urlopen')
    def test_tool_loop_returns_database_evidence_and_audit(self, mocked):
        self.reading(seconds=3600)
        self.reading(value=28)
        self.reading(value=65, key='humidity', label='湿度', unit='%')
        mocked.side_effect = [upstream({'tool_calls': [tool_call('asset_snapshot', {'asset_code': 'CTRL-01'})]}),
            upstream({'content': '[E1] 最新温度 28 C；当前节点仍需现场核查。'})]
        response = self.client.post('/api/assistant/chat/', self.payload, format='json')
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body['mode'], 'tool_verified')
        data = body['evidence'][0]['data']
        self.assertEqual(data['connection']['state'], 'online')
        self.assertEqual(data['metric_count'], 2)
        temp = next(r for r in data['readings'] if r['metric_key'] == 'temperature')
        self.assertEqual(temp['value'], 28)
        self.assertEqual(temp['freshness'], 'fresh')
        self.assertIn('ingested_at', temp)
        sent = json.loads(mocked.call_args.args[0].data)
        self.assertEqual(sent['messages'][-1]['role'], 'tool')
        self.assertNotIn('fake-secret', response.content.decode())
        log = AuditLog.objects.get(action='assistant.queried')
        self.assertEqual(log.detail['traces'][0]['tool'], 'asset_snapshot')
        self.assertNotIn('messages', log.detail)

    def test_stale_future_missing_and_unbound_data_are_explicit(self):
        self.binding.last_heartbeat_at = self.now - timedelta(hours=1)
        self.binding.save()
        self.reading(seconds=3600)
        snapshot = _execute('asset_snapshot', {'asset_code': 'CTRL-01'}, self.context)
        self.assertEqual(snapshot['connection']['state'], 'offline')
        self.assertEqual(snapshot['readings'][0]['freshness'], 'stale')
        self.reading(seconds=-60)
        self.assertEqual(_execute('asset_snapshot', {'asset_code': 'CTRL-01'}, self.context)['readings'][0]['freshness'], 'future_timestamp')
        self.binding.delete()
        snapshot = _execute('asset_snapshot', {'asset_code': 'CTRL-01'}, self.context)
        self.assertEqual(snapshot['connection']['state'], 'unbound')
        Telemetry.objects.all().delete()
        self.assertEqual(_execute('asset_snapshot', {'asset_code': 'CTRL-01'}, self.context)['readings'], [])

    def test_latest_metric_key_does_not_duplicate_changed_labels(self):
        self.reading(value=20, seconds=10, label='旧温度标签')
        self.reading(value=28, label='新温度标签')
        snapshot = _execute('asset_snapshot', {'asset_code': 'CTRL-01'}, self.context)
        self.assertEqual(snapshot['metric_count'], 1)
        self.assertEqual(snapshot['readings'][0]['value'], 28)

    def test_no_heartbeat_is_not_inferred_online_from_registered_status(self):
        self.binding.last_heartbeat_at = None
        self.binding.save()
        self.asset.status = 'normal'
        self.asset.save()
        snapshot = _execute('asset_snapshot', {'asset_code': 'CTRL-01'}, self.context)
        self.assertEqual(snapshot['connection']['state'], 'awaiting_data')

    def test_trend_separates_units_and_excludes_bad_quality_statistics(self):
        self.reading(value=10)
        self.reading(value=20)
        self.reading(value=1000, quality='bad')
        self.reading(value=68, unit='F')
        self.reading(value=999, seconds=-120)
        result = _execute('telemetry_trend', {'asset_code': 'CTRL-01', 'metric_key': 'temperature', 'minutes': 5}, self.context)
        self.assertEqual(result['total'], 4)
        good = next(g for g in result['groups'] if g['unit'] == 'C' and g['quality'] == 'good')
        bad = next(g for g in result['groups'] if g['quality'] == 'bad')
        self.assertEqual(good['average'], 15)
        self.assertIsNone(bad['average'])
        self.assertEqual(result['statistics_scope'], 'latest_sample_only')

    def test_tool_argument_validation_is_server_side(self):
        invalid = [('shell', {}), ('asset_snapshot', {'asset_code': '../../env'}),
            ('asset_snapshot', {'asset_code': 'CTRL-01', 'sql': 'DROP TABLE'}),
            ('asset_snapshot', {}), ('telemetry_trend', {'asset_code': 'CTRL-01', 'metric_key': 'x', 'minutes': True}),
            ('telemetry_trend', {'asset_code': 'CTRL-01', 'metric_key': 'x', 'minutes': 61}),
            ('lookup_runbook', {'topic': 'remote_url'}), ('runtime_overview', [])]
        for name, args in invalid:
            with self.subTest(name=name, args=args), self.assertRaises(ValueError):
                _validate(name, args)

    @patch('operations.ai_assistant.urlopen')
    def test_untrusted_unknown_tool_cannot_mutate_database(self, mocked):
        mocked.side_effect = [upstream({'tool_calls': [tool_call('execute_sql', {'sql': 'DELETE FROM operations_asset'})]}),
            upstream({'content': '该请求不被允许。'})]
        response = self.client.post('/api/assistant/chat/', self.payload, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['traces'][0]['status'], 'rejected')
        self.assertEqual(Asset.objects.count(), 1)
        self.assertEqual(response.json()['mode'], 'explanation_only')

    @patch('operations.ai_assistant.urlopen')
    def test_tool_budget_rejects_excess_batch(self, mocked):
        mocked.return_value = upstream({'tool_calls': [tool_call('runtime_overview', {}, str(i)) for i in range(7)]})
        response = self.client.post('/api/assistant/chat/', self.payload, format='json')
        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.json()['error'], 'assistant_budget_exceeded')

    @patch('operations.ai_assistant.urlopen')
    def test_duplicate_tool_ids_are_rejected(self, mocked):
        mocked.return_value = upstream({'tool_calls': [tool_call('runtime_overview', {}), tool_call('open_alerts', {})]})
        response = self.client.post('/api/assistant/chat/', self.payload, format='json')
        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.json()['error'], 'assistant_invalid_response')

    @patch('operations.ai_assistant.urlopen')
    def test_ingest_principal_cannot_query_agent(self, mocked):
        profile, _ = Profile.objects.get_or_create(user=self.user)
        profile.role = 'ingest'
        profile.save()
        self.assertEqual(self.client.post('/api/assistant/chat/', self.payload, format='json').status_code, 403)
        mocked.assert_not_called()

    def test_draft_requires_role_and_asset_evidence_and_never_writes(self):
        args = {'asset_code': 'CTRL-01', 'title': '检查节点通信', 'description': '人工核查电源与链路', 'priority': 'high'}
        with self.assertRaises(ValueError):
            _execute('draft_work_order', args, self.context)
        _execute('asset_snapshot', {'asset_code': 'CTRL-01'}, self.context)
        _execute('active_work_orders', {'asset_code': 'CTRL-01'}, self.context)
        self.context['can_write'] = False
        with self.assertRaises(ValueError):
            _execute('draft_work_order', args, self.context)
        self.context['can_write'] = True
        result = _execute('draft_work_order', args, self.context)
        self.assertEqual(result['state'], 'draft_only_not_created')
        self.assertEqual(WorkOrder.objects.count(), 0)
        self.assertEqual(Alert.objects.count(), 0)
        self.assertEqual(len(self.context['proposals']), 1)

    @patch('operations.ai_assistant.urlopen')
    def test_operator_workflow_returns_confirmable_proposal_without_write(self, mocked):
        profile, _ = Profile.objects.get_or_create(user=self.user)
        profile.role = 'operator'
        profile.save()
        mocked.side_effect = [upstream({'tool_calls': [
            tool_call('asset_snapshot', {'asset_code': 'CTRL-01'}, 'snapshot'),
            tool_call('active_work_orders', {'asset_code': 'CTRL-01'}, 'orders')]}),
            upstream({'tool_calls': [tool_call('draft_work_order', {'asset_code': 'CTRL-01', 'title': '节点巡检',
                'description': '请人工核查数据未上报原因', 'priority': 'normal'}, 'draft')]}),
            upstream({'content': '[E1] 未查到测量。已生成草案，等待人工确认，并未创建工单。'})]
        response = self.client.post('/api/assistant/chat/', self.payload, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['proposals'][0]['requires_confirmation'], True)
        self.assertEqual(WorkOrder.objects.count(), 0)

    @patch('operations.ai_assistant.urlopen')
    def test_upstream_timeout_does_not_claim_completion(self, mocked):
        mocked.side_effect = TimeoutError()
        response = self.client.post('/api/assistant/chat/', self.payload, format='json')
        self.assertEqual(response.status_code, 504)
        self.assertNotIn('reply', response.json())
        self.assertEqual(WorkOrder.objects.count(), 0)
