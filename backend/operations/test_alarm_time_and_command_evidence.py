"""Real API audit-to-diagnosis and temporal alarm regression; all transport mocked."""
from datetime import timedelta
from unittest.mock import patch
from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient
from .agent_operations import diagnose_station
from .models import Alert, Asset, AuditLog, HardwareBinding, Profile, Telemetry, Threshold


@override_settings(CONTROLLER_COMMAND_PROTOCOL='four-controller-v2', AGENT_EVALUATION_MODE=False)
class FourControllerAuditDiagnosisTests(TestCase):
    def setUp(self):
        cache.clear()
        self.now = timezone.now()
        self.user = User.objects.create_user(username='audit-to-diagnosis')
        Profile.objects.create(user=self.user, display_name='operator', role=Profile.Role.OPERATOR)
        self.client = APIClient(); self.client.force_authenticate(self.user)
        for code in ['CTRL-02', 'CTRL-03', 'CTRL-04', 'FAN-01', 'FAN-02', 'LED-01', 'BUZZ-01']:
            asset = Asset.objects.create(code=code, name=code, zone='control', asset_type='device')
            HardwareBinding.objects.create(asset=asset, protocol='mqtt', device_identifier=code,
                endpoint='test', expected_interval_seconds=2, status='connected', last_heartbeat_at=self.now)

    def dispatch(self, controller, action, value=None, outcome='accepted'):
        body = {'action': action}
        if value is not None:
            body['dutyPercent'] = value
        confirmation = self.client.post(f'/api/controllers/{controller}/commands/confirmations/', body, format='json')
        self.assertEqual(confirmation.status_code, 201, confirmation.data)
        body['confirmationToken'] = confirmation.data['confirmationToken']
        def reply(command):
            return {'schema': 'ut.command-ack.v2', 'cmdId': command['cmdId'], 'controllerId': controller,
                    'status': outcome, 'reason': 'outputs_applied_feedback_required' if outcome == 'accepted' else 'local_protection',
                    'physicalStateVerified': False}
        with patch('operations.views.publish_controller_command', side_effect=reply):
            result = self.client.post(f'/api/controllers/{controller}/commands/', body, format='json')
        self.assertEqual(result.status_code, 201, result.data)

    def fact(self, code='FAN-01'):
        return next(f for f in diagnose_station('P5')['diagnosis']['facts'] if f['assetCode'] == code)

    def test_pwm_and_supply_audits_reach_diagnosis_without_becoming_motion_proof(self):
        self.dispatch('CTRL-04', 'fan_pwm', 60)
        audit = AuditLog.objects.get(action='controller.command.sent')
        self.assertEqual((audit.detail['assetCode'], audit.detail['controllerId'], audit.detail['protocolVersion']),
                         ('FAN-01', 'CTRL-04', 'four-controller-v2'))
        fact = self.fact()
        self.assertEqual(fact['commandIntent'], 'fan.pwm')
        self.assertEqual(fact['commandValue'], 60)
        self.assertEqual(fact['commandOutcome'], 'accepted')
        self.assertTrue(fact['outputsApplied'])
        self.assertTrue(fact['commandLeaseActive'])
        self.assertEqual(fact['movementState'], 'unknown')
        self.assertIsNone(fact['rpm'])
        self.dispatch('CTRL-04', 'relay_on')
        fact = self.fact()
        self.assertEqual(fact['commandIntent'], 'fan.power_on')
        self.assertEqual(fact['commandValue'], 1)
        self.assertEqual(fact['movementState'], 'unknown')
        self.assertIn('独立', fact['controlBoundary'])

    def test_rejected_output_and_expired_lease_cannot_be_treated_as_running(self):
        self.dispatch('CTRL-02', 'fan2_pwm', 100, outcome='rejected')
        fact = self.fact('FAN-02')
        self.assertFalse(fact['outputsApplied'])
        self.assertEqual(fact['commandOutcome'], 'rejected')
        self.assertEqual(fact['movementState'], 'unknown')
        row = AuditLog.objects.get(action='controller.command.sent')
        row.detail['issuedAtMs'] -= 20000
        row.save(update_fields=['detail'])
        self.assertFalse(self.fact('FAN-02')['commandLeaseActive'])

    def test_fresh_independent_rpm_is_required_for_motion_state(self):
        self.dispatch('CTRL-04', 'relay_on')
        fan = Asset.objects.get(code='FAN-01')
        row = Telemetry.objects.create(asset=fan, event_id='actual-rpm', metric_key='rotational.speed',
            metric='RPM', value=1200, unit='rpm', quality='good', recorded_at=timezone.now()-timedelta(seconds=1))
        self.assertEqual(self.fact()['movementState'], 'observed_rotating')
        row.quality = 'bad'; row.save(update_fields=['quality'])
        self.assertEqual(self.fact()['movementState'], 'unknown')
        row.quality = 'good'; row.value = 0
        row.save(update_fields=['quality', 'value'])
        self.assertEqual(self.fact()['movementState'], 'observed_zero_rpm')

    def test_led_and_buzzer_audits_identify_the_output_and_owner(self):
        self.dispatch('CTRL-03', 'led_blue')
        self.dispatch('CTRL-03', 'buzzer_on')
        rows = list(AuditLog.objects.filter(action='controller.command.sent').order_by('id'))
        self.assertEqual([row.detail['assetCode'] for row in rows], ['LED-01', 'BUZZ-01'])
        self.assertEqual([row.detail['commandIntent'] for row in rows], ['led.set', 'buzzer.set'])
        self.assertTrue(all(row.detail['controllerId'] == 'CTRL-03' and
                            row.detail['protocolVersion'] == 'four-controller-v2' for row in rows))

    def test_legacy_shared_relay_record_is_not_new_layout_command_evidence(self):
        AuditLog.objects.create(actor=self.user, action='controller.command.sent', resource_type='asset',
            resource_id='CTRL-01', detail={'action': 'relay_on', 'outcome': 'accepted'})
        self.assertIsNone(self.fact()['commandIntent'])
        # Earlier explicit four-controller v1 evidence remains recognized.
        AuditLog.objects.create(actor=self.user, action='controller.command.sent', resource_type='asset',
            resource_id='CTRL-04', detail={'action': 'fan.start', 'assetCode': 'FAN-01',
                                         'protocolVersion': 'four-controller-v1', 'outcome': 'requested'})
        self.assertEqual(self.fact()['commandIntent'], 'fan.start')


@override_settings(DEVICE_OFFLINE_GRACE_MULTIPLIER=3, DEVICE_OFFLINE_MIN_GRACE_SECONDS=15)
class CurrentAlarmTimeTests(TestCase):
    def setUp(self):
        cache.clear()
        self.now = timezone.now()
        self.user = User.objects.create_user(username='current-alarm-ingest')
        Profile.objects.create(user=self.user, display_name='operator', role=Profile.Role.OPERATOR)
        self.client = APIClient(); self.client.force_authenticate(self.user)
        self.asset = Asset.objects.create(code='SMOKE-01', name='smoke', zone='P1', asset_type='sensor')
        self.binding = HardwareBinding.objects.create(asset=self.asset, protocol='mqtt',
            device_identifier='alarm-timing', endpoint='test', expected_interval_seconds=2,
            status='connected', last_heartbeat_at=self.now)
        Threshold.objects.create(key='smoke.alarm', label='smoke', warning=.5, alarm=1, unit='bool')

    def ingest(self, event, value, *, seconds=0, quality='good'):
        reading = {'eventId': event, 'assetCode': self.asset.code, 'metricKey': 'smoke.alarm',
                   'metric': 'smoke', 'value': value, 'unit': 'bool', 'quality': quality,
                   'recordedAt': (self.now+timedelta(seconds=seconds)).isoformat()}
        result = self.client.post('/api/telemetry/', {'readings': [reading]}, format='json')
        self.assertEqual(result.status_code, 201, result.data)
        return result.json()['rules']

    def test_future_expired_bad_missing_and_suspect_cannot_create_a_current_alarm(self):
        for event, seconds, quality, outcome in [
            ('future', 60, 'good', 'skipped_future'), ('historic', -16, 'good', 'skipped_expired'),
            ('bad', 0, 'bad', 'skipped_quality'), ('missing', 0, 'missing', 'skipped_quality'),
            ('suspect', 0, 'suspect', 'skipped_quality'),
        ]:
            self.assertEqual(self.ingest(event, 1, seconds=seconds, quality=quality), {outcome: 1})
        self.assertEqual(Telemetry.objects.count(), 5)
        self.assertEqual(Alert.objects.filter(rule_key='smoke.alarm').count(), 0)

    def test_future_expired_bad_missing_and_suspect_cannot_clear_a_current_alarm(self):
        self.assertEqual(self.ingest('real-alarm', 1, seconds=-1), {'created': 1})
        alarm = Alert.objects.get(rule_key='smoke.alarm')
        for event, seconds, quality in [('future-zero', 60, 'good'), ('historic-zero', -16, 'good'),
                                        ('bad-zero', 0, 'bad'), ('missing-zero', 0, 'missing'),
                                        ('suspect-zero', 0, 'suspect')]:
            self.ingest(event, 0, seconds=seconds, quality=quality)
            alarm.refresh_from_db(); self.asset.refresh_from_db()
            self.assertEqual(alarm.status, 'open')
            self.assertEqual(self.asset.status, 'alarm')
        self.assertEqual(self.ingest('real-recovery', 0, seconds=0), {'resolved': 1})
        alarm.refresh_from_db()
        self.assertEqual(alarm.status, 'resolved')

    def test_future_and_bad_rows_do_not_suppress_a_later_received_valid_alarm(self):
        self.ingest('future-poison', 0, seconds=60)
        self.ingest('bad-poison', 0, seconds=1, quality='bad')
        self.ingest('missing-poison', 0, seconds=1, quality='missing')
        self.ingest('suspect-poison', 0, seconds=1, quality='suspect')
        self.assertEqual(self.ingest('observed-alarm', 1), {'created': 1})
        self.assertEqual(Alert.objects.get(rule_key='smoke.alarm').status, 'open')

    def test_valid_newer_good_sample_still_wins_over_out_of_order_data(self):
        self.ingest('normal-newer', 0, seconds=-1)
        self.assertEqual(self.ingest('out-of-order', 1, seconds=-2), {'skipped_stale': 1})
        self.assertFalse(Alert.objects.filter(rule_key='smoke.alarm').exists())

    def test_explicit_future_tolerance_is_two_seconds(self):
        self.assertEqual(self.ingest('clock-small-skew', 1, seconds=1), {'created': 1})
        self.assertEqual(self.ingest('clock-too-far', 0, seconds=3), {'skipped_future': 1})
        self.assertEqual(Alert.objects.get(rule_key='smoke.alarm').status, 'open')

    def test_legacy_sixty_second_interval_and_unbound_default_are_respected(self):
        self.binding.expected_interval_seconds = 60
        self.binding.save(update_fields=['expected_interval_seconds'])
        self.assertEqual(self.ingest('legacy-within-grace', 1, seconds=-90), {'created': 1})
        self.binding.delete()
        # No binding: explicit 60-second freshness default.
        self.assertEqual(self.ingest('unbound-expired', 0, seconds=-61), {'skipped_expired': 1})
        self.assertEqual(self.ingest('unbound-recent', 0, seconds=-20), {'resolved': 1})
