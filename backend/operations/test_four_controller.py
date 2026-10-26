"""Four-node API/ACK boundaries and observation-time connectivity; no broker I/O."""
import json
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch
from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import TestCase, SimpleTestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient
from .command_dispatch import CommandDispatchError, publish_controller_command
from .command_policy import build_command
from .models import Asset, HardwareBinding, Profile, ControllerCommandConfirmation, Telemetry, Alert, Threshold
from .serializers import hardware_connectivity


@override_settings(CONTROLLER_COMMAND_PROTOCOL='four-controller-v2', AGENT_EVALUATION_MODE=False)
class FourControllerApiTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.operator = User.objects.create_user(username='four-operator')
        cls.viewer = User.objects.create_user(username='four-viewer')
        Profile.objects.create(user=cls.operator, display_name='operator', role=Profile.Role.OPERATOR)
        Profile.objects.create(user=cls.viewer, display_name='viewer', role=Profile.Role.VIEWER)
        for i in range(1, 5):
            Asset.objects.create(code=f'CTRL-0{i}', name='controller', zone='control', asset_type='controller')

    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.client.force_authenticate(self.operator)

    def issue(self, controller, action, duty=None):
        body = {'action': action}
        if duty is not None:
            body['dutyPercent'] = duty
        response = self.client.post(f'/api/controllers/{controller}/commands/confirmations/', body, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        return response.json()['confirmationToken']

    @patch('operations.views.publish_controller_command', return_value=None)
    def test_each_owner_dispatches_exact_seven_field_v2_contract(self, dispatch):
        cases = [('CTRL-04', 'fan_pwm', 60, 'fan', 60),
                 ('CTRL-02', 'fan2_pwm', 30, 'fan', 30),
                 ('CTRL-04', 'relay_on', None, 'relay', 1),
                 ('CTRL-02', 'relay_off', None, 'relay', 0),
                 ('CTRL-03', 'led_blue', None, 'led', 4),
                 ('CTRL-03', 'buzzer_on', None, 'buzzer', 1),
                 ('CTRL-02', 'auto', None, 'auto', 0)]
        for controller, action, duty, command, value in cases:
            with self.subTest(controller=controller, action=action):
                token = self.issue(controller, action, duty)
                body = {'action': action, 'confirmationToken': token}
                if duty is not None:
                    body['dutyPercent'] = duty
                response = self.client.post(f'/api/controllers/{controller}/commands/', body, format='json')
                self.assertEqual(response.status_code, 201, response.data)
                sent = dispatch.call_args.args[0]
                self.assertEqual(set(sent), {'schema', 'cmdId', 'controllerId', 'command', 'value', 'issuedAtMs', 'ttlMs'})
                self.assertEqual((sent['schema'], sent['controllerId'], sent['command'], sent['value']),
                                 ('ut.command.v2', controller, command, value))
                self.assertEqual(sent['ttlMs'], 10000)
                self.assertLess(abs(sent['issuedAtMs'] - int(timezone.now().timestamp() * 1000)), 2000)
        self.assertEqual(dispatch.call_count, len(cases))

    @patch('operations.views.publish_controller_command')
    def test_wrong_owners_and_unknown_controllers_cannot_issue_tokens(self, dispatch):
        for controller, action in [('CTRL-01', 'relay_on'), ('CTRL-02', 'fan_pwm'),
                                   ('CTRL-04', 'fan2_pwm'), ('CTRL-04', 'led_blue'), ('CTRL-03', 'relay_on')]:
            response = self.client.post(f'/api/controllers/{controller}/commands/confirmations/',
                                        {'action': action, 'dutyPercent': 30} if action.startswith('fan') else {'action': action}, format='json')
            self.assertEqual(response.status_code, 400)
        self.assertEqual(self.client.post('/api/controllers/CTRL-05/commands/confirmations/',
                                         {'action': 'relay_on'}, format='json').status_code, 404)
        self.assertEqual(ControllerCommandConfirmation.objects.count(), 0)
        dispatch.assert_not_called()

    @patch('operations.views.publish_controller_command', return_value=None)
    def test_confirmation_is_bound_to_target_and_is_consumed_once(self, dispatch):
        token = self.issue('CTRL-04', 'relay_on')
        body = {'action': 'relay_on', 'confirmationToken': token}
        self.assertEqual(self.client.post('/api/controllers/CTRL-02/commands/', body, format='json').status_code, 409)
        dispatch.assert_not_called()
        self.assertEqual(self.client.post('/api/controllers/CTRL-04/commands/', body, format='json').status_code, 201)
        self.assertEqual(self.client.post('/api/controllers/CTRL-04/commands/', body, format='json').status_code, 409)
        self.assertEqual(dispatch.call_count, 1)

    @patch('operations.views.publish_controller_command', side_effect=CommandDispatchError('uncertain broker'))
    def test_timeout_consumes_approval_and_never_retries_physical_write(self, dispatch):
        token = self.issue('CTRL-04', 'relay_off')
        body = {'action': 'relay_off', 'confirmationToken': token}
        self.assertEqual(self.client.post('/api/controllers/CTRL-04/commands/', body, format='json').status_code, 503)
        self.assertEqual(self.client.post('/api/controllers/CTRL-04/commands/', body, format='json').status_code, 409)
        self.assertEqual(dispatch.call_count, 1)

    @patch('operations.views.publish_controller_command')
    def test_invalid_types_ranges_and_unapproved_calls_do_not_dispatch(self, dispatch):
        for action in [[], {}, None, 1, True]:
            self.assertEqual(self.client.post('/api/controllers/CTRL-04/commands/confirmations/',
                                             {'action': action}, format='json').status_code, 400)
        for duty in [-1, 101, 256, True, 60.5, '60', [], {}]:
            self.assertEqual(self.client.post('/api/controllers/CTRL-04/commands/confirmations/',
                                             {'action': 'fan_pwm', 'dutyPercent': duty}, format='json').status_code, 400)
        self.assertEqual(self.client.post('/api/controllers/CTRL-04/commands/',
                                         {'action': 'relay_off'}, format='json').status_code, 409)
        self.assertEqual(ControllerCommandConfirmation.objects.count(), 0)
        dispatch.assert_not_called()

    @patch('operations.views.publish_controller_command')
    def test_permissions_and_evaluation_mode_still_block_hardware(self, dispatch):
        self.client.force_authenticate(self.viewer)
        self.assertEqual(self.client.post('/api/controllers/CTRL-04/commands/confirmations/',
                                         {'action': 'relay_on'}, format='json').status_code, 403)
        self.client.force_authenticate(self.operator)
        with override_settings(AGENT_EVALUATION_MODE=True, IS_PRODUCTION=False):
            self.assertTrue(self.client.get('/api/controllers/command-capabilities/').json()['controlDisabled'])
            for path in ['confirmations/', '']:
                self.assertEqual(self.client.post('/api/controllers/CTRL-04/commands/' + path,
                                                 {'action': 'relay_on'}, format='json').status_code, 403)
        dispatch.assert_not_called()

    def test_capabilities_and_legacy_mode_remain_explicit(self):
        result = self.client.get('/api/controllers/command-capabilities/').json()
        self.assertEqual(result['protocol'], 'four-controller-v2')
        self.assertEqual(result['controllers']['CTRL-01'], [])
        self.assertIn('fan_pwm', result['controllers']['CTRL-04'])
        self.assertEqual(result['manualLeaseMs'], 10000)
        with override_settings(CONTROLLER_COMMAND_PROTOCOL='legacy'):
            result = self.client.get('/api/controllers/command-capabilities/').json()
            self.assertEqual(set(result['controllers']), {'CTRL-01'})
            command = build_command('CTRL-01', 'fan_pwm', 60, 'legacy-1')
            self.assertEqual(command, {'schema': 'ut.command.v1', 'cmdId': 'legacy-1', 'action': 'fan_pwm',
                                      'ttlMs': 10000, 'dutyPercent': 60})
            self.assertEqual(self.client.post('/api/controllers/CTRL-04/commands/confirmations/',
                                             {'action': 'relay_on'}, format='json').status_code, 404)


@override_settings(DEVICE_OFFLINE_GRACE_MULTIPLIER=3, DEVICE_OFFLINE_MIN_GRACE_SECONDS=15)
class ObservationConnectivityTests(TestCase):
    def setUp(self):
        cache.clear()
        self.now = timezone.now()
        self.user = User.objects.create_user(username='observation-ingest')
        Profile.objects.create(user=self.user, display_name='operator', role=Profile.Role.OPERATOR)
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.asset = Asset.objects.create(code='FAN-01', name='fan', zone='tunnel', asset_type='actuator')
        self.binding = HardwareBinding.objects.create(asset=self.asset, protocol='mqtt',
            device_identifier='observed-fan', endpoint='ut/v1/CTRL-04/telemetry',
            expected_interval_seconds=10, status='connected', last_heartbeat_at=self.now - timedelta(hours=1))
        self.alert = Alert.objects.create(code='COMM-OBS', asset=self.asset, severity='warning',
            category='通信', title='offline', detail='', rule_key='connectivity.offline', opened_at=self.now - timedelta(hours=1))

    def reading(self, event_id, *, at=None, quality='good'):
        return {'eventId': event_id, 'assetCode': self.asset.code, 'metricKey': 'rotational.speed',
                'metric': 'RPM', 'value': 1200, 'unit': 'rpm', 'quality': quality,
                'recordedAt': (at or self.now).isoformat()}

    def post(self, reading):
        result = self.client.post('/api/telemetry/', {'readings': [reading]}, format='json')
        self.assertIn(result.status_code, (200, 201), result.data)
        self.binding.refresh_from_db()
        self.alert.refresh_from_db()
        return result

    def test_recent_sample_uses_observation_time_and_resolves_offline_alert(self):
        at = self.now - timedelta(seconds=4)
        self.post(self.reading('fresh', at=at))
        self.assertEqual(self.binding.last_heartbeat_at, at)
        self.assertEqual(hardware_connectivity(self.binding), 'online')
        self.assertEqual(self.alert.status, 'resolved')

    def test_bad_missing_future_and_stale_data_do_not_restore_online(self):
        before = self.binding.last_heartbeat_at
        for name, at, quality in [('bad', self.now, 'bad'), ('missing', self.now, 'missing'),
                                  ('future', self.now + timedelta(seconds=60), 'good'),
                                  ('stale', self.now - timedelta(seconds=31), 'good')]:
            with self.subTest(name=name):
                self.post(self.reading(name, at=at, quality=quality))
                self.assertEqual(self.binding.last_heartbeat_at, before)
                self.assertEqual(hardware_connectivity(self.binding), 'offline')
                self.assertEqual(self.alert.status, 'open')
        self.assertEqual(Telemetry.objects.count(), 4)

    def test_exact_replay_cannot_renew_heartbeat_or_resolve_a_new_offline_alert(self):
        frame = self.reading('original', at=self.now - timedelta(seconds=1))
        self.post(frame)
        self.binding.last_heartbeat_at = self.now - timedelta(hours=1)
        self.binding.save(update_fields=['last_heartbeat_at'])
        self.alert.status = 'open'; self.alert.resolved_at = None
        self.alert.save(update_fields=['status', 'resolved_at'])
        result = self.post(frame)
        self.assertEqual(result.json()['duplicates'], 1)
        self.assertEqual(self.binding.last_heartbeat_at, self.now - timedelta(hours=1))
        self.assertEqual(self.alert.status, 'open')
        self.assertEqual(hardware_connectivity(self.binding), 'offline')

    def test_source_time_policy_respects_legacy_reporting_interval(self):
        self.binding.expected_interval_seconds = 60
        self.binding.save(update_fields=['expected_interval_seconds'])
        at = self.now - timedelta(seconds=90)
        self.post(self.reading('legacy-interval', at=at, quality='suspect'))
        self.assertEqual(self.binding.last_heartbeat_at, at)
        self.assertEqual(hardware_connectivity(self.binding), 'online')

    def test_future_poisoned_prior_heartbeat_is_not_online_and_recovers_on_valid_data(self):
        self.binding.last_heartbeat_at = self.now + timedelta(hours=1)
        self.binding.save(update_fields=['last_heartbeat_at'])
        self.assertEqual(hardware_connectivity(self.binding), 'offline')
        self.post(self.reading('recovery'))
        self.assertEqual(self.binding.last_heartbeat_at, self.now)
        self.assertEqual(hardware_connectivity(self.binding), 'online')


class FakeMqtt:
    def __init__(self, replies=(), denied=False):
        self.replies = replies; self.denied = denied; self.published = []; self.subscription = None
    def username_pw_set(self, *_): pass
    def connect(self, *_args, **_kwargs): pass
    def loop_start(self): self.on_connect(self, None, None, 0, None)
    def subscribe(self, topic, qos):
        self.subscription = topic
        self.on_subscribe(self, None, 1, [128 if self.denied else 1], None)
        return 0, 1
    def publish(self, topic, payload, **kwargs):
        self.published.append((topic, json.loads(payload), kwargs))
        for message in self.replies: self.on_message(self, None, message)
        return SimpleNamespace(rc=0, wait_for_publish=lambda **_: None, is_published=lambda: True)
    def loop_stop(self): pass
    def disconnect(self): pass


@override_settings(MQTT_COMMAND_ACK_TIMEOUT_SECONDS=0.01)
class FourControllerDispatchTests(SimpleTestCase):
    def message(self, payload, *, topic='ut/v1/CTRL-04/cmd_ack', retain=False):
        return SimpleNamespace(topic=topic, payload=json.dumps(payload).encode(), retain=retain)
    def command(self):
        return {'schema': 'ut.command.v2', 'cmdId': 'test-4', 'controllerId': 'CTRL-04',
                'command': 'fan', 'value': 60, 'issuedAtMs': int(timezone.now().timestamp() * 1000), 'ttlMs': 10000}
    def ack(self, **changes):
        return {'schema': 'ut.command-ack.v2', 'cmdId': 'test-4', 'controllerId': 'CTRL-04',
                'status': 'accepted', 'reason': 'outputs_applied_feedback_required',
                'physicalStateVerified': False, **changes}

    def test_exact_topic_schema_target_id_and_receipt_shape_are_required(self):
        invalid = [self.message(self.ack(), topic='ut/v1/CTRL-02/cmd_ack'),
                   self.message(self.ack(schema='ut.command.ack.v1')),
                   self.message(self.ack(controllerId='CTRL-02')), self.message(self.ack(cmdId='other')),
                   self.message(self.ack(status=['accepted'])), self.message(self.ack(physicalStateVerified=True)),
                   self.message(self.ack(), retain=True), self.message([]),
                   SimpleNamespace(topic='ut/v1/CTRL-04/cmd_ack', payload=b'{broken', retain=False)]
        fake = FakeMqtt([*invalid, self.message(self.ack())])
        with patch('operations.command_dispatch.mqtt.Client', return_value=fake):
            self.assertEqual(publish_controller_command(self.command()), self.ack())
        self.assertEqual(fake.subscription, 'ut/v1/CTRL-04/cmd_ack')
        self.assertEqual(fake.published[0][0], 'ut/v1/CTRL-04/cmd')
        self.assertFalse(fake.published[0][2]['retain'])

    def test_only_invalid_receipts_return_unknown_and_do_not_republish(self):
        fake = FakeMqtt([self.message(self.ack(cmdId='other'))])
        with patch('operations.command_dispatch.mqtt.Client', return_value=fake):
            self.assertIsNone(publish_controller_command(self.command()))
        self.assertEqual(len(fake.published), 1)

    def test_broker_denied_ack_subscription_prevents_publish(self):
        fake = FakeMqtt(denied=True)
        with patch('operations.command_dispatch.mqtt.Client', return_value=fake):
            with self.assertRaises(CommandDispatchError):
                publish_controller_command(self.command())
        self.assertEqual(fake.published, [])



class LatchedObservationTests(TestCase):
    def setUp(self):
        cache.clear()
        self.now=timezone.now()
        self.user=User.objects.create_user(username='latched-ingest')
        Profile.objects.create(user=self.user,display_name='operator',role=Profile.Role.OPERATOR)
        self.client=APIClient();self.client.force_authenticate(self.user)
        self.asset=Asset.objects.create(code='MQ2-05',name='P5烟雾',zone='P5',asset_type='传感器',mesh='MQ2-05')
        HardwareBinding.objects.create(asset=self.asset,protocol='mqtt',endpoint='test',expected_interval_seconds=2,status='connected',last_heartbeat_at=self.now)
        Threshold.objects.create(key='smoke.alarm',label='烟雾事件',warning=.5,alarm=1,unit='bool')

    def frame(self,event='pulse',value=1,kind='latched_event',quality='good',offset=0):
        return {'eventId':event,'assetCode':self.asset.code,'metricKey':'smoke.alarm','metric':'烟雾告警','value':value,
                'unit':'bool','quality':quality,'recordedAt':(self.now+timedelta(seconds=offset)).isoformat(),'observationKind':kind}

    def test_observed_event_creates_localizable_alarm_and_persists_its_meaning(self):
        observed=self.frame(offset=-2)
        response=self.client.post('/api/telemetry/',{'readings':[observed]},format='json')
        self.assertEqual(response.status_code,201,response.data)
        self.assertEqual(response.data['items'][0]['observationKind'],'latched_event')
        alarm=Alert.objects.get(rule_key='smoke.alarm')
        self.assertEqual(alarm.asset.code,'MQ2-05')
        self.assertEqual(alarm.asset.mesh,'MQ2-05')
        self.assertIn('不表示输入此刻仍持续触发',alarm.detail)
        self.asset.refresh_from_db();self.assertEqual(self.asset.status,'alarm')
        from .agent_operations import snapshots
        result=snapshots(['MQ2-05'],self.now)['MQ2-05']['readings'][0]
        self.assertEqual(result['observation_kind'],'latched_event')
        self.assertIn('不表示',result['observation_note'])
        # Changing the meaning of the same evidence identifier is a conflict.
        observed['observationKind']='sample'
        self.assertEqual(self.client.post('/api/telemetry/',{'readings':[observed]},format='json').status_code,409)
        self.assertEqual(Telemetry.objects.count(),1)
        bad=self.frame('bad-zero',0,'sample','bad',1)
        self.client.post('/api/telemetry/',{'readings':[bad]},format='json')
        alarm.refresh_from_db();self.assertEqual(alarm.status,'open')
        normal=self.frame('new-zero',0,'sample','good',1)
        self.client.post('/api/telemetry/',{'readings':[normal]},format='json')
        alarm.refresh_from_db();self.assertEqual(alarm.status,'resolved')

    def test_invalid_held_observation_cannot_be_inserted_as_current_normal_or_analog_data(self):
        for change in [{'value':0},{'metricKey':'temperature','unit':'degC'}, {'observationKind':'unknown'}]:
            reading=self.frame();reading.update(change)
            response=self.client.post('/api/telemetry/',{'readings':[reading]},format='json')
            self.assertEqual(response.status_code,400,response.data)
        self.assertEqual(Telemetry.objects.count(),0)
