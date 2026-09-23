import io
import csv
import json
import struct
import tempfile
from datetime import datetime, timedelta
from unittest.mock import patch
from types import SimpleNamespace

from django.conf import settings
from django.contrib.auth.models import User
from django.core.cache import cache
from django.core.management import call_command
from django.core.management.base import CommandError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient
from config.settings import parse_origins
from .models import Alert, Asset, AuditLog, ControllerCommandConfirmation, HardwareBinding, Profile, RegistrationRequest, ReportExport, SpatialFeature, Telemetry, Threshold, TwinModelRelease, WorkOrder


class OperationsApiTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.operator = User.objects.create_user(username='operator@example.com', email='operator@example.com', password='demo-password')
        self.admin = User.objects.create_user(username='admin@example.com', email='admin@example.com', password='demo-password')
        Profile.objects.create(user=self.operator, display_name='运维员', role=Profile.Role.OPERATOR)
        Profile.objects.create(user=self.admin, display_name='管理员', role=Profile.Role.ADMINISTRATOR)
        self.asset = Asset.objects.create(code='FAN-01', name='风机', zone='UT-ZB', asset_type='执行器')
        self.alert = Alert.objects.create(code='ALM-1', asset=self.asset, severity=Alert.Severity.WARNING, category='设备', title='测试告警', detail='测试', opened_at='2026-08-26T00:00:00Z')

    def auth(self, user):
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {Token.objects.get_or_create(user=user)[0].key}')

    def controller_confirmation(self, action, duty_percent=None):
        payload = {'action': action}
        if duty_percent is not None:
            payload['dutyPercent'] = duty_percent
        response = self.client.post('/api/controllers/CTRL-01/commands/confirmations/', payload, format='json')
        self.assertEqual(response.status_code, 201)
        return response.json()['confirmationToken']

    def test_alert_history_filters_by_device_and_time(self):
        other = Asset.objects.create(code='OTHER', name='其他设备', zone='UT-ZA', asset_type='测点')
        Alert.objects.create(code='OTHER-ALERT', asset=other, severity='warning', category='设备', title='其他事件', detail='', opened_at='2026-08-26T00:00:00Z')
        self.auth(self.operator)
        result = self.client.get('/api/alerts/', {'assetCode': self.asset.code, 'openedFrom': '2026-08-25T00:00:00Z', 'openedTo': '2026-08-27T00:00:00Z'})
        self.assertEqual(result.status_code, 200)
        self.assertEqual([item['code'] for item in result.json()['items']], ['ALM-1'])
        self.assertEqual(result.json()['total'], 1)
        self.assertEqual(self.client.get('/api/alerts/', {'assetCode': 'missing'}).json()['total'], 0)
        self.assertEqual(self.client.get('/api/alerts/', {'assetCode': self.asset.code, 'openedFrom': '2026-08-27T00:00:00Z'}).json()['total'], 0)

    def test_alert_history_device_set_is_filtered_before_pagination(self):
        other = Asset.objects.create(code='OTHER', name='其他设备', zone='UT-ZA', asset_type='测点')
        Alert.objects.bulk_create([
            Alert(code=f'UNRELATED-{index}', asset=other, severity='warning', category='设备', title='其他事件', detail='', opened_at=timezone.now())
            for index in range(105)
        ])
        self.auth(self.operator)
        result = self.client.get('/api/alerts/', {'assetCodes': f'{self.asset.code},UNKNOWN', 'pageSize': 100})
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.json()['total'], 1)
        self.assertEqual(result.json()['items'][0]['code'], 'ALM-1')
        for value in ['', 'FAN-01,', ',FAN-01', ','.join(['X'] * 101)]:
            self.assertEqual(self.client.get('/api/alerts/', {'assetCodes': value}).status_code, 400)

    def test_alerts_paginate_beyond_one_hundred_without_overlap(self):
        page_asset = Asset.objects.create(code='PAGE-ASSET', name='分页资产', zone='UT-ZA', asset_type='测点')
        Alert.objects.bulk_create([
            Alert(code=f'PAGE-{index}', asset=page_asset, severity='warning', category='设备', title='分页', detail='', opened_at=timezone.now())
            for index in range(101)
        ])
        self.auth(self.operator)
        page1 = self.client.get('/api/alerts/', {'assetCode': page_asset.code, 'page': 1, 'pageSize': 100}).json()
        page2 = self.client.get('/api/alerts/', {'assetCode': page_asset.code, 'page': 2, 'pageSize': 100}).json()
        ids1 = [item['id'] for item in page1['items']]
        ids2 = [item['id'] for item in page2['items']]
        self.assertEqual(page1['total'], 101)
        self.assertEqual(len(ids1), 100)
        self.assertEqual(len(ids2), 1)
        self.assertEqual(ids1, sorted(ids1, reverse=True))
        self.assertFalse(set(ids1) & set(ids2))

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

    def test_preflight_command_runs_database_probe_in_ci_mode(self):
        output = io.StringIO()
        call_command('production_preflight', '--allow-non-production', '--skip-migrations', stdout=output)
        self.assertIn('Production preflight passed', output.getvalue())

    def test_data_governance_report_is_read_only_and_machine_readable(self):
        Telemetry.objects.create(asset=self.asset, metric='temperature', value=26, unit='°C', quality=Telemetry.Quality.GOOD, recorded_at=timezone.now() - timedelta(days=91))
        AuditLog.objects.create(actor=self.operator, action='test.audit', resource_type='test', resource_id='1', detail={})
        before = {'telemetry': Telemetry.objects.count(), 'audit': AuditLog.objects.count(), 'exports': ReportExport.objects.count()}
        output = io.StringIO()

        call_command('data_governance_report', '--telemetry-days=90', '--format=json', stdout=output)

        report = json.loads(output.getvalue())
        self.assertEqual(report['mode'], 'read-only')
        self.assertEqual(report['collections']['telemetry']['reviewCandidates'], 1)
        self.assertEqual(before, {'telemetry': Telemetry.objects.count(), 'audit': AuditLog.objects.count(), 'exports': ReportExport.objects.count()})

    def test_login_returns_token(self):
        response = self.client.post('/api/auth/login/', {'email': self.operator.email, 'password': 'demo-password'}, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertIn('accessToken', response.json())

    @patch('operations.views.publish_controller_command')
    def test_operator_can_send_audited_controller_led_command(self, publish_command):
        Asset.objects.create(code='CTRL-01', name='主控', zone='CTRL', asset_type='控制器')
        publish_command.return_value = {
            'schema': 'ut.command.ack.v1', 'cmdId': 'platform-command', 'status': 'accepted', 'reason': 'led_blue',
        }
        self.auth(self.operator)

        token = self.controller_confirmation('led_blue')
        response = self.client.post('/api/controllers/CTRL-01/commands/', {'action': 'led_blue', 'confirmationToken': token}, format='json')

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()['delivery'], 'acknowledged')
        command = publish_command.call_args.args[0]
        self.assertEqual(command['schema'], 'ut.command.v1')
        self.assertEqual(command['action'], 'led_blue')
        self.assertEqual(command['ttlMs'], 10000)
        self.assertTrue(command['cmdId'].startswith('platform-'))
        self.assertTrue(AuditLog.objects.filter(action='controller.command.sent', resource_id='CTRL-01').exists())

    @patch('operations.views.publish_controller_command')
    def test_operator_can_start_the_fan_with_the_bounded_relay_command(self, publish_command):
        Asset.objects.create(code='CTRL-01', name='主控', zone='CTRL', asset_type='控制器')
        publish_command.return_value = {
            'schema': 'ut.command.ack.v1', 'cmdId': 'platform-command', 'status': 'accepted', 'reason': 'relay_active',
        }
        self.auth(self.operator)

        token = self.controller_confirmation('relay_on')
        response = self.client.post('/api/controllers/CTRL-01/commands/', {'action': 'relay_on', 'confirmationToken': token}, format='json')

        self.assertEqual(response.status_code, 201)
        command = publish_command.call_args.args[0]
        self.assertEqual(command['action'], 'relay_on')
        self.assertEqual(command['ttlMs'], 10000)

    @patch('operations.views.publish_controller_command')
    def test_operator_can_set_validated_fan_pwm(self, publish_command):
        Asset.objects.create(code='CTRL-01', name='主控', zone='CTRL', asset_type='控制器')
        publish_command.return_value = {
            'schema': 'ut.command.ack.v1', 'cmdId': 'platform-command', 'status': 'accepted', 'reason': 'fan_pwm_set',
        }
        self.auth(self.operator)

        token = self.controller_confirmation('fan_pwm', 60)
        response = self.client.post('/api/controllers/CTRL-01/commands/', {'action': 'fan_pwm', 'dutyPercent': 60, 'confirmationToken': token}, format='json')

        self.assertEqual(response.status_code, 201)
        command = publish_command.call_args.args[0]
        self.assertEqual(command['action'], 'fan_pwm')
        self.assertEqual(command['dutyPercent'], 60)

    @patch('operations.views.publish_controller_command')
    def test_operator_can_set_validated_second_fan_pwm(self, publish_command):
        Asset.objects.create(code='CTRL-01', name='主控', zone='CTRL', asset_type='控制器')
        publish_command.return_value = {
            'schema': 'ut.command.ack.v1', 'cmdId': 'platform-command', 'status': 'accepted', 'reason': 'fan2_pwm_set',
        }
        self.auth(self.operator)

        token = self.controller_confirmation('fan2_pwm', 30)
        response = self.client.post('/api/controllers/CTRL-01/commands/', {'action': 'fan2_pwm', 'dutyPercent': 30, 'confirmationToken': token}, format='json')

        self.assertEqual(response.status_code, 201)
        command = publish_command.call_args.args[0]
        self.assertEqual(command['action'], 'fan2_pwm')
        self.assertEqual(command['dutyPercent'], 30)

    def test_fan_pwm_rejects_out_of_range_duty(self):
        Asset.objects.create(code='CTRL-01', name='主控', zone='CTRL', asset_type='控制器')
        self.auth(self.operator)

        response = self.client.post('/api/controllers/CTRL-01/commands/', {'action': 'fan_pwm', 'dutyPercent': 101}, format='json')

        self.assertEqual(response.status_code, 400)

    def test_second_fan_pwm_rejects_missing_duty(self):
        Asset.objects.create(code='CTRL-01', name='主控', zone='CTRL', asset_type='控制器')
        self.auth(self.operator)

        response = self.client.post('/api/controllers/CTRL-01/commands/', {'action': 'fan2_pwm'}, format='json')

        self.assertEqual(response.status_code, 400)

    def test_controller_command_rejects_missing_replayed_and_mismatched_confirmation(self):
        Asset.objects.create(code='CTRL-01', name='主控', zone='CTRL', asset_type='控制器')
        self.auth(self.operator)
        missing = self.client.post('/api/controllers/CTRL-01/commands/', {'action': 'led_blue'}, format='json')
        self.assertEqual(missing.status_code, 409)
        self.assertEqual(missing.json()['error'], 'confirmation_required')

        token = self.controller_confirmation('led_blue')
        mismatched = self.client.post('/api/controllers/CTRL-01/commands/', {'action': 'led_green', 'confirmationToken': token}, format='json')
        self.assertEqual(mismatched.status_code, 409)
        with patch('operations.views.publish_controller_command', return_value=None):
            accepted = self.client.post('/api/controllers/CTRL-01/commands/', {'action': 'led_blue', 'confirmationToken': token}, format='json')
        self.assertEqual(accepted.status_code, 201)
        replayed = self.client.post('/api/controllers/CTRL-01/commands/', {'action': 'led_blue', 'confirmationToken': token}, format='json')
        self.assertEqual(replayed.status_code, 409)

    def test_controller_confirmation_is_bound_to_operator_and_expiry(self):
        Asset.objects.create(code='CTRL-01', name='主控', zone='CTRL', asset_type='控制器')
        self.auth(self.operator)
        other_user_token = self.controller_confirmation('relay_off')
        self.auth(self.admin)
        other_user = self.client.post('/api/controllers/CTRL-01/commands/', {'action': 'relay_off', 'confirmationToken': other_user_token}, format='json')
        self.assertEqual(other_user.status_code, 409)

        self.auth(self.operator)
        expired_token = self.controller_confirmation('relay_off')
        ControllerCommandConfirmation.objects.filter(user=self.operator, action='relay_off', consumed_at__isnull=True).update(expires_at=timezone.now() - timedelta(seconds=1))
        expired = self.client.post('/api/controllers/CTRL-01/commands/', {'action': 'relay_off', 'confirmationToken': expired_token}, format='json')
        self.assertEqual(expired.status_code, 409)

    def test_viewer_cannot_send_controller_command(self):
        viewer = User.objects.create_user(username='viewer@example.com', email='viewer@example.com', password='demo-password')
        Profile.objects.create(user=viewer, display_name='查看者', role=Profile.Role.VIEWER)
        Asset.objects.create(code='CTRL-01', name='主控', zone='CTRL', asset_type='控制器')
        self.auth(viewer)

        response = self.client.post('/api/controllers/CTRL-01/commands/', {'action': 'led_blue'}, format='json')

        self.assertEqual(response.status_code, 403)

    @override_settings(API_TOKEN_TTL_SECONDS=900, API_TOKEN_RENEWAL_WINDOW_SECONDS=60)
    def test_login_rotates_a_token_that_is_about_to_expire(self):
        token = Token.objects.create(user=self.operator)
        token.created = timezone.now() - timedelta(seconds=850)
        token.save(update_fields=['created'])

        response = self.client.post('/api/auth/login/', {'email': self.operator.email, 'password': 'demo-password'}, format='json')

        self.assertEqual(response.status_code, 200)
        self.assertNotEqual(response.json()['accessToken'], token.key)
        self.assertFalse(Token.objects.filter(key=token.key).exists())

    def test_password_change_rotates_bearer_credential(self):
        self.auth(self.operator)
        previous_token = Token.objects.get(user=self.operator).key
        response = self.client.post('/api/auth/password/', {
            'currentPassword': 'demo-password',
            'newPassword': 'Stronger-Operator-2026!',
        }, format='json')
        self.assertEqual(response.status_code, 200)
        replacement_token = response.json()['accessToken']
        self.assertNotEqual(replacement_token, previous_token)
        self.assertFalse(Token.objects.filter(key=previous_token).exists())
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {replacement_token}')
        self.assertEqual(self.client.get('/api/auth/me/').status_code, 200)
        self.operator.refresh_from_db()
        self.assertFalse(self.operator.check_password('demo-password'))
        self.assertTrue(self.operator.check_password('Stronger-Operator-2026!'))
        self.assertTrue(AuditLog.objects.filter(action='auth.password_changed', resource_id=str(self.operator.pk)).exists())

    def test_registration_request_needs_administrator_approval_before_login(self):
        application = self.client.post('/api/auth/registration-requests/', {
            'account': 'new.operator',
            'displayName': '新运维员',
            'role': Profile.Role.OPERATOR,
        }, format='json')
        self.assertEqual(application.status_code, 201)
        self.assertFalse(User.objects.filter(email='new.operator').exists())
        request_id = application.json()['id']
        self.auth(self.admin)
        pending = self.client.get('/api/admin/registration-requests/?status=pending')
        self.assertEqual(pending.status_code, 200)
        self.assertEqual(pending.json()['total'], 1)
        approved = self.client.patch(f'/api/admin/registration-requests/{request_id}/', {'status': 'approved'}, format='json')
        self.assertEqual(approved.status_code, 200)
        self.assertEqual(approved.json()['status'], RegistrationRequest.Status.APPROVED)
        self.assertIn('setupToken', approved.json())
        created = User.objects.get(email='new.operator')
        self.assertEqual(created.profile.role, Profile.Role.OPERATOR)
        self.assertFalse(created.is_active)
        self.assertFalse(created.has_usable_password())
        self.client.credentials()
        before_setup = self.client.post('/api/auth/login/', {'email': 'new.operator', 'password': 'NewOperator!2026'}, format='json')
        self.assertEqual(before_setup.status_code, 401)
        setup = self.client.post(
            '/api/auth/registration-requests/setup/',
            {'token': approved.json()['setupToken'], 'password': 'NewOperator!2026'},
            format='json',
        )
        self.assertEqual(setup.status_code, 200)
        login = self.client.post('/api/auth/login/', {'email': 'new.operator', 'password': 'NewOperator!2026'}, format='json')
        self.assertEqual(login.status_code, 200)
        reused = self.client.post(
            '/api/auth/registration-requests/setup/',
            {'token': approved.json()['setupToken'], 'password': 'AnotherStrong!2026'},
            format='json',
        )
        self.assertEqual(reused.status_code, 400)
        request_record = RegistrationRequest.objects.get(pk=request_id)
        self.assertEqual(request_record.setup_token_hash, '')
        self.assertIsNone(request_record.setup_expires_at)
        self.assertTrue(AuditLog.objects.filter(action='registration.approved').exists())

    def test_administrator_can_reissue_an_expired_unused_setup_link(self):
        application = self.client.post('/api/auth/registration-requests/', {
            'account': 'expired.operator',
            'displayName': '过期链接运维员',
            'role': Profile.Role.OPERATOR,
        }, format='json')
        self.auth(self.admin)
        approved = self.client.patch(
            f"/api/admin/registration-requests/{application.json()['id']}/",
            {'status': 'approved'},
            format='json',
        )
        old_token = approved.json()['setupToken']
        record = RegistrationRequest.objects.get(pk=application.json()['id'])
        record.setup_expires_at = timezone.now() - timedelta(seconds=1)
        record.save(update_fields=['setup_expires_at'])
        self.client.credentials()
        expired = self.client.post('/api/auth/registration-requests/setup/', {
            'token': old_token,
            'password': 'ExpiredOperator!2026',
        }, format='json')
        self.assertEqual(expired.status_code, 400)

        self.auth(self.admin)
        reissued = self.client.post(f'/api/admin/registration-requests/{record.pk}/setup-token/')
        self.assertEqual(reissued.status_code, 200)
        self.assertNotEqual(reissued.json()['setupToken'], old_token)
        self.assertTrue(AuditLog.objects.filter(action='registration.setup_token_reissued', resource_id=str(record.pk)).exists())

        self.client.credentials()
        self.assertEqual(self.client.post('/api/auth/registration-requests/setup/', {
            'token': old_token,
            'password': 'ExpiredOperator!2026',
        }, format='json').status_code, 400)
        completed = self.client.post('/api/auth/registration-requests/setup/', {
            'token': reissued.json()['setupToken'],
            'password': 'ExpiredOperator!2026',
        }, format='json')
        self.assertEqual(completed.status_code, 200)

    def test_registration_rejects_password_material(self):
        response = self.client.post('/api/auth/registration-requests/', {
            'account': 'weak-password.operator',
            'displayName': '弱口令测试账号',
            'role': Profile.Role.OPERATOR,
            'password': '123456789',
        }, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()['error'], 'invalid_request')
        self.assertFalse(RegistrationRequest.objects.filter(account='weak-password.operator').exists())

    def test_registration_rejection_requires_and_records_a_reason(self):
        application = self.client.post('/api/auth/registration-requests/', {
            'account': 'rejected.operator',
            'displayName': '待驳回账号',
            'role': Profile.Role.OPERATOR,
        }, format='json')
        self.assertEqual(application.status_code, 201)
        self.auth(self.admin)
        application_id = application.json()['id']
        missing_reason = self.client.patch(f'/api/admin/registration-requests/{application_id}/', {'status': 'rejected'}, format='json')
        self.assertEqual(missing_reason.status_code, 400)
        rejected = self.client.patch(f'/api/admin/registration-requests/{application_id}/', {
            'status': 'rejected',
            'reviewNote': '请使用单位分配的账号名称后重新申请。',
        }, format='json')
        self.assertEqual(rejected.status_code, 200)
        self.assertEqual(rejected.json()['reviewNote'], '请使用单位分配的账号名称后重新申请。')
        rejection_audit = AuditLog.objects.get(action='registration.rejected')
        self.assertTrue(rejection_audit.detail['hasReviewNote'])

    def test_registration_cannot_create_or_promote_a_second_administrator(self):
        public = self.client.post('/api/auth/registration-requests/', {
            'account': 'another.admin',
            'displayName': '第二管理员',
            'role': Profile.Role.ADMINISTRATOR,
            'password': 'AnotherAdmin!2026',
        }, format='json')
        self.assertEqual(public.status_code, 400)
        self.auth(self.admin)
        created = self.client.post('/api/admin/users/', {
            'email': 'second-admin@example.com', 'displayName': '第二管理员', 'password': 'AnotherAdmin!2026', 'role': Profile.Role.ADMINISTRATOR,
        }, format='json')
        self.assertEqual(created.status_code, 409)
        promoted = self.client.patch(f'/api/admin/users/{self.operator.pk}/', {'role': Profile.Role.ADMINISTRATOR}, format='json')
        self.assertEqual(promoted.status_code, 409)

    @override_settings(
        INGEST_API_KEY='test-ingest-key-that-is-at-least-thirty-two-characters',
        INGEST_PRINCIPAL_USERNAME='service-iotda-admin-boundary',
    )
    def test_machine_principal_is_not_managed_as_a_human_user(self):
        call_command('configure_ingest_principal', verbosity=0)
        principal = User.objects.get(username='service-iotda-admin-boundary')
        self.auth(self.admin)
        listing = self.client.get('/api/admin/users/?pageSize=100')
        self.assertEqual(listing.status_code, 200)
        self.assertNotIn(principal.pk, [item['id'] for item in listing.json()['items']])
        self.assertEqual(self.client.patch(f'/api/admin/users/{principal.pk}/', {'isActive': False}, format='json').status_code, 403)
        self.assertEqual(self.client.post('/api/admin/users/', {
            'email': 'fake-ingest@example.com',
            'displayName': '伪造机器账号',
            'password': 'FakeIngestPassword!2026',
            'role': Profile.Role.INGEST,
        }, format='json').status_code, 400)

    def test_superuser_login_returns_administrator_role(self):
        superuser = User.objects.create_superuser(username='login-root@example.com', email='login-root@example.com', password='root-password-2026')
        response = self.client.post('/api/auth/login/', {'email': superuser.email, 'password': 'root-password-2026'}, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['user']['role'], Profile.Role.ADMINISTRATOR)
        self.assertEqual(Profile.objects.get(user=superuser).role, Profile.Role.ADMINISTRATOR)

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

    def test_login_throttle_is_account_scoped_with_an_ip_wide_ceiling(self):
        cache.clear()
        try:
            for _ in range(10):
                response = self.client.post('/api/auth/login/', {'email': self.operator.email, 'password': 'wrong-password'}, format='json')
                self.assertEqual(response.status_code, 401)
            limited = self.client.post('/api/auth/login/', {'email': self.operator.email, 'password': 'wrong-password'}, format='json')
            self.assertEqual(limited.status_code, 429)
            other_account = self.client.post('/api/auth/login/', {'email': 'another-user@example.com', 'password': 'wrong-password'}, format='json')
            self.assertEqual(other_account.status_code, 401)
        finally:
            cache.clear()

    def test_successful_logins_do_not_consume_the_failed_attempt_budget(self):
        cache.clear()
        try:
            for _ in range(12):
                response = self.client.post('/api/auth/login/', {'email': self.operator.email, 'password': 'demo-password'}, format='json')
                self.assertEqual(response.status_code, 200)
            self.assertEqual(self.client.post('/api/auth/login/', {'email': self.operator.email, 'password': 'wrong-password'}, format='json').status_code, 401)
        finally:
            cache.clear()

    def test_telemetry_export_contains_full_history_and_immutable_snapshot(self):
        Telemetry.objects.bulk_create([
            Telemetry(asset=self.asset, event_id=f'csv-{i}', metric_key='temperature',
                      metric='=unsafe', value=i, unit='°C', quality='good', recorded_at=timezone.now())
            for i in range(125)
        ])
        self.auth(self.operator)
        response = self.client.post('/api/report-exports/', {'report': 'telemetry'}, format='json', HTTP_IDEMPOTENCY_KEY='history-csv-1')
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()['rowCount'], 125)
        path = f"/api/report-exports/{response.json()['id']}/download/"
        download = self.client.get(path)
        self.assertEqual(download.status_code, 200)
        rows = list(csv.DictReader(io.StringIO(download.content.decode('utf-8-sig'))))
        self.assertEqual(len(rows), 125)
        self.assertEqual(rows[0]['asset__code'], self.asset.code)
        self.assertEqual(rows[0]['metric'], "'=unsafe")
        self.assertIn('ingested_at', rows[0])
        other_asset = Asset.objects.create(code='CSV-OTHER', name='导出隔离设备', zone='UT-ZA', asset_type='测试')
        Telemetry.objects.create(asset=other_asset, event_id='csv-other', metric_key='temperature', metric='环境温度', value=99, unit='°C', quality='good', recorded_at=timezone.now())
        filtered = self.client.post('/api/report-exports/', {
            'report': 'telemetry',
            'filters': {'assetCode': self.asset.code, 'metricKey': 'temperature', 'quality': 'good'},
        }, format='json', HTTP_IDEMPOTENCY_KEY='history-csv-filtered-1')
        self.assertEqual(filtered.status_code, 201)
        self.assertEqual(filtered.json()['filters'], {'assetCode': self.asset.code, 'metricKey': 'temperature', 'quality': 'good'})
        self.assertEqual(filtered.json()['rowCount'], 125)
        filtered_download = self.client.get(f"/api/report-exports/{filtered.json()['id']}/download/")
        filtered_rows = list(csv.DictReader(io.StringIO(filtered_download.content.decode('utf-8-sig'))))
        self.assertEqual({row['asset__code'] for row in filtered_rows}, {self.asset.code})
        repeated_filtered = self.client.post('/api/report-exports/', {
            'report': 'telemetry',
            'filters': {'quality': 'good', 'metricKey': 'temperature', 'assetCode': self.asset.code},
        }, format='json', HTTP_IDEMPOTENCY_KEY='history-csv-filtered-1')
        self.assertEqual(repeated_filtered.status_code, 200)
        self.assertEqual(repeated_filtered.json()['id'], filtered.json()['id'])
        self.assertEqual(self.client.post('/api/report-exports/', {
            'report': 'telemetry', 'filters': {'assetCode': other_asset.code},
        }, format='json', HTTP_IDEMPOTENCY_KEY='history-csv-filtered-1').status_code, 409)
        self.assertEqual(self.client.post('/api/report-exports/', {
            'report': 'telemetry', 'filters': {'unknown': 'value'},
        }, format='json').status_code, 400)
        Telemetry.objects.all().delete()
        self.assertEqual(self.client.get(path).content, download.content)
        repeated = self.client.post('/api/report-exports/', {'report': 'telemetry'}, format='json', HTTP_IDEMPOTENCY_KEY='history-csv-1')
        self.assertEqual(repeated.json()['id'], response.json()['id'])
        outsider = User.objects.create_user(username='outsider')
        Profile.objects.create(user=outsider, display_name='查看者', role=Profile.Role.VIEWER)
        self.auth(outsider)
        self.assertEqual(self.client.get(path).status_code, 403)
        self.client.credentials()
        self.assertIn(self.client.post('/api/report-exports/', {'report': 'telemetry'}, format='json').status_code, [401, 403])

    def test_read_api_contract_and_report_export(self):
        threshold = Threshold.objects.create(key='temperature', label='温度', warning=28, alarm=32, unit='°C')
        self.auth(self.operator)
        for path in ['/api/dashboard/', '/api/assets/?search=FAN', '/api/alerts/?status=open', '/api/work-orders/?page=1&pageSize=10', '/api/telemetry/', '/api/thresholds/', '/api/audit/']:
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200, path)
        report = self.client.post('/api/report-exports/', {'report': 'daily'}, format='json')
        self.assertEqual(report.status_code, 201)
        self.assertEqual(report.json()['reportType'], 'daily')
        download = self.client.get(f"/api/report-exports/{report.json()['id']}/download/")
        self.assertEqual(download.status_code, 200)
        self.assertEqual(download['Content-Type'], 'text/csv; charset=utf-8')
        self.assertIn('assets_total', download.content.decode('utf-8-sig'))
        self.assertEqual(report.json()['rowCount'], 1)
        self.assertEqual(download['X-Content-SHA256'], report.json()['contentSha256'])
        original_snapshot = download.content
        Asset.objects.create(code='SNAPSHOT-LATER', name='导出后新增资产', zone='UT-ZA', asset_type='测试')
        repeated_download = self.client.get(f"/api/report-exports/{report.json()['id']}/download/")
        self.assertEqual(repeated_download.content, original_snapshot)
        self.assertEqual(self.client.get('/api/report-exports/').status_code, 200)
        self.assertEqual(self.client.get('/api/assets/?pageSize=not-a-number').status_code, 400)
        self.assertEqual(self.client.get('/api/assets/?status=broken').status_code, 400)
        self.assertEqual(self.client.get('/api/assets/?integrationStatus=broken').status_code, 400)
        self.assertEqual(self.client.get('/api/assets/?hasLocation=maybe').status_code, 400)
        self.assertEqual(self.client.get('/api/assets/?isActive=maybe').status_code, 400)
        self.assertEqual(self.client.get('/api/alerts/?severity=blocker').status_code, 400)
        self.assertEqual(self.client.get('/api/alerts/?openedFrom=not-a-date').status_code, 400)
        self.assertEqual(self.client.get('/api/alerts/?openedFrom=2026-08-27T00:00:00Z&openedTo=2026-08-26T00:00:00Z').status_code, 400)
        self.assertEqual(self.client.get('/api/work-orders/?updatedFrom=not-a-date').status_code, 400)
        page = self.client.get('/api/assets/?page=1&pageSize=1').json()
        self.assertEqual(page['pageCount'], 2)
        self.assertTrue(page['hasNext'])

    def test_twin_model_readiness_requires_asset_mapping_and_an_active_release(self):
        self.assertEqual(self.client.get('/api/twin/model-readiness/').status_code, 401)
        self.auth(self.operator)
        blocked = self.client.get('/api/twin/model-readiness/')
        self.assertEqual(blocked.status_code, 200)
        self.assertEqual(blocked.json()['status'], 'blocked')
        self.assertEqual(blocked.json()['missingMeshCodes'], [self.asset.code])
        self.assertFalse(blocked.json()['contract']['modelFileVerified'])

        self.asset.mesh = 'MESH_FAN_01'
        self.asset.save(update_fields=['mesh', 'updated_at'])
        ready = self.client.get('/api/twin/model-readiness/')
        self.assertEqual(ready.status_code, 200)
        self.assertEqual(ready.json()['status'], 'blocked')
        self.assertEqual(ready.json()['summary'], {'activeAssetCount': 1, 'mappedAssetCount': 1, 'unmappedAssetCount': 0})
        self.assertEqual(ready.json()['missingMeshCodes'], [])
        self.assertIsNone(ready.json()['activeRelease'])

    @staticmethod
    def glb_upload(name='utility-tunnel.glb', payload=b'{"asset":{"version":"2.0"},"nodes":[{"name":"MESH_FAN_01"}]}'):
        payload += b' ' * (-len(payload) % 4)
        body = struct.pack('<I4s', len(payload), b'JSON') + payload
        content = struct.pack('<4sII', b'glTF', 2, 12 + len(body)) + body
        return SimpleUploadedFile(name, content, content_type='model/gltf-binary')

    def test_administrator_can_upload_activate_and_roll_back_validated_glb_releases(self):
        self.asset.mesh = 'MESH_FAN_01'
        self.asset.save(update_fields=['mesh', 'updated_at'])
        with tempfile.TemporaryDirectory() as media_root, override_settings(MEDIA_ROOT=media_root):
            self.auth(self.operator)
            forbidden = self.client.post('/api/twin/models/', {'version': 'r1', 'file': self.glb_upload()}, format='multipart')
            self.assertEqual(forbidden.status_code, 403)

            self.auth(self.admin)
            invalid = self.client.post('/api/twin/models/', {'version': 'r1', 'file': SimpleUploadedFile('bad.glb', b'not-a-glb')}, format='multipart')
            self.assertEqual(invalid.status_code, 400)
            malformed_scene = self.client.post('/api/twin/models/', {'version': 'broken-json', 'file': self.glb_upload(payload=b'{broken-json')}, format='multipart')
            self.assertEqual(malformed_scene.status_code, 400)
            empty_scene = self.client.post('/api/twin/models/', {'version': 'empty-scene', 'file': self.glb_upload(payload=b'{"asset":{"version":"2.0"},"nodes":[]}')}, format='multipart')
            self.assertEqual(empty_scene.status_code, 400)
            first = self.client.post('/api/twin/models/', {'version': 'r1', 'notes': '首次交付', 'file': self.glb_upload()}, format='multipart')
            self.assertEqual(first.status_code, 201)
            self.assertEqual(first.json()['status'], 'draft')
            self.assertEqual(len(first.json()['sha256']), 64)
            self.assertTrue(first.json()['isCompatible'])
            self.assertEqual(first.json()['nodeCount'], 1)
            self.assertEqual(first.json()['namedNodeCount'], 1)
            self.assertEqual(first.json()['nodeNames'], ['MESH_FAN_01'])
            self.assertTrue(first.json()['nodeInventoryAvailable'])
            self.assertEqual(first.json()['missingAssetCodes'], [])
            self.assertTrue(AuditLog.objects.filter(action='twin.model.uploaded', resource_id=str(first.json()['id'])).exists())

            duplicate = self.client.post('/api/twin/models/', {'version': 'r1-copy', 'file': self.glb_upload()}, format='multipart')
            self.assertEqual(duplicate.status_code, 409)
            activated = self.client.post(f"/api/twin/models/{first.json()['id']}/activate/")
            self.assertEqual(activated.status_code, 200)
            self.assertEqual(activated.json()['status'], 'active')
            first_file_url = activated.json()['fileUrl']
            self.client.credentials()
            self.assertEqual(self.client.get(first_file_url).status_code, 401)
            self.auth(self.admin)
            readiness = self.client.get('/api/twin/model-readiness/').json()
            self.assertEqual(readiness['status'], 'ready')
            self.assertTrue(readiness['contract']['modelFileVerified'])
            self.assertEqual(readiness['activeRelease']['version'], 'r1')
            self.assertTrue(readiness['contract']['modelNodeInventoryAvailable'])
            self.assertEqual(readiness['mappings'], [{'assetCode': self.asset.code, 'meshName': 'MESH_FAN_01', 'status': 'matched'}])
            model_file = self.client.get('/api/twin/model-file/')
            self.assertEqual(model_file.status_code, 200)
            self.assertEqual(b''.join(model_file.streaming_content)[:4], b'glTF')
            self.assertTrue(model_file.headers['ETag'].startswith('"'))

            incompatible = self.client.post('/api/twin/models/', {'version': 'incompatible', 'file': self.glb_upload(payload=b'{"asset":{"version":"2.0"},"nodes":[{"name":"OTHER_NODE"}]}')}, format='multipart')
            self.assertEqual(incompatible.status_code, 201)
            self.assertFalse(incompatible.json()['isCompatible'])
            self.assertEqual(incompatible.json()['missingAssetCodes'], [self.asset.code])
            blocked_activation = self.client.post(f"/api/twin/models/{incompatible.json()['id']}/activate/")
            self.assertEqual(blocked_activation.status_code, 409)
            self.assertEqual(blocked_activation.json()['error'], 'model_contract_failed')

            second = self.client.post('/api/twin/models/', {'version': 'r2', 'notes': '材质更新', 'file': self.glb_upload(payload=b'{"asset":{"version":"2.0"},"nodes":[{"name":"MESH_FAN_01"},{"name":"SCENE_ROOT"}]}')}, format='multipart')
            self.assertEqual(second.status_code, 201)
            self.assertEqual(self.client.post(f"/api/twin/models/{second.json()['id']}/activate/").status_code, 200)
            self.assertEqual(self.client.get(first_file_url).status_code, 404)
            first_release = TwinModelRelease.objects.get(pk=first.json()['id'])
            self.assertEqual(first_release.status, TwinModelRelease.Status.RETIRED)
            rollback = self.client.post(f"/api/twin/models/{first_release.pk}/activate/")
            self.assertEqual(rollback.status_code, 200)
            self.assertEqual(rollback.json()['status'], 'active')
            self.assertEqual(TwinModelRelease.objects.filter(status=TwinModelRelease.Status.ACTIVE).count(), 1)

    def test_model_readiness_rechecks_asset_mappings_after_activation(self):
        self.asset.mesh = 'MESH_FAN_01'
        self.asset.save(update_fields=['mesh', 'updated_at'])
        with tempfile.TemporaryDirectory() as media_root, override_settings(MEDIA_ROOT=media_root):
            self.auth(self.admin)
            created = self.client.post('/api/twin/models/', {'version': 'dynamic-contract', 'file': self.glb_upload()}, format='multipart')
            self.assertEqual(created.status_code, 201)
            self.assertEqual(self.client.post(f"/api/twin/models/{created.json()['id']}/activate/").status_code, 200)

            self.asset.mesh = 'MESH_FAN_RENAMED'
            self.asset.save(update_fields=['mesh', 'updated_at'])
            readiness = self.client.get('/api/twin/model-readiness/').json()
            self.assertEqual(readiness['status'], 'blocked')
            self.assertEqual(readiness['modelMismatchCodes'], [self.asset.code])
            self.assertEqual(readiness['mappings'][0]['status'], 'not_in_model')

            release = TwinModelRelease.objects.get(pk=created.json()['id'])
            release.status = TwinModelRelease.Status.RETIRED
            release.save(update_fields=['status'])
            blocked_reactivation = self.client.post(f'/api/twin/models/{release.pk}/activate/')
            self.assertEqual(blocked_reactivation.status_code, 409)
            self.assertEqual(blocked_reactivation.json()['details']['missingAssetCodes'], [self.asset.code])

            self.asset.mesh = 'MESH_FAN_01'
            self.asset.save(update_fields=['mesh', 'updated_at'])
            repaired_reactivation = self.client.post(f'/api/twin/models/{release.pk}/activate/')
            self.assertEqual(repaired_reactivation.status_code, 200)
            self.assertTrue(repaired_reactivation.json()['isCompatible'])
            self.assertEqual(repaired_reactivation.json()['missingAssetCodes'], [])

    def test_release_preflight_detects_and_cleans_reserved_browser_test_data(self):
        self.asset.mesh = 'MESH_FAN_01'
        self.asset.save(update_fields=['mesh', 'updated_at'])
        throttle_keys = [
            'throttle_login_burst_127.0.0.1',
            'throttle_registration_127.0.0.1',
            'throttle_password_setup_127.0.0.1',
        ]
        for key in throttle_keys:
            cache.set(key, [timezone.now().timestamp()], 3600)
        User.objects.create_user(username='e2e-operator-stale', email='e2e-operator-stale', password='test-only-password')
        shared_alert = Alert.objects.create(code='ALM-260826-001', asset=self.asset, severity=Alert.Severity.WARNING, category='通信', title='共享回归告警', detail='测试', opened_at=timezone.now(), status=Alert.Status.ACKNOWLEDGED, acknowledged_at=timezone.now(), acknowledged_by=self.operator)
        baseline = TwinModelRelease.objects.create(version='baseline', model_file='twin_models/baseline.glb', original_name='baseline.glb', sha256='a' * 64, size_bytes=1, is_compatible=True, status=TwinModelRelease.Status.RETIRED, uploaded_by=self.admin)
        TwinModelRelease.objects.create(version='e2e-model-stale', model_file='twin_models/e2e.glb', original_name='e2e.glb', sha256='b' * 64, size_bytes=1, is_compatible=True, status=TwinModelRelease.Status.ACTIVE, uploaded_by=self.admin)
        with self.assertRaises(CommandError):
            call_command('release_preflight', format='json', stdout=io.StringIO())

        output = io.StringIO()
        call_command('release_preflight', clean_test_data=True, format='json', stdout=output)
        self.assertFalse(User.objects.filter(email__startswith='e2e-operator-').exists())
        shared_alert.refresh_from_db()
        baseline.refresh_from_db()
        self.assertEqual(shared_alert.status, Alert.Status.OPEN)
        self.assertIsNone(shared_alert.acknowledged_at)
        self.assertEqual(baseline.status, TwinModelRelease.Status.ACTIVE)
        self.assertEqual(cache.get_many(throttle_keys), {})
        self.assertIn('"clean": true', output.getvalue())

    def test_dashboard_uses_the_latest_telemetry_reading(self):
        from .models import Telemetry

        Telemetry.objects.create(asset=self.asset, metric='temperature', value=31, unit='°C', quality=Telemetry.Quality.GOOD, recorded_at='2026-08-26T01:00:00Z')
        latest = Telemetry.objects.create(asset=self.asset, metric='temperature', value=35, unit='°C', quality=Telemetry.Quality.GOOD, recorded_at='2026-08-26T02:00:00Z')
        self.auth(self.operator)

        response = self.client.get('/api/dashboard/')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['telemetry']['id'], latest.id)

    def test_connectivity_uses_heartbeat_freshness_and_recovers_on_ingest(self):
        binding = HardwareBinding.objects.create(
            asset=self.asset,
            protocol=HardwareBinding.Protocol.MQTT,
            device_identifier='ut-fan-01',
            endpoint='ut/v1/fan-01/telemetry',
            expected_interval_seconds=10,
            status=HardwareBinding.Status.CONNECTED,
            last_heartbeat_at=timezone.now(),
        )
        self.auth(self.operator)
        self.assertEqual(self.client.get('/api/dashboard/').json()['assets']['online'], 1)

        binding.last_heartbeat_at = timezone.now() - timedelta(minutes=2)
        binding.save(update_fields=['last_heartbeat_at'])
        self.assertEqual(self.client.get('/api/dashboard/').json()['assets']['online'], 0)
        command_output = io.StringIO()
        call_command('reconcile_connectivity', stdout=command_output)
        self.asset.refresh_from_db()
        self.assertEqual(self.asset.status, Asset.Status.OFFLINE)
        communication_alert = Alert.objects.get(asset=self.asset, rule_key='connectivity.offline')
        self.assertEqual(communication_alert.status, Alert.Status.OPEN)

        ingested = self.client.post('/api/telemetry/', {'readings': [{
            'eventId': 'connectivity-recovery-1',
            'assetCode': self.asset.code,
            'metricKey': 'fan.feedback',
            'metric': '风机反馈',
            'value': 1,
            'unit': 'bool',
            'quality': 'good',
            'recordedAt': timezone.now().isoformat(),
        }]}, format='json')
        self.assertEqual(ingested.status_code, 201)
        binding.refresh_from_db()
        communication_alert.refresh_from_db()
        self.asset.refresh_from_db()
        self.assertEqual(binding.status, HardwareBinding.Status.CONNECTED)
        self.assertIsNotNone(binding.last_heartbeat_at)
        self.assertEqual(communication_alert.status, Alert.Status.RESOLVED)
        self.assertNotEqual(self.asset.status, Asset.Status.OFFLINE)
    def test_hardware_connectivity_uses_a_three_interval_heartbeat_grace_period(self):
        binding = HardwareBinding.objects.create(
            asset=self.asset,
            protocol=HardwareBinding.Protocol.MQTT,
            device_identifier='fan-controller-01',
            endpoint='ut/v1/fan-01/telemetry',
            expected_interval_seconds=60,
            status=HardwareBinding.Status.CONNECTED,
            last_heartbeat_at=timezone.now() - timedelta(seconds=90),
        )
        self.auth(self.operator)
        online = self.client.get('/api/hardware-bindings/').json()['items'][0]
        self.assertEqual(online['connectivity'], 'online')
        self.assertGreaterEqual(online['heartbeatAgeSeconds'], 89)
        self.assertIsNotNone(online['heartbeatDueAt'])
        self.assertEqual(self.client.get('/api/dashboard/').json()['connections']['online'], 1)

        binding.last_heartbeat_at = timezone.now() - timedelta(seconds=181)
        binding.save(update_fields=['last_heartbeat_at'])
        offline = self.client.get('/api/hardware-bindings/').json()['items'][0]
        self.assertEqual(offline['connectivity'], 'offline')
        dashboard = self.client.get('/api/dashboard/').json()['connections']
        self.assertEqual(dashboard['online'], 0)
        self.assertEqual(dashboard['offline'], 1)

    def test_work_order_sla_status_and_filters_are_consistent(self):
        now = timezone.now()
        overdue = WorkOrder.objects.create(code='WO-SLA-OVERDUE', asset=self.asset, title='超时工单', priority=WorkOrder.Priority.HIGH, status=WorkOrder.Status.IN_PROGRESS, due_at=now - timedelta(minutes=15), created_by=self.operator)
        due_soon = WorkOrder.objects.create(code='WO-SLA-SOON', asset=self.asset, title='临期工单', priority=WorkOrder.Priority.URGENT, status=WorkOrder.Status.OPEN, due_at=now + timedelta(hours=2), created_by=self.operator)
        WorkOrder.objects.create(code='WO-SLA-TRACK', asset=self.asset, title='正常工单', priority=WorkOrder.Priority.NORMAL, status=WorkOrder.Status.OPEN, due_at=now + timedelta(hours=12), created_by=self.operator)
        self.auth(self.operator)

        items = {item['id']: item for item in self.client.get('/api/work-orders/?pageSize=10').json()['items']}
        self.assertEqual(items[overdue.id]['slaStatus'], 'overdue')
        self.assertLess(items[overdue.id]['remainingMinutes'], 0)
        self.assertEqual(items[due_soon.id]['slaStatus'], 'due_soon')
        self.assertGreater(items[due_soon.id]['remainingMinutes'], 0)
        self.assertEqual(self.client.get('/api/work-orders/?sla=overdue').json()['total'], 1)
        self.assertEqual(self.client.get('/api/work-orders/?sla=dueSoon').json()['total'], 1)
        self.assertEqual(self.client.get('/api/work-orders/?sla=onTrack').json()['total'], 1)
        self.assertEqual(self.client.get('/api/work-orders/?sla=invalid').status_code, 400)

    def test_telemetry_history_filters_by_business_time_and_summarizes_quality(self):
        now = timezone.now()
        newest = Telemetry.objects.create(asset=self.asset, event_id='history-newest', metric_key='temperature', metric='环境温度', value=32, unit='°C', quality=Telemetry.Quality.GOOD, recorded_at=now)
        Telemetry.objects.create(asset=self.asset, event_id='history-oldest', metric_key='temperature', metric='环境温度', value=24, unit='°C', quality=Telemetry.Quality.SUSPECT, recorded_at=now - timedelta(minutes=10))
        Telemetry.objects.create(asset=self.asset, event_id='history-other', metric_key='humidity', metric='环境湿度', value=60, unit='%RH', quality=Telemetry.Quality.GOOD, recorded_at=now - timedelta(minutes=5))
        self.auth(self.operator)
        recorded_from = (now - timedelta(hours=1)).isoformat().replace('+00:00', 'Z')
        recorded_to = (now + timedelta(minutes=1)).isoformat().replace('+00:00', 'Z')
        params = f'assetCode={self.asset.code}&metricKey=temperature&recordedFrom={recorded_from}&recordedTo={recorded_to}'

        history = self.client.get(f'/api/telemetry/?{params}&page=1&pageSize=10')
        summary = self.client.get(f'/api/telemetry/summary/?{params}')

        self.assertEqual(history.status_code, 200)
        self.assertEqual([item['id'] for item in history.json()['items']], [newest.id, newest.id + 1])
        self.assertEqual(summary.status_code, 200)
        self.assertEqual(summary.json()['sampleCount'], 2)
        self.assertTrue(summary.json()['comparable'])
        self.assertEqual(summary.json()['minimum'], 24)
        self.assertEqual(summary.json()['maximum'], 32)
        self.assertEqual(summary.json()['average'], 28)
        self.assertEqual(summary.json()['qualityCounts'], {'good': 1, 'suspect': 1, 'bad': 0, 'missing': 0})
        self.assertEqual(summary.json()['latest']['eventId'], 'history-newest')
        mixed = self.client.get(f'/api/telemetry/summary/?assetCode={self.asset.code}')
        self.assertFalse(mixed.json()['comparable'])
        self.assertIsNone(mixed.json()['average'])
        self.assertIsNone(mixed.json()['minimum'])

    def test_telemetry_history_rejects_invalid_filters_and_supports_empty_results(self):
        self.auth(self.operator)
        invalid_queries = [
            'assetCode=bad code',
            'metricKey=Temperature',
            'quality=unknown',
            'recordedFrom=not-a-date',
            'recordedFrom=2026-08-28T12:00:00Z&recordedTo=2026-08-28T11:00:00Z',
        ]
        for query in invalid_queries:
            self.assertEqual(self.client.get(f'/api/telemetry/?{query}').status_code, 400)
            self.assertEqual(self.client.get(f'/api/telemetry/summary/?{query}').status_code, 400)
        empty = self.client.get('/api/telemetry/summary/?assetCode=NOT-FOUND')
        self.assertEqual(empty.status_code, 200)
        self.assertEqual(empty.json()['sampleCount'], 0)
        self.assertTrue(empty.json()['comparable'])
        self.assertIsNone(empty.json()['average'])
        self.assertIsNone(empty.json()['latest'])

    def test_telemetry_batch_is_idempotent_and_creates_threshold_alert(self):
        asset = Asset.objects.create(code='ENV-T1', name='环境节点', zone='UT-ZA', asset_type='环境测点')
        Threshold.objects.create(key='temperature', label='环境温度', warning=28, alarm=32, unit='°C')
        self.auth(self.operator)
        recorded_at = timezone.now()
        reading = {'eventId': 'evt-temperature-1', 'assetCode': asset.code, 'metricKey': 'temperature', 'metric': '环境温度', 'value': 30, 'unit': '°C', 'quality': 'good', 'recordedAt': recorded_at.isoformat()}

        created = self.client.post('/api/telemetry/', {'readings': [reading]}, format='json', HTTP_X_REQUEST_ID='telemetry-batch-1')

        self.assertEqual(created.status_code, 201)
        self.assertEqual(created.json()['created'], 1)
        self.assertEqual(created.json()['rules']['created'], 1)
        self.assertEqual(created.json()['items'][0]['eventId'], reading['eventId'])
        self.assertEqual(created.json()['items'][0]['metricKey'], 'temperature')
        asset.refresh_from_db()
        self.assertEqual(asset.status, Asset.Status.WARNING)
        alert = Alert.objects.get(asset=asset, rule_key='temperature')
        self.assertEqual(alert.severity, Alert.Severity.WARNING)
        self.assertEqual(alert.last_observed_value, 30)
        self.assertTrue(AuditLog.objects.filter(action='alert.auto_created', resource_id=str(alert.pk)).exists())
        self.assertTrue(AuditLog.objects.filter(action='telemetry.batch_ingested', request_id='telemetry-batch-1').exists())

        duplicate = self.client.post('/api/telemetry/', {'readings': [reading]}, format='json')
        self.assertEqual(duplicate.status_code, 200)
        self.assertEqual(duplicate.json()['created'], 0)
        self.assertEqual(duplicate.json()['duplicates'], 1)
        self.assertEqual(Telemetry.objects.filter(event_id=reading['eventId']).count(), 1)
        conflict = self.client.post('/api/telemetry/', {'readings': [{**reading, 'value': 31}]}, format='json')
        self.assertEqual(conflict.status_code, 409)

    def test_threshold_alert_escalates_without_duplication_and_auto_resolves(self):
        asset = Asset.objects.create(code='ENV-T2', name='环境节点', zone='UT-ZA', asset_type='环境测点')
        Threshold.objects.create(key='temperature', label='环境温度', warning=28, alarm=32, unit='°C')
        self.auth(self.operator)
        now = timezone.now()

        def ingest(event_id, value, seconds):
            return self.client.post('/api/telemetry/', {'readings': [{'eventId': event_id, 'assetCode': asset.code, 'metricKey': 'temperature', 'metric': '环境温度', 'value': value, 'unit': '°C', 'quality': 'good', 'recordedAt': (now + timedelta(seconds=seconds)).isoformat()}]}, format='json')

        self.assertEqual(ingest('evt-rule-warning', 29, 0).json()['rules']['created'], 1)
        escalated = ingest('evt-rule-alarm', 34, 1)
        self.assertEqual(escalated.status_code, 201)
        self.assertEqual(escalated.json()['rules']['escalated'], 1)
        self.assertEqual(Alert.objects.filter(asset=asset, rule_key='temperature').count(), 1)
        alert = Alert.objects.get(asset=asset, rule_key='temperature')
        self.assertEqual(alert.severity, Alert.Severity.CRITICAL)
        asset.refresh_from_db()
        self.assertEqual(asset.status, Asset.Status.ALARM)

        deescalated = ingest('evt-rule-deescalated', 30, 2)
        self.assertEqual(deescalated.json()['rules']['deescalated'], 1)
        alert.refresh_from_db()
        asset.refresh_from_db()
        self.assertEqual(alert.severity, Alert.Severity.WARNING)
        self.assertEqual(asset.status, Asset.Status.WARNING)

        stale = ingest('evt-rule-stale', 35, 1.5)
        self.assertEqual(stale.json()['rules']['skipped_stale'], 1)
        alert.refresh_from_db()
        self.assertEqual(alert.severity, Alert.Severity.WARNING)

        resolved = ingest('evt-rule-normal', 25, 3)
        self.assertEqual(resolved.json()['rules']['resolved'], 1)
        alert.refresh_from_db()
        asset.refresh_from_db()
        self.assertEqual(alert.status, Alert.Status.RESOLVED)
        self.assertEqual(asset.status, Asset.Status.NORMAL)
        self.assertTrue(AuditLog.objects.filter(action='alert.auto_escalated').exists())
        self.assertTrue(AuditLog.objects.filter(action='alert.auto_deescalated').exists())
        self.assertTrue(AuditLog.objects.filter(action='alert.auto_resolved').exists())

    def test_telemetry_batch_validation_is_atomic_and_quality_can_skip_rules(self):
        asset = Asset.objects.create(code='ENV-T3', name='环境节点', zone='UT-ZA', asset_type='环境测点')
        Threshold.objects.create(key='temperature', label='环境温度', warning=28, alarm=32, unit='°C')
        now = timezone.now().isoformat()
        self.auth(self.operator)
        valid = {'eventId': 'evt-valid', 'assetCode': asset.code, 'metricKey': 'temperature', 'metric': '环境温度', 'value': 35, 'unit': '°C', 'quality': 'good', 'recordedAt': now}
        invalid_batch = self.client.post('/api/telemetry/', {'readings': [valid, {**valid, 'eventId': 'evt-missing', 'assetCode': 'MISSING-1'}]}, format='json')
        self.assertEqual(invalid_batch.status_code, 400)
        self.assertEqual(Telemetry.objects.filter(event_id='evt-valid').count(), 0)
        duplicate_batch = self.client.post('/api/telemetry/', {'readings': [valid, valid]}, format='json')
        self.assertEqual(duplicate_batch.status_code, 400)
        bad_quality = self.client.post('/api/telemetry/', {'readings': [{**valid, 'eventId': 'evt-bad-quality', 'quality': 'bad'}]}, format='json')
        self.assertEqual(bad_quality.status_code, 201)
        self.assertEqual(bad_quality.json()['rules']['skipped_quality'], 1)
        self.assertFalse(Alert.objects.filter(asset=asset, rule_key='temperature').exists())
        wrong_unit = self.client.post('/api/telemetry/', {'readings': [{**valid, 'eventId': 'evt-wrong-unit', 'unit': 'K'}]}, format='json')
        self.assertEqual(wrong_unit.status_code, 400)

        original = {**valid, 'eventId': 'evt-existing'}
        self.assertEqual(self.client.post('/api/telemetry/', {'readings': [original]}, format='json').status_code, 201)
        new_reading = {**valid, 'eventId': 'evt-must-rollback', 'value': 20}
        conflict = {**original, 'value': 31}
        conflicted_batch = self.client.post('/api/telemetry/', {'readings': [new_reading, conflict]}, format='json')
        self.assertEqual(conflicted_batch.status_code, 409)
        self.assertFalse(Telemetry.objects.filter(event_id='evt-must-rollback').exists())

    def test_viewer_cannot_ingest_telemetry(self):
        viewer = User.objects.create_user(username='telemetry-viewer@example.com', email='telemetry-viewer@example.com', password='demo-password')
        Profile.objects.create(user=viewer, display_name='查看者', role=Profile.Role.VIEWER)
        self.auth(viewer)
        self.assertEqual(self.client.post('/api/telemetry/', {'readings': []}, format='json').status_code, 403)
        self.assertIn('idempotency-key', settings.CORS_ALLOW_HEADERS)

    @override_settings(
        INGEST_API_KEY='test-ingest-key-that-is-at-least-thirty-two-characters',
        INGEST_PRINCIPAL_USERNAME='service-iotda-test',
    )
    def test_ingest_api_key_is_scoped_to_telemetry_post(self):
        call_command('configure_ingest_principal', verbosity=0)
        principal = User.objects.get(username='service-iotda-test')
        self.assertFalse(principal.has_usable_password())
        self.assertEqual(principal.profile.role, Profile.Role.INGEST)
        reading = {
            'eventId': 'evt-machine-principal',
            'assetCode': self.asset.code,
            'metricKey': 'vibration.alarm',
            'metric': '振动锁存',
            'value': 0,
            'unit': 'bool',
            'quality': 'good',
            'recordedAt': timezone.now().isoformat(),
        }
        self.client.credentials(HTTP_X_INGEST_KEY=settings.INGEST_API_KEY)
        created = self.client.post('/api/telemetry/', {'readings': [reading]}, format='json')
        self.assertEqual(created.status_code, 201)
        self.assertEqual(self.client.get('/api/telemetry/').status_code, 403)
        # The machine credential is installed only on the telemetry endpoint;
        # it must never become a human API session or reach mutation handlers.
        self.assertEqual(self.client.get('/api/auth/me/').status_code, 401)
        self.assertEqual(self.client.get('/api/assets/').status_code, 401)
        self.assertEqual(self.client.post(f'/api/alerts/{self.alert.pk}/acknowledge/').status_code, 401)
        self.assertEqual(self.client.post('/api/work-orders/', {
            'assetCode': self.asset.code,
            'title': '机器密钥不得创建工单',
        }, format='json').status_code, 401)
        self.assertEqual(self.client.get('/api/admin/users/').status_code, 401)
        self.client.credentials(HTTP_X_INGEST_KEY='wrong-key')
        self.assertEqual(self.client.post('/api/telemetry/', {'readings': [reading]}, format='json').status_code, 401)

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
        self.assertEqual(self.client.get('/api/audit/?occurredFrom=not-a-date').status_code, 400)
        self.assertEqual(self.client.get('/api/audit/?occurredFrom=2026-08-27T00:00:00Z&occurredTo=2026-08-26T00:00:00Z').status_code, 400)
        self.assertEqual(self.client.get('/api/audit/?occurredFrom=2026-08-26T00:00:00Z&occurredTo=2026-08-27T00:00:00Z').status_code, 200)

    def test_paginated_lists_are_newest_first(self):
        newer = Asset.objects.create(code='CTRL-02', name='控制器', zone='UT-ZA', asset_type='控制器')
        self.auth(self.operator)
        response = self.client.get('/api/assets/?page=1&pageSize=1')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['items'][0]['id'], newer.pk)

    def test_operator_can_acknowledge_alert(self):
        self.auth(self.operator)
        first = self.client.post(f'/api/alerts/{self.alert.pk}/acknowledge/')
        repeated = self.client.post(f'/api/alerts/{self.alert.pk}/acknowledge/')
        self.assertEqual(first.status_code, 200)
        self.assertEqual(repeated.status_code, 200)
        self.assertEqual(repeated.json()['status'], Alert.Status.ACKNOWLEDGED)
        self.assertEqual(AuditLog.objects.filter(action='alert.acknowledged', resource_id=str(self.alert.pk)).count(), 1)

    def test_completed_work_order_requires_admin(self):
        order = WorkOrder.objects.create(code='WO-1', asset=self.asset, title='测试工单', status=WorkOrder.Status.PENDING_REVIEW, created_by=self.operator)
        self.auth(self.operator)
        self.assertEqual(self.client.post(f'/api/work-orders/{order.pk}/transition/', {'to': WorkOrder.Status.COMPLETED}, format='json').status_code, 403)
        self.auth(self.admin)
        response = self.client.post(f'/api/work-orders/{order.pk}/transition/', {'to': WorkOrder.Status.COMPLETED, 'note': '复核通过，设备反馈恢复正常。'}, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['timeline'][0]['note'], '复核通过，设备反馈恢复正常。')

    def test_work_order_review_requires_note_and_exposes_timeline(self):
        order = WorkOrder.objects.create(code='WO-TIMELINE', asset=self.asset, title='处置留痕', status=WorkOrder.Status.IN_PROGRESS, created_by=self.operator)
        self.auth(self.operator)
        missing = self.client.post(f'/api/work-orders/{order.pk}/transition/', {'to': WorkOrder.Status.PENDING_REVIEW}, format='json')
        self.assertEqual(missing.status_code, 400)
        response = self.client.post(f'/api/work-orders/{order.pk}/transition/', {'to': WorkOrder.Status.PENDING_REVIEW, 'note': '已复位控制器并连续观察十分钟。'}, format='json')
        self.assertEqual(response.status_code, 200)
        event = response.json()['timeline'][0]
        self.assertEqual(event['fromStatus'], WorkOrder.Status.IN_PROGRESS)
        self.assertEqual(event['toStatus'], WorkOrder.Status.PENDING_REVIEW)
        self.assertEqual(event['actorName'], self.operator.email)

    def test_work_order_transition_rejects_stale_version(self):
        order = WorkOrder.objects.create(code='WO-VERSION', asset=self.asset, title='版本校验', status=WorkOrder.Status.OPEN, created_by=self.operator)
        self.auth(self.operator)
        response = self.client.post(f'/api/work-orders/{order.pk}/transition/', {'to': WorkOrder.Status.ASSIGNED, 'version': 99}, format='json')
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()['error'], 'version_conflict')
        order.refresh_from_db()
        self.assertEqual(order.status, WorkOrder.Status.OPEN)

    def test_linked_work_order_is_unique_per_alert(self):
        existing = WorkOrder.objects.create(code='WO-LINKED', source_alert=self.alert, asset=self.asset, title='已存在', created_by=self.operator)
        self.auth(self.operator)
        response = self.client.post(f'/api/alerts/{self.alert.pk}/work-order/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['id'], existing.pk)

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

    def test_work_order_deadlines_follow_priority_sla(self):
        self.auth(self.operator)
        before = timezone.now()
        manual = self.client.post('/api/work-orders/', {'assetCode': self.asset.code, 'title': '紧急处置', 'priority': 'urgent'}, format='json')
        self.assertEqual(manual.status_code, 201)
        urgent_due_at = datetime.fromisoformat(manual.json()['dueAt'].replace('Z', '+00:00'))
        self.assertGreaterEqual(urgent_due_at, before + timedelta(hours=3, minutes=59))
        self.assertLessEqual(urgent_due_at, before + timedelta(hours=4, minutes=1))
        linked = self.client.post(f'/api/alerts/{self.alert.pk}/work-order/')
        self.assertEqual(linked.status_code, 201)
        high_due_at = datetime.fromisoformat(linked.json()['dueAt'].replace('Z', '+00:00'))
        self.assertGreaterEqual(high_due_at, before + timedelta(hours=23, minutes=59))
        self.assertLessEqual(high_due_at, before + timedelta(hours=24, minutes=1))

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

    def test_report_export_concurrent_key_cannot_return_another_report_type(self):
        self.auth(self.operator)
        conflicting = SimpleNamespace(requested_by_id=self.operator.pk, report_type='assets')
        with patch('operations.views.ReportExport.objects.filter') as lookup, patch('operations.views._build_report_csv', side_effect=IntegrityError('concurrent key')):
            lookup.return_value.first.side_effect = [None, conflicting]
            response = self.client.post('/api/report-exports/', {'report': 'telemetry'}, format='json', HTTP_IDEMPOTENCY_KEY='racing-report')
        self.assertEqual(response.status_code, 409)
        self.assertEqual(ReportExport.objects.count(), 0)

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
        self.assertTrue(User.objects.get(username='admin').check_password('123'))
        self.assertEqual(Asset.objects.count(), 19)
        positions = list(Asset.objects.exclude(code__startswith='LEVEL-L').values_list('code', 'position'))
        self.assertEqual(len(positions), 14)
        self.assertEqual(len({tuple(sorted(position.items())) for _, position in positions}), 14)
        water = Asset.objects.get(hardware_code='H-04')
        self.assertEqual(water.integration_status, Asset.IntegrationStatus.CALIBRATION_REQUIRED)
        self.assertEqual(float(water.latitude), 31.230505)
        self.assertEqual(Asset.objects.filter(latitude__isnull=False, longitude__isnull=False).count(), 14)

    def test_e2e_cleanup_removes_legacy_and_timestamped_twin_test_assets(self):
        Asset.objects.create(code='ENV-E2E', name='旧版回归资产', zone='UT-ZA', asset_type='测试')
        Asset.objects.create(code='ENV-E2E-12345678', name='新版回归资产', zone='UT-ZA', asset_type='测试')
        call_command('seed_demo', '--clean-e2e-data', stdout=io.StringIO())
        self.assertFalse(Asset.objects.filter(code__startswith='ENV-E2E').exists())

    def test_asset_gis_filters_and_serialization(self):
        self.asset.hardware_code = 'H-10'
        self.asset.integration_status = Asset.IntegrationStatus.PENDING_VERIFICATION
        self.asset.latitude = 31.230630
        self.asset.longitude = 121.474125
        self.asset.location_source = Asset.LocationSource.CONFIGURED
        self.asset.capabilities = ['启停控制']
        self.asset.save()
        self.auth(self.operator)

        response = self.client.get('/api/assets/?hardwareCode=H-10&hasLocation=true&integrationStatus=pending_verification')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['total'], 1)
        item = response.json()['items'][0]
        self.assertEqual(item['hardwareCode'], 'H-10')
        self.assertEqual(item['latitude'], 31.23063)
        self.assertEqual(item['capabilities'], ['启停控制'])
        self.assertTrue(item['isActive'])
        self.assertEqual(item['version'], 1)

    def test_admin_can_create_and_version_asset_master_data(self):
        self.auth(self.admin)
        payload = {
            'code': 'TEMP-01',
            'hardwareCode': 'H-30',
            'name': '临时温度模块',
            'zone': 'UT-ZA',
            'type': '环境测点',
            'status': Asset.Status.NORMAL,
            'integrationStatus': Asset.IntegrationStatus.PENDING_VERIFICATION,
            'interface': 'PA2',
            'capabilities': ['温度采集'],
            'mesh': 'MESH_TEMP_01',
            'position': {'x': 42, 'y': 48, 'z': 0},
            'latitude': 31.2307,
            'longitude': 121.4743,
            'locationSource': Asset.LocationSource.CONFIGURED,
            'installationNote': '待接入。',
        }

        created = self.client.post('/api/assets/', payload, format='json')

        self.assertEqual(created.status_code, 201)
        self.assertEqual(created.json()['version'], 1)
        asset_id = created.json()['id']
        updated = self.client.patch(f'/api/assets/{asset_id}/', {'name': '温度模块 A', 'version': 1}, format='json')
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.json()['name'], '温度模块 A')
        self.assertEqual(updated.json()['version'], 2)
        self.assertEqual(self.client.patch(f'/api/assets/{asset_id}/', {'name': '过期写入', 'version': 1}, format='json').status_code, 409)
        self.assertEqual(AuditLog.objects.filter(resource_type='asset', resource_id=str(asset_id)).count(), 2)

    def test_asset_mutations_validate_coordinates_position_and_uniqueness(self):
        self.auth(self.admin)
        base = {'code': 'TEMP-01', 'name': '温度模块', 'zone': 'UT-ZA', 'type': '环境测点', 'integrationStatus': Asset.IntegrationStatus.PENDING_VERIFICATION, 'locationSource': Asset.LocationSource.UNASSIGNED}
        self.assertEqual(self.client.post('/api/assets/', {**base, 'latitude': 31.2}, format='json').status_code, 400)
        self.assertEqual(self.client.post('/api/assets/', {**base, 'position': {'x': 101}}, format='json').status_code, 400)
        self.assertEqual(self.client.post('/api/assets/', {**base, 'capabilities': ['温度', '温度']}, format='json').status_code, 400)
        first = self.client.post('/api/assets/', base, format='json')
        self.assertEqual(first.status_code, 201)
        self.assertEqual(self.client.post('/api/assets/', base, format='json').status_code, 409)
        self.assertEqual(self.client.patch(f"/api/assets/{first.json()['id']}/", {'version': 1}, format='json').status_code, 400)

    def test_asset_mutations_keep_3d_model_nodes_unique_and_normalized(self):
        self.auth(self.admin)
        base = {'code': 'TEMP-01', 'name': '温度模块', 'zone': 'UT-ZA', 'type': '环境测点', 'integrationStatus': Asset.IntegrationStatus.PENDING_VERIFICATION, 'locationSource': Asset.LocationSource.UNASSIGNED, 'mesh': 'mesh_temp_01'}
        created = self.client.post('/api/assets/', base, format='json')
        self.assertEqual(created.status_code, 201)
        self.assertEqual(created.json()['mesh'], 'MESH_TEMP_01')
        duplicate = self.client.post('/api/assets/', {**base, 'code': 'TEMP-02', 'mesh': 'MESH_TEMP_01'}, format='json')
        self.assertEqual(duplicate.status_code, 400)
        invalid = self.client.post('/api/assets/', {**base, 'code': 'TEMP-03', 'mesh': '模型 TEMP'}, format='json')
        self.assertEqual(invalid.status_code, 400)

    def test_asset_deactivation_requires_clear_operations_and_admin_role(self):
        self.auth(self.operator)
        self.assertEqual(self.client.patch(f'/api/assets/{self.asset.pk}/', {'isActive': False, 'version': 1}, format='json').status_code, 403)
        self.assertEqual(self.client.post('/api/assets/', {'code': 'NOPE-01'}, format='json').status_code, 403)
        self.assertEqual(self.client.get('/api/assets/?isActive=all').status_code, 403)

        self.auth(self.admin)
        blocked = self.client.patch(f'/api/assets/{self.asset.pk}/', {'isActive': False, 'version': 1}, format='json')
        self.assertEqual(blocked.status_code, 409)
        self.assertEqual(blocked.json()['error'], 'asset_in_use')
        self.alert.status = Alert.Status.RESOLVED
        self.alert.resolved_at = timezone.now()
        self.alert.save(update_fields=['status', 'resolved_at'])
        deactivated = self.client.patch(f'/api/assets/{self.asset.pk}/', {'isActive': False, 'version': 1}, format='json')
        self.assertEqual(deactivated.status_code, 200)
        self.assertFalse(deactivated.json()['isActive'])
        self.assertEqual(self.client.get('/api/assets/').json()['total'], 0)
        self.assertEqual(self.client.get('/api/assets/?isActive=all').json()['total'], 1)

    def test_dashboard_excludes_inactive_asset_master_data(self):
        self.asset.is_active = False
        self.asset.status = Asset.Status.ALARM
        self.asset.save(update_fields=['is_active', 'status'])
        self.auth(self.operator)
        response = self.client.get('/api/dashboard/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['assets'], {'total': 0, 'online': 0})
        self.assertEqual(response.json()['health']['value'], 100)

    def test_database_rejects_partial_or_out_of_range_gis_coordinates(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Asset.objects.create(code='BAD-COORD-1', name='错误坐标', zone='CTRL', asset_type='测试', latitude=31.2)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Asset.objects.create(code='BAD-COORD-2', name='错误坐标', zone='CTRL', asset_type='测试', latitude=91, longitude=121.4)

    def test_gis_features_are_governed_geojson_with_review_and_bbox_boundaries(self):
        self.auth(self.operator)
        self.assertEqual(self.client.get('/api/gis/features/').status_code, 200)
        self.assertEqual(self.client.post('/api/gis/features/', {}, format='json').status_code, 403)

        self.auth(self.admin)
        payload = {
            'code': 'SEG-01', 'name': 'A 区管廊段', 'layerType': 'tunnel_segment',
            'geometry': {'type': 'LineString', 'coordinates': [[121.473700, 31.230400], [121.473900, 31.230500]]},
            'source': 'surveyed', 'sourceReference': '2026 测绘成果 #01', 'accuracyM': '0.250', 'status': 'draft',
        }
        created = self.client.post('/api/gis/features/', payload, format='json')
        self.assertEqual(created.status_code, 201)
        self.assertEqual(self.client.get('/api/gis/features/').json()['meta']['count'], 0)
        # Neither endpoint is in this small viewport, but the line crosses it.
        # Spatial filtering must not silently omit that feature.
        all_features = self.client.get('/api/gis/features/?status=all&bbox=121.47379,31.23044,121.47381,31.23046')
        self.assertEqual(all_features.status_code, 200)
        self.assertEqual(all_features.json()['features'][0]['properties']['code'], 'SEG-01')
        rejected_publish = self.client.patch(f"/api/gis/features/{created.json()['id']}/", {'status': 'published', 'version': 1}, format='json')
        self.assertEqual(rejected_publish.status_code, 400)
        published = self.client.patch(f"/api/gis/features/{created.json()['id']}/", {'status': 'published', 'verifiedAt': timezone.now().isoformat(), 'version': 1}, format='json')
        self.assertEqual(published.status_code, 200)
        self.assertEqual(self.client.get('/api/gis/features/?bbox=121.4736,31.2303,121.4740,31.2306').json()['meta']['count'], 1)
        self.assertEqual(self.client.get('/api/gis/features/?bbox=121,31,120,32').status_code, 400)

    def test_gis_import_is_atomic_and_hardware_bindings_reserve_future_interfaces(self):
        self.auth(self.admin)
        feature = {
            'type': 'Feature', 'geometry': {'type': 'Point', 'coordinates': [121.4737, 31.2304]},
            'properties': {'code': 'MH-01', 'name': '一号井口', 'layerType': 'manhole', 'source': 'cad_import', 'sourceReference': '管廊总图 V1', 'status': 'draft'},
        }
        imported = self.client.post('/api/gis/features/import/', {'type': 'FeatureCollection', 'features': [feature]}, format='json')
        self.assertEqual(imported.status_code, 201)
        self.assertEqual(SpatialFeature.objects.count(), 1)
        conflict = self.client.post('/api/gis/features/import/', {'type': 'FeatureCollection', 'features': [feature, feature]}, format='json')
        self.assertEqual(conflict.status_code, 409)
        self.assertEqual(SpatialFeature.objects.count(), 1)
        binding = self.client.post('/api/hardware-bindings/', {'assetCode': self.asset.code, 'protocol': 'mqtt', 'deviceIdentifier': 'ctrl-gateway-01', 'endpoint': 'ut/v1/fan-01/telemetry', 'expectedIntervalSeconds': 30, 'status': 'reserved'}, format='json')
        self.assertEqual(binding.status_code, 201)
        self.assertEqual(binding.json()['assetCode'], self.asset.code)
        self.assertEqual(binding.json()['deviceIdentifier'], 'ctrl-gateway-01')
        self.assertEqual(HardwareBinding.objects.get(asset=self.asset).status, HardwareBinding.Status.RESERVED)

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
        self.assertEqual(HardwareBinding.objects.filter(status=HardwareBinding.Status.RESERVED).count(), 19)
