import json
from datetime import timedelta
from unittest.mock import patch
from io import StringIO
from tempfile import TemporaryDirectory
from pathlib import Path

from django.contrib.auth.models import User
from django.db import connection
from django.core.management import call_command, CommandError
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.test import APIClient

from .agent_operations import BINDINGS, SENSOR_METRICS, diagnose_station, location_cards, primary_trends, review_work_order, station_snapshot
from .agent_runbooks import RUNBOOKS
from .ai_assistant import _execute, _validate
from .models import Alert, Asset, HardwareBinding, Profile, Telemetry, TwinModelRelease, WorkOrder
from .test_ai_agent import tool_call, upstream


class StationAgentTests(TestCase):
    def setUp(self):
        self.now = timezone.now()
        self.assets = {}
        units = {'temperature': '°C', 'humidity': '%RH', 'smoke.alarm': 'bool',
            'flame.alarm': 'bool', 'level.detected': 'bool'}
        for b in BINDINGS:
            asset = Asset.objects.create(code=b['assetCode'], name=b['physicalTag'], zone=b['stationId'],
                asset_type='sensor', mesh=b['targetNode'])
            self.assets[asset.code] = asset
            HardwareBinding.objects.create(asset=asset, protocol='mqtt', device_identifier=asset.code,
                endpoint='test', status='connected', expected_interval_seconds=60, last_heartbeat_at=self.now)
            for group in SENSOR_METRICS[b['physicalTag'].split('-')[0]]:
                key = group[0]
                Telemetry.objects.create(asset=asset, metric_key=key, metric=key, value=0, unit=units.get(key, 'adc'), recorded_at=self.now)
        self.context = {'can_write': True, 'snapshots': set(), 'orders_checked': set(), 'proposals': []}

    def user(self, role='viewer'):
        user = User.objects.create_user(username=f'agent-{role}')
        Profile.objects.update_or_create(user=user, defaults={'role': role})
        return user

    def order(self, code='WO-TEST', asset_code='MQ4-05'):
        return WorkOrder.objects.create(code=code, asset=self.assets[asset_code], title='核查气体测点', created_by=self.user())

    def item(self, code, result=None):
        return next(i for i in (result or station_snapshot())['items'] if i['assetCode'] == code)

    def test_full_inventory_is_physical_sensor_count_not_metric_count(self):
        before = Telemetry.objects.count()
        result = station_snapshot()
        self.assertEqual(result['expected_sensor_count'], 31)
        self.assertEqual(result['registered_sensor_count'], 31)
        self.assertEqual(result['usable_observation_sensor_count'], 31)
        self.assertEqual(result['controller_allocation'], {'CTRL-01': 11, 'CTRL-02': 7, 'CTRL-03': 6, 'CTRL-04': 7})
        self.assertEqual(Telemetry.objects.count(), before)
        self.assertEqual(WorkOrder.objects.count(), 0)
        self.assertEqual(sum(len(i['snapshot']['readings']) for i in result['items']), 35)

    def test_sensor_registry_missing_is_not_auto_created_or_replaced_by_legacy_asset(self):
        self.assets['MQ4-05'].delete()
        Asset.objects.create(code='GAS-01', name='旧组合节点', zone='旧区', asset_type='sensor')
        result = station_snapshot()
        self.assertEqual(result['registered_sensor_count'], 30)
        self.assertEqual(self.item('MQ4-05', result)['mapping_status'], 'asset_missing')
        self.assertEqual(self.item('MQ4-05', result)['missing_metric_groups'], [['methane.raw']])
        self.assertFalse(Asset.objects.filter(code='MQ4-05').exists())

    def test_missing_second_temperature_humidity_metric_is_incomplete(self):
        Telemetry.objects.filter(asset=self.assets['ENV-01'], metric_key='humidity').delete()
        self.assertEqual(self.item('ENV-01')['missing_metric_groups'], [['humidity']])
        self.assertEqual(station_snapshot()['usable_observation_sensor_count'], 30)

    def test_heartbeat_only_never_counts_as_sensor_measurement(self):
        a = self.assets['MQ4-05']
        Telemetry.objects.filter(asset=a).update(metric_key='sample_period')
        self.assertEqual(self.item(a.code)['observation_state'], 'needs_verification')

    def test_stale_bad_future_and_demo_never_count_as_usable(self):
        changes = [('SMOKE-01', {'recorded_at': self.now-timedelta(hours=1)}),
            ('MQ4-02', {'quality': 'bad'}), ('CO-03', {'recorded_at': self.now+timedelta(minutes=1)}),
            ('FLAME-04', {'event_id': 'demo:flame'}), ('MQ4-05', {'ingested_at': self.now+timedelta(minutes=1)})]
        for code, fields in changes:
            Telemetry.objects.filter(asset=self.assets[code]).update(**fields)
        result = station_snapshot()
        self.assertEqual(result['usable_observation_sensor_count'], 26)
        for code, _ in changes:
            self.assertEqual(self.item(code, result)['observation_state'], 'needs_verification')

    def test_gateway_loss_does_not_hide_aging_data(self):
        HardwareBinding.objects.update(last_heartbeat_at=self.now-timedelta(hours=1))
        result = station_snapshot()
        self.assertEqual(result['usable_observation_sensor_count'], 0)
        self.assertTrue(all(i['snapshot']['connection']['state'] == 'offline' for i in result['items']))

    def test_fresh_but_wrong_unit_is_flagged(self):
        Telemetry.objects.filter(asset=self.assets['MQ4-05']).update(unit='ppm')
        self.assertEqual(self.item('MQ4-05')['unit_issues'], ['methane.raw'])
        self.assertEqual(self.item('MQ4-05')['observation_state'], 'needs_verification')

    def test_mapping_requires_exact_unique_node_in_active_release(self):
        self.assertEqual(self.item('MQ4-05')['mapping_status'], 'active_model_unverified')
        user = self.user()
        release = TwinModelRelease.objects.create(version='test-v17', model_file='test.glb', original_name='test.glb',
            sha256='0'*64, size_bytes=100, uploaded_by=user, status='active', node_inventory_available=True,
            node_names=[b['targetNode'] for b in BINDINGS])
        self.assertEqual(self.item('MQ4-05')['mapping_status'], 'active_model_node_verified')
        release.node_names += ['MQ4-05']; release.save()
        self.assertEqual(self.item('MQ4-05')['mapping_status'], 'node_missing_or_ambiguous')
        self.assets['MQ4-05'].mesh = ''; self.assets['MQ4-05'].save()
        self.assertEqual(self.item('MQ4-05')['mapping_status'], 'mesh_missing')

    def test_batch_queries_do_not_grow_per_sensor(self):
        with CaptureQueriesContext(connection) as queries:
            result = station_snapshot()
        self.assertEqual(len(result['items']), 31)
        self.assertLessEqual(len(queries), 7)

    def test_metric_limit_is_per_asset_and_truncation_never_means_complete(self):
        asset = self.assets['MQ4-05']
        Telemetry.objects.bulk_create([Telemetry(asset=asset, metric_key=f'a{i:02}', metric='extra', value=1,
            unit='adc', recorded_at=self.now) for i in range(25)])
        result = station_snapshot()
        item = self.item(asset.code, result)
        self.assertEqual(item['snapshot']['metric_count'], 26)
        self.assertEqual(len(item['snapshot']['readings']), 20)
        self.assertEqual(item['observation_state'], 'needs_verification')
        self.assertEqual(len(self.item('CO-05', result)['snapshot']['readings']), 1)

    def test_no_rpm_is_never_diagnosed_as_proven_motor_failure(self):
        result = diagnose_station('P5')
        self.assertEqual(len(result['station']['items']), 5)  # Four station members + contextual oxygen.
        self.assertEqual(result['fans'], {})
        self.assertTrue(any(c['candidate'] == '转速反馈缺失或不可用' for c in result['candidate_causes']))
        self.assertEqual(len(result['neighbor_latest_observations']), 20)

    def test_duplicate_order_and_duplicate_draft_are_rejected_server_side(self):
        args = {'asset_code': 'MQ4-05', 'title': '复核', 'description': '现场人工核验', 'priority': 'normal'}
        _execute('station_snapshot', {}, self.context)
        _execute('active_work_orders', {'asset_code': 'MQ4-05'}, self.context)
        _execute('draft_work_order', args, self.context)
        with self.assertRaisesMessage(ValueError, '已为该资产生成草案'):
            _execute('draft_work_order', args, self.context)
        self.context['proposals'] = []
        self.order()
        with self.assertRaisesMessage(ValueError, '已有未完成工单'):
            _execute('draft_work_order', args, self.context)
        self.assertEqual(WorkOrder.objects.count(), 1)

    def test_recovery_requires_new_measurements_and_never_closes(self):
        order = self.order()
        self.assertEqual(review_work_order(order.code)['measurement_review'], 'insufficient_new_evidence')
        now = timezone.now()
        Telemetry.objects.filter(asset=order.asset).update(recorded_at=now)
        result = review_work_order(order.code)
        self.assertEqual(result['measurement_review'], 'new_usable_observations')
        self.assertTrue(result['human_review_required'])
        self.assertFalse(result['work_order_changed'])
        order.refresh_from_db()
        self.assertEqual(order.status, 'open')

    def test_old_value_with_new_ingest_time_is_not_recovery(self):
        order = self.order()
        Telemetry.objects.filter(asset=order.asset).update(recorded_at=self.now-timedelta(days=1), ingested_at=timezone.now())
        self.assertEqual(review_work_order(order.code)['measurement_review'], 'insufficient_new_evidence')

    def test_location_cards_only_come_from_successful_recognized_evidence(self):
        result = station_snapshot('P5')
        evidence = [{'id': 'E1', 'tool': 'station_snapshot', 'status': 'ok', 'data': result}]
        cards = location_cards(evidence)
        self.assertEqual({c['assetCode'] for c in cards}, {'MQ2-05', 'MQ4-05', 'CO-05', 'FLAME-05', 'GAS-O2-02'})
        self.assertEqual(location_cards([{**evidence[0], 'status': 'rejected'}]), [])
        self.assertEqual(location_cards([{**evidence[0], 'tool': 'untrusted_user_text'}]), [])

    def test_runbooks_have_version_sources_and_current_architecture(self):
        for key, book in RUNBOOKS.items():
            self.assertTrue(book['version'])
            self.assertTrue(book['sources'])
            self.assertTrue(all(len(s['sha256']) == 64 for s in book['sources']))
        self.assertIn('RS-485', ''.join(RUNBOOKS['offline']['steps']))

    def test_trends_compare_same_sensor_and_units_and_exclude_demo_bad_future(self):
        asset = self.assets['MQ4-05']
        Telemetry.objects.filter(asset=asset).delete()
        fields = dict(asset=asset, metric_key='methane.raw', metric='甲烷原始量', unit='adc')
        Telemetry.objects.create(**fields, value=20, recorded_at=self.now-timedelta(seconds=20))
        Telemetry.objects.create(**fields, value=40, recorded_at=self.now-timedelta(seconds=10))
        Telemetry.objects.create(**fields, value=999, recorded_at=self.now, event_id='demo:ch4')
        Telemetry.objects.create(**fields, value=888, recorded_at=self.now, quality='bad')
        Telemetry.objects.create(**fields, value=777, recorded_at=self.now+timedelta(minutes=1))
        result = primary_trends([asset.code], timezone.now())['items'][0]
        self.assertEqual(result['count'], 2)
        self.assertEqual(result['delta'], 20)
        self.assertEqual(result['maximum'], 40)

    def test_controller_and_sensor_counts_are_separate(self):
        Asset.objects.create(code='CTRL-03', name='中部控制器', zone='P3', asset_type='controller')
        report = station_snapshot()
        self.assertEqual(report['registered_sensor_count'], 31)
        self.assertEqual(report['controllers']['CTRL-03']['connection']['state'], 'unbound')

    def test_inspection_command_is_read_only_and_does_not_overwrite_reports(self):
        with TemporaryDirectory() as directory:
            target = Path(directory)/'inspection.json'
            call_command('inspect_stations', station='P5', output=str(target), stdout=StringIO())
            self.assertEqual(json.loads(target.read_text(encoding='utf-8'))['expected_sensor_count'], 5)
            with self.assertRaises(CommandError):
                call_command('inspect_stations', station='P5', output=str(target), stdout=StringIO())
        self.assertEqual(Asset.objects.count(), 31)
        with self.assertRaises(CommandError):
            call_command('inspect_stations', strict=True, stdout=StringIO())

    def test_extreme_raw_delta_is_json_safe(self):
        asset = self.assets['MQ4-05']
        Telemetry.objects.filter(asset=asset).update(value=-1.7e308, recorded_at=self.now-timedelta(seconds=1))
        Telemetry.objects.create(asset=asset, metric_key='methane.raw', metric='raw', value=1.7e308, unit='adc', recorded_at=self.now)
        result = primary_trends([asset.code], timezone.now())
        self.assertIsNone(result['items'][0]['delta'])
        json.dumps(result, allow_nan=False)

    @override_settings(DEEPSEEK_API_KEY='')
    def test_direct_inspection_needs_login_but_no_llm_key_and_respects_roles(self):
        client = APIClient()
        self.assertEqual(client.get('/api/assistant/inspection/').status_code, 401)
        user = self.user()
        client.force_authenticate(user)
        response = client.get('/api/assistant/inspection/?station=P5')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['evidence'][0]['data']['expected_sensor_count'], 5)
        self.assertEqual(len(response.json()['locations']), 5)
        self.assertEqual(client.get('/api/assistant/inspection/?station=P6').status_code, 400)
        self.assertEqual(client.get('/api/assistant/inspection/?url=evil').status_code, 400)
        user.profile.role = 'ingest'; user.profile.save()
        self.assertEqual(client.get('/api/assistant/inspection/').status_code, 403)

    def test_schema_rejects_arbitrary_station_and_extra_fields(self):
        for name, args in [('station_snapshot', {'station_id': 'P6'}),
                ('diagnose_station', {'station_id': 'P5', 'url': 'evil'}),
                ('review_work_order', {'work_order_code': '../env'})]:
            with self.assertRaises(ValueError):
                _validate(name, args)

    @override_settings(DEEPSEEK_API_KEY='fake-key')
    @patch('operations.ai_assistant.urlopen')
    def test_model_inspection_includes_server_generated_location_cards(self, mocked):
        mocked.side_effect = [upstream({'tool_calls': [tool_call('station_snapshot', {'station_id': 'P5'})]}),
            upstream({'content': '[E1] P5观测与模型绑定仍需核查。'})]
        client = APIClient(); client.force_authenticate(self.user())
        response = client.post('/api/assistant/chat/', {'messages': [{'role': 'user', 'content': '巡检P5'}]}, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()['locations']), 5)
        self.assertEqual(WorkOrder.objects.count(), 0)

    @override_settings(DEEPSEEK_API_KEY='fake-key')
    @patch('operations.ai_assistant.urlopen')
    def test_sequential_inspection_diagnosis_runbook_and_order_proposal(self, mocked):
        draft = {'asset_code': 'MQ4-05', 'title': 'P5测点人工复核', 'description': '核查原始量、供电和采样链路', 'priority': 'high'}
        steps = [('station_snapshot', {}), ('diagnose_station', {'station_id': 'P5'}),
            ('lookup_runbook', {'topic': 'sensor'}), ('active_work_orders', {'asset_code': 'MQ4-05'}),
            ('draft_work_order', draft)]
        mocked.side_effect = [upstream({'tool_calls': [tool_call(name, args, f'step-{i}')]})
            for i, (name, args) in enumerate(steps)] + [upstream({'content': '[E1][E2][E3] 已准备草案，等待人工确认。'})]
        client = APIClient(); client.force_authenticate(self.user('operator'))
        result = client.post('/api/assistant/chat/', {'messages': [{'role': 'user', 'content': '巡检排障并准备工单'}]}, format='json')
        self.assertEqual(result.status_code, 200)
        body = result.json()
        self.assertEqual(len(body['traces']), 5)
        self.assertEqual(len(body['proposals']), 1)
        self.assertEqual(body['inspection']['expected'], 5)  # Latest, focused P5 evidence.
        self.assertEqual(WorkOrder.objects.count(), 0)
        payload = {'assetCode': draft['asset_code'], 'title': draft['title'], 'description': draft['description'], 'priority': 'high'}
        first = client.post('/api/work-orders/', payload, format='json', HTTP_IDEMPOTENCY_KEY='agent-fixture-confirm')
        second = client.post('/api/work-orders/', payload, format='json', HTTP_IDEMPOTENCY_KEY='agent-fixture-confirm')
        self.assertIn(first.status_code, (200, 201)); self.assertIn(second.status_code, (200, 201))
        self.assertEqual(WorkOrder.objects.count(), 1)
        self.assertEqual(first.json()['code'], second.json()['code'])
        self.assertTrue(review_work_order(first.json()['code'])['human_review_required'])
