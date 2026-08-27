import io

from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import TestCase
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient
from .models import Alert, Asset, Profile, Threshold, WorkOrder


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

    def test_login_returns_token(self):
        response = self.client.post('/api/auth/login/', {'email': self.operator.email, 'password': 'demo-password'}, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertIn('accessToken', response.json())

    def test_audit_endpoint_serializes_camel_case_fields(self):
        self.auth(self.operator)
        response = self.client.get('/api/audit/')
        self.assertEqual(response.status_code, 200)
        self.assertIn('items', response.json())

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

    def test_manual_work_order_rejects_unknown_priority(self):
        self.auth(self.operator)
        response = self.client.post('/api/work-orders/', {'assetCode': self.asset.code, 'title': '异常优先级', 'priority': 'blocker'}, format='json')
        self.assertEqual(response.status_code, 400)

    def test_threshold_version_must_be_numeric(self):
        threshold = Threshold.objects.create(key='temperature', label='温度', warning=28, alarm=32, unit='°C')
        self.auth(self.admin)
        response = self.client.put(f'/api/thresholds/{threshold.key}/', {'warning': 29, 'alarm': 33, 'version': 'not-a-number'}, format='json')
        self.assertEqual(response.status_code, 400)

    def test_threshold_rejects_non_finite_values(self):
        threshold = Threshold.objects.create(key='temperature', label='温度', warning=28, alarm=32, unit='°C')
        self.auth(self.admin)
        for warning, alarm in [('NaN', 33), (29, 'Infinity')]:
            response = self.client.put(f'/api/thresholds/{threshold.key}/', {'warning': warning, 'alarm': alarm, 'version': threshold.version}, format='json')
            self.assertEqual(response.status_code, 400)

    def test_seed_demo_assigns_distinct_twin_positions(self):
        call_command('seed_demo', stdout=io.StringIO())
        positions = list(Asset.objects.values_list('code', 'position'))
        self.assertEqual(len(positions), 4)
        self.assertEqual(len({tuple(sorted(position.items())) for _, position in positions}), 4)
