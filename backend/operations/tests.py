import io
from datetime import timedelta
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth.models import User
from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient
from config.settings import parse_origins
from .models import Alert, Asset, AuditLog, Profile, ReportExport, Threshold, WorkOrder


class OperationsApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.operator = User.objects.create_user(username='operator@example.com', email='operator@example.com', password='demo-password')
        self.admin = User.objects.create_user(username='admin@example.com', email='admin@example.com', password='demo-password')
        Profile.objects.create(user=self.operator, display_name='运维员', role=Profile.Role.OPERATOR)
        Profile.objects.create(user=self.admin, display_name='管理员', role=Profile.Role.ADMINISTRATOR)
        self.asset = Asset.objects.create(code='FAN-01', name='风机', zone='UT-ZB', asset_type='执行器')
        self.alert = Alert.objects.create(code='ALM-1', asset=self.asset, severity=Alert.Severity.WARNING, category='设备', title='测试告警', detail='测试', opened_at='2026-08-26T00:00:00Z')

    def auth(self, user):
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {Token.objects.get_or_create(user=user)[0].key}')

    def test_health_is_public(self):
        response = self.client.get('/api/health/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['status'], 'ok')
        self.assertTrue(response.headers.get('X-Request-Id'))
        self.assertEqual(response.headers.get('Cache-Control'), 'no-store')
        self.assertIn('geolocation=()', response.headers.get('Permissions-Policy', ''))
        self.assertIn('version', response.json())
        self.assertIn('commit', response.json())

    def test_api_errors_use_a_stable_envelope(self):
        self.auth(self.operator)
        response = self.client.get('/api/assets/?page=invalid')
        self.assertEqual(response.status_code, 400)
        self.assertEqual(set(response.json()), {'error', 'message', 'details'})
        missing = self.client.get('/api/does-not-exist/', HTTP_X_REQUEST_ID='scan-404')
        self.assertEqual(missing.status_code, 404)
        self.assertEqual(set(missing.json()), {'error', 'message', 'details'})
        self.assertEqual(missing.headers.get('X-Request-Id'), 'scan-404')

    def test_ready_checks_database_and_is_public(self):
        response = self.client.get('/api/ready/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['status'], 'ready')
        self.assertEqual(response.json()['checks']['database'], 'ok')
        self.assertGreaterEqual(response.json()['latencyMs'], 0)

    def test_login_returns_token(self):
        response = self.client.post('/api/auth/login/', {'email': self.operator.email, 'password': 'demo-password'}, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertIn('accessToken', response.json())

    def test_duplicate_active_emails_are_rejected(self):
        User.objects.create_user(username='duplicate@example.com', email=self.operator.email, password='demo-password')
        response = self.client.post('/api/auth/login/', {'email': self.operator.email, 'password': 'demo-password'}, format='json')
        self.assertEqual(response.status_code, 401)

    def test_origin_validation_rejects_credentials_and_paths(self):
        with self.assertRaises(ValueError):
            parse_origins('https://user:secret@example.com', '', 'CORS_ALLOWED_ORIGINS')
        with self.assertRaises(ValueError):
            parse_origins('https://example.com/api', '', 'CORS_ALLOWED_ORIGINS')

    def test_expired_token_is_rejected_and_rotated_on_login(self):
        token = Token.objects.create(user=self.operator)
        token.created = timezone.now() - timedelta(seconds=settings.API_TOKEN_TTL_SECONDS + 1)
        token.save(update_fields=['created'])
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {token.key}')
        self.assertEqual(self.client.get('/api/auth/me/').status_code, 401)
        login = self.client.post('/api/auth/login/', {'email': self.operator.email, 'password': 'demo-password'}, format='json')
        self.assertEqual(login.status_code, 200)
        self.assertNotEqual(login.json()['accessToken'], token.key)

    def test_read_api_contract_and_report_export(self):
        threshold = Threshold.objects.create(key='temperature', label='温度', warning=28, alarm=32, unit='°C')
        self.auth(self.operator)
        for path in ['/api/dashboard/', '/api/assets/?search=FAN', '/api/alerts/?status=open', '/api/work-orders/?page=1&pageSize=10', '/api/telemetry/', '/api/thresholds/', '/api/audit/']:
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200, path)
        report = self.client.post('/api/report-exports/', {'report': 'daily'}, format='json')
        self.assertEqual(report.status_code, 201)
        self.assertEqual(report.json()['reportType'], 'daily')
        self.assertEqual(self.client.get('/api/report-exports/').status_code, 200)
        self.assertEqual(self.client.get('/api/assets/?pageSize=not-a-number').status_code, 400)
        self.assertEqual(self.client.get('/api/assets/?status=broken').status_code, 400)
        self.assertEqual(self.client.get('/api/alerts/?severity=blocker').status_code, 400)
        self.assertEqual(self.client.get('/api/alerts/?openedFrom=not-a-date').status_code, 400)
        self.assertEqual(self.client.get('/api/alerts/?openedFrom=2026-08-27T00:00:00Z&openedTo=2026-08-26T00:00:00Z').status_code, 400)
        self.assertEqual(self.client.get('/api/work-orders/?updatedFrom=not-a-date').status_code, 400)
        page = self.client.get('/api/assets/?page=1&pageSize=1').json()
        self.assertEqual(page['pageCount'], 1)
        self.assertFalse(page['hasNext'])

    def test_dashboard_uses_the_latest_telemetry_reading(self):
        from .models import Telemetry

        Telemetry.objects.create(asset=self.asset, metric='temperature', value=31, unit='°C', quality=Telemetry.Quality.GOOD, recorded_at='2026-08-26T01:00:00Z')
        latest = Telemetry.objects.create(asset=self.asset, metric='temperature', value=35, unit='°C', quality=Telemetry.Quality.GOOD, recorded_at='2026-08-26T02:00:00Z')
        self.auth(self.operator)

        response = self.client.get('/api/dashboard/')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['telemetry']['id'], latest.id)

    def test_malformed_object_payloads_return_400_instead_of_500(self):
        self.auth(self.operator)
        self.assertEqual(self.client.post('/api/work-orders/', ['not', 'an', 'object'], format='json').status_code, 400)
        self.assertEqual(self.client.post('/api/work-orders/', {'assetCode': ['FAN-01'], 'title': '异常'}, format='json').status_code, 400)
        self.assertEqual(self.client.post('/api/work-orders/', {'assetCode': 'FAN-01', 'title': '异常', 'description': {'unexpected': 'object'}}, format='json').status_code, 400)
        self.assertEqual(self.client.post('/api/work-orders/999/transition/', ['in_progress'], format='json').status_code, 400)
        self.assertEqual(self.client.post('/api/report-exports/', ['daily'], format='json').status_code, 400)
        self.assertEqual(self.client.post('/api/report-exports/', {'report': ['daily']}, format='json').status_code, 400)
        self.auth(self.admin)
        Threshold.objects.create(key='temperature', label='温度', warning=28, alarm=32, unit='°C')
        self.assertEqual(self.client.put('/api/thresholds/temperature/', ['bad'], format='json').status_code, 400)

    def test_unknown_transition_type_returns_400_instead_of_500(self):
        order = WorkOrder.objects.create(code='WO-2', asset=self.asset, title='测试工单', status=WorkOrder.Status.OPEN, created_by=self.operator)
        self.auth(self.operator)
        response = self.client.post(f'/api/work-orders/{order.pk}/transition/', {'to': ['assigned']}, format='json')
        self.assertEqual(response.status_code, 400)

    def test_viewer_cannot_write(self):
        viewer = User.objects.create_user(username='viewer@example.com', email='viewer@example.com', password='demo-password')
        Profile.objects.create(user=viewer, display_name='查看者', role=Profile.Role.VIEWER)
        self.auth(viewer)
        self.assertEqual(self.client.post(f'/api/alerts/{self.alert.pk}/acknowledge/').status_code, 403)
        self.assertEqual(self.client.post('/api/work-orders/', {'assetCode': self.asset.code, 'title': '不应创建'}, format='json').status_code, 403)
        self.assertEqual(self.client.put('/api/thresholds/missing/', {'warning': 1, 'alarm': 2}, format='json').status_code, 403)

    def test_admin_can_manage_user_lifecycle(self):
        self.auth(self.admin)
        created = self.client.post('/api/admin/users/', {'email': 'new-operator@example.com', 'password': 'strong-password-2026', 'displayName': '新运维员', 'role': Profile.Role.OPERATOR}, format='json')
        self.assertEqual(created.status_code, 201)
        user_id = created.json()['id']
        self.assertEqual(created.json()['role'], Profile.Role.OPERATOR)
        listed = self.client.get('/api/admin/users/?search=new-operator&active=true')
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(listed.json()['total'], 1)
        updated = self.client.patch(f'/api/admin/users/{user_id}/', {'role': Profile.Role.VIEWER, 'isActive': False, 'displayName': '已停用'}, format='json')
        self.assertEqual(updated.status_code, 200)
        self.assertFalse(updated.json()['isActive'])
        duplicate = self.client.post('/api/admin/users/', {'email': 'new-operator@example.com', 'password': 'strong-password-2026'}, format='json')
        self.assertEqual(duplicate.status_code, 409)
        invalid_email = self.client.post('/api/admin/users/', {'email': 'not-an-email', 'password': 'strong-password-2026'}, format='json')
        self.assertEqual(invalid_email.status_code, 400)

    def test_non_admin_cannot_manage_users(self):
        self.auth(self.operator)
        self.assertEqual(self.client.get('/api/admin/users/').status_code, 403)

    def test_admin_cannot_remove_last_administrator(self):
        self.auth(self.admin)
        response = self.client.patch(f'/api/admin/users/{self.admin.pk}/', {'role': Profile.Role.OPERATOR}, format='json')
        self.assertEqual(response.status_code, 409)

    def test_superuser_profile_defaults_to_administrator(self):
        superuser = User.objects.create_superuser(username='root@example.com', email='root@example.com', password='root-password-2026')
        self.auth(superuser)
        response = self.client.patch(f'/api/admin/users/{superuser.pk}/', {'displayName': '系统超级管理员'}, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['role'], Profile.Role.ADMINISTRATOR)

    def test_audit_endpoint_serializes_camel_case_fields(self):
        self.auth(self.operator)
        response = self.client.get('/api/audit/')
        self.assertEqual(response.status_code, 200)
        self.assertIn('items', response.json())

    def test_audit_endpoint_supports_search_and_pagination(self):
        AuditLog.objects.create(actor=self.operator, action='work_order.created_manual', resource_type='work_order', resource_id='42', detail={'source': 'manual'}, request_id='req-manual')
        AuditLog.objects.create(actor=self.operator, action='alert.acknowledged', resource_type='alert', resource_id='7', detail={}, request_id='req-alert')
        self.auth(self.operator)
        response = self.client.get('/api/audit/?search=manual&page=1&pageSize=1')
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body['total'], 1)
        self.assertEqual(body['pageCount'], 1)
        self.assertEqual(body['items'][0]['action'], 'work_order.created_manual')

    def test_paginated_lists_are_newest_first(self):
        newer = Asset.objects.create(code='CTRL-02', name='控制器', zone='UT-ZA', asset_type='控制器')
        self.auth(self.operator)
        response = self.client.get('/api/assets/?page=1&pageSize=1')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['items'][0]['id'], newer.pk)

    def test_operator_can_acknowledge_alert(self):
        self.auth(self.operator)
        response = self.client.post(f'/api/alerts/{self.alert.pk}/acknowledge/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['status'], Alert.Status.ACKNOWLEDGED)

    def test_completed_work_order_requires_admin(self):
        order = WorkOrder.objects.create(code='WO-1', asset=self.asset, title='测试工单', status=WorkOrder.Status.PENDING_REVIEW, created_by=self.operator)
        self.auth(self.operator)
        self.assertEqual(self.client.post(f'/api/work-orders/{order.pk}/transition/', {'to': WorkOrder.Status.COMPLETED}, format='json').status_code, 403)
        self.auth(self.admin)
        self.assertEqual(self.client.post(f'/api/work-orders/{order.pk}/transition/', {'to': WorkOrder.Status.COMPLETED}, format='json').status_code, 200)

    def test_work_order_transition_rejects_stale_version(self):
        order = WorkOrder.objects.create(code='WO-VERSION', asset=self.asset, title='版本校验', status=WorkOrder.Status.OPEN, created_by=self.operator)
        self.auth(self.operator)
        response = self.client.post(f'/api/work-orders/{order.pk}/transition/', {'to': WorkOrder.Status.ASSIGNED, 'version': 99}, format='json')
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()['error'], 'version_conflict')
        order.refresh_from_db()
        self.assertEqual(order.status, WorkOrder.Status.OPEN)

    def test_linked_work_order_is_unique_per_alert(self):
        WorkOrder.objects.create(code='WO-LINKED', source_alert=self.alert, asset=self.asset, title='已存在', created_by=self.operator)
        self.auth(self.operator)
        response = self.client.post(f'/api/alerts/{self.alert.pk}/work-order/')
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()['error'], 'conflict')

    def test_manual_work_order_rejects_unknown_priority(self):
        self.auth(self.operator)
        response = self.client.post('/api/work-orders/', {'assetCode': self.asset.code, 'title': '异常优先级', 'priority': 'blocker'}, format='json')
        self.assertEqual(response.status_code, 400)

    def test_manual_work_order_is_idempotent(self):
        self.auth(self.operator)
        headers = {'HTTP_IDEMPOTENCY_KEY': 'manual-work-order-001'}
        payload = {'assetCode': self.asset.code, 'title': '幂等工单', 'priority': 'normal'}
        first = self.client.post('/api/work-orders/', payload, format='json', **headers)
        second = self.client.post('/api/work-orders/', payload, format='json', **headers)
        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(first.json()['id'], second.json()['id'])
        self.assertEqual(WorkOrder.objects.filter(title='幂等工单').count(), 1)
        changed = self.client.post('/api/work-orders/', {'assetCode': self.asset.code, 'title': '另一张工单', 'priority': 'normal'}, format='json', **headers)
        self.assertEqual(changed.status_code, 409)

    def test_idempotency_key_is_validated(self):
        self.auth(self.operator)
        response = self.client.post('/api/work-orders/', {'assetCode': self.asset.code, 'title': '非法键'}, format='json', HTTP_IDEMPOTENCY_KEY='bad key')
        self.assertEqual(response.status_code, 400)

    def test_manual_work_order_rolls_back_when_audit_fails(self):
        self.auth(self.operator)
        self.client.raise_request_exception = False
        with patch('operations.views.audit', side_effect=RuntimeError('audit unavailable')):
            response = self.client.post('/api/work-orders/', {'assetCode': self.asset.code, 'title': '审计失败回滚'}, format='json')
        self.assertEqual(response.status_code, 500)
        self.assertTrue(response.headers.get('X-Request-Id'))
        self.assertFalse(WorkOrder.objects.filter(title='审计失败回滚').exists())

    def test_report_export_rolls_back_when_audit_fails(self):
        self.auth(self.operator)
        self.client.raise_request_exception = False
        with patch('operations.views.audit', side_effect=RuntimeError('audit unavailable')):
            response = self.client.post('/api/report-exports/', {'report': 'daily'}, format='json')
        self.assertEqual(response.status_code, 500)
        self.assertFalse(ReportExport.objects.filter(report_type='daily').exists())

    def test_report_export_is_idempotent(self):
        self.auth(self.operator)
        first = self.client.post('/api/report-exports/', {'report': 'daily'}, format='json', HTTP_IDEMPOTENCY_KEY='report-export-001')
        second = self.client.post('/api/report-exports/', {'report': 'daily'}, format='json', HTTP_IDEMPOTENCY_KEY='report-export-001')
        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(first.json()['id'], second.json()['id'])
        self.assertEqual(ReportExport.objects.filter(report_type='daily').count(), 1)
        changed = self.client.post('/api/report-exports/', {'report': 'assets'}, format='json', HTTP_IDEMPOTENCY_KEY='report-export-001')
        self.assertEqual(changed.status_code, 409)

    def test_threshold_version_must_be_numeric(self):
        threshold = Threshold.objects.create(key='temperature', label='温度', warning=28, alarm=32, unit='°C')
        self.auth(self.admin)
        response = self.client.put(f'/api/thresholds/{threshold.key}/', {'warning': 29, 'alarm': 33, 'version': 'not-a-number'}, format='json')
        self.assertEqual(response.status_code, 400)

    def test_unknown_threshold_returns_not_found(self):
        self.auth(self.admin)
        response = self.client.put('/api/thresholds/missing/', {'warning': 1, 'alarm': 2}, format='json')
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()['error'], 'not_found')

    def test_threshold_rejects_non_finite_values(self):
        threshold = Threshold.objects.create(key='temperature', label='温度', warning=28, alarm=32, unit='°C')
        self.auth(self.admin)
        for warning, alarm in [('NaN', 33), (29, 'Infinity')]:
            response = self.client.put(f'/api/thresholds/{threshold.key}/', {'warning': warning, 'alarm': alarm, 'version': threshold.version}, format='json')
            self.assertEqual(response.status_code, 400)

    def test_database_rejects_invalid_threshold_order(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Threshold.objects.create(key='invalid-order', label='非法', warning=40, alarm=30, unit='°C')

    def test_seed_demo_assigns_distinct_twin_positions(self):
        call_command('seed_demo', stdout=io.StringIO())
        positions = list(Asset.objects.values_list('code', 'position'))
        self.assertEqual(len(positions), 4)
        self.assertEqual(len({tuple(sorted(position.items())) for _, position in positions}), 4)

    def test_seed_demo_resets_lifecycle_timestamps(self):
        call_command('seed_demo', stdout=io.StringIO())
        alert = Alert.objects.get(code='ALM-260826-003')
        alert.status = Alert.Status.RESOLVED
        alert.resolved_at = timezone.now()
        alert.save(update_fields=['status', 'resolved_at'])
        order = WorkOrder.objects.get(code='WO-260826-08')
        order.status = WorkOrder.Status.COMPLETED
        order.completed_at = timezone.now()
        order.reviewed_by = self.admin
        order.version = 8
        order.save(update_fields=['status', 'completed_at', 'reviewed_by', 'version'])

        call_command('seed_demo', stdout=io.StringIO())

        alert.refresh_from_db()
        order.refresh_from_db()
        self.assertEqual(alert.status, Alert.Status.OPEN)
        self.assertIsNone(alert.resolved_at)
        self.assertEqual(order.status, WorkOrder.Status.OPEN)
        self.assertIsNone(order.completed_at)
        self.assertIsNone(order.reviewed_by)
        self.assertEqual(order.version, 1)
