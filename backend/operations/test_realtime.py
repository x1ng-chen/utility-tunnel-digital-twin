from asgiref.sync import async_to_sync
from channels.db import database_sync_to_async
from unittest.mock import patch
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from channels.layers import get_channel_layer
from channels.testing import WebsocketCommunicator
from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from config.asgi import application
from operations import realtime
from .models import Asset, Profile, Threshold
from .realtime import EVENTS_GROUP, publish_event, replay_since


ALLOWED_ORIGIN = 'http://127.0.0.1:5173'


def _reset_realtime_state():
    with realtime._seq_lock:
        realtime._seq_counter = 0
        realtime._buffer.clear()
    channel_layer = get_channel_layer()
    if channel_layer is not None:
        async_to_sync(channel_layer.flush)()


class RealtimeEventBusTests(TestCase):
    def setUp(self):
        _reset_realtime_state()

    def test_publish_assigns_monotonic_seq_and_replays(self):
        first = publish_event('telemetry', 1, 1, timezone.now(), {'value': 1})
        second = publish_event('telemetry', 2, 1, timezone.now(), {'value': 2})
        third = publish_event('alert', 3, 42, timezone.now(), {'status': 'open'})
        self.assertEqual([first['seq'], second['seq'], third['seq']], [1, 2, 3])
        self.assertEqual([event['seq'] for event in replay_since(0)], [1, 2, 3])
        self.assertEqual([event['seq'] for event in replay_since(1)], [2, 3])
        self.assertEqual([event['seq'] for event in replay_since(3)], [])
        self.assertEqual([event['type'] for event in replay_since(None)], ['telemetry', 'telemetry', 'alert'])
        self.assertEqual(first['entityId'], 1)
        self.assertEqual(first['updatedAt'] is not None, True)

    def test_publish_rejects_unknown_event_type(self):
        with self.assertRaises(ValueError):
            publish_event('bogus', 1, 1, timezone.now(), {})

    def test_replay_buffer_is_bounded(self):
        for index in range(realtime.REPLAY_BUFFER_SIZE + 10):
            publish_event('telemetry', index, 1, timezone.now(), {})
        events = replay_since(0)
        self.assertEqual(len(events), realtime.REPLAY_BUFFER_SIZE)
        self.assertEqual(events[0]['seq'], 11)
        self.assertEqual(realtime.replay_snapshot(realtime.STREAM_EPOCH, 0)[1], 'cursor_expired')

    def test_stream_reset_reasons(self):
        self.assertEqual(realtime.replay_snapshot(None, None)[1], 'initial')
        self.assertEqual(realtime.replay_snapshot('old-server', 0)[1], 'epoch_changed')
        self.assertEqual(realtime.replay_snapshot(realtime.STREAM_EPOCH, 99)[1], 'cursor_ahead')
        self.assertIsNone(realtime.replay_snapshot(realtime.STREAM_EPOCH, 0)[1])

    def test_concurrent_publish_keeps_buffer_in_sequence_order(self):
        with patch.object(realtime, '_channel_layer', return_value=None):
            with ThreadPoolExecutor(max_workers=8) as pool:
                list(pool.map(lambda n: publish_event('asset', n, 1, timezone.now(), {}), range(100)))
        self.assertEqual([item['seq'] for item in replay_since(0)], list(range(1, 101)))


@override_settings(WEBSOCKET_ALLOWED_ORIGINS=[ALLOWED_ORIGIN])
class EventsConsumerTests(TestCase):
    def setUp(self):
        _reset_realtime_state()
        self.user = User.objects.create_user(username='realtime@example.com', email='realtime@example.com', password='demo-password')
        self.token = Token.objects.create(user=self.user).key

    def _communicator(self, token=None, cursor=None, origin=ALLOWED_ORIGIN):
        path = '/ws/events/'
        headers = [(b'origin', origin.encode('utf-8'))] if origin is not None else []
        return WebsocketCommunicator(application, path, headers=headers)

    def test_rejects_missing_origin(self):
        async def scenario():
            communicator = self._communicator(token=self.token, origin=None)
            return await communicator.connect()
        connected, code = async_to_sync(scenario)()
        self.assertFalse(connected)
        self.assertEqual(code, 4403)

    def test_rejects_disallowed_origin(self):
        async def scenario():
            communicator = self._communicator(token=self.token, origin='https://evil.example.com')
            return await communicator.connect()
        connected, code = async_to_sync(scenario)()
        self.assertFalse(connected)
        self.assertEqual(code, 4403)

    def test_rejects_missing_token(self):
        with override_settings(WEBSOCKET_AUTH_TIMEOUT_SECONDS=0.02):
            async def scenario():
                communicator = self._communicator()
                self.assertTrue((await communicator.connect())[0])
                closed = await communicator.receive_output()
                await communicator.disconnect()
                return closed
            self.assertEqual(async_to_sync(scenario)()['code'], 4408)

    def test_rejects_query_credentials(self):
        async def scenario():
            communicator = WebsocketCommunicator(application, '/ws/events/?token=secret', headers=[(b'origin', ALLOWED_ORIGIN.encode())])
            return await communicator.connect()
        connected, code = async_to_sync(scenario)()
        self.assertFalse(connected)
        self.assertEqual(code, 4401)

    def test_rejects_invalid_token(self):
        async def scenario():
            communicator = self._communicator(token='not-a-real-token')
            self.assertTrue((await communicator.connect())[0])
            await communicator.send_json_to({'type': 'auth', 'token': 'bad'})
            closed = await communicator.receive_output()
            await communicator.disconnect()
            return closed
        self.assertEqual(async_to_sync(scenario)()['code'], 4401)

    def test_accepts_valid_token_and_replays_cursor(self):
        publish_event('telemetry', 1, 1, timezone.now(), {'value': 1})
        publish_event('telemetry', 2, 1, timezone.now(), {'value': 2})
        publish_event('alert', 3, 7, timezone.now(), {'status': 'open'})

        async def scenario():
            communicator = self._communicator(token=self.token, cursor=1)
            connected, _ = await communicator.connect()
            assert connected
            await communicator.send_json_to({'type': 'auth', 'token': self.token, 'cursor': 1, 'epoch': realtime.STREAM_EPOCH})
            self.assertEqual((await communicator.receive_json_from())['type'], 'hello')
            first = await communicator.receive_json_from()
            second = await communicator.receive_json_from()
            self.assertEqual((await communicator.receive_json_from())['type'], 'ready')
            await communicator.disconnect()
            return first, second
        first, second = async_to_sync(scenario)()
        self.assertEqual([first['seq'], second['seq']], [2, 3])
        self.assertEqual(first['type'], 'telemetry')
        self.assertEqual(second['type'], 'alert')

    def test_forwards_live_group_event_to_connected_client(self):
        async def scenario():
            communicator = self._communicator(token=self.token)
            connected, _ = await communicator.connect()
            assert connected
            await communicator.send_json_to({'type': 'auth', 'token': self.token})
            for expected in ['hello', 'reset', 'ready']:
                self.assertEqual((await communicator.receive_json_from())['type'], expected)
            layer = get_channel_layer()
            await layer.group_send(EVENTS_GROUP, {
                'type': 'events.forward',
                'event': {'seq': 9, 'type': 'workOrder', 'entityId': 4, 'version': 2, 'updatedAt': '2026-08-26T00:00:00Z', 'payload': {'status': 'open'}},
            })
            event = await communicator.receive_json_from()
            await communicator.disconnect()
            return event
        event = async_to_sync(scenario)()
        self.assertEqual(event['seq'], 9)
        self.assertEqual(event['type'], 'workOrder')
        self.assertEqual(event['entityId'], 4)

    def test_revoked_token_cannot_receive_event(self):
        async def scenario():
            communicator = self._communicator()
            await communicator.connect()
            await communicator.send_json_to({'type': 'auth', 'token': self.token})
            for _ in range(3):
                await communicator.receive_json_from()
            await database_sync_to_async(Token.objects.filter(key=self.token).delete)()
            await get_channel_layer().group_send(EVENTS_GROUP, {'type': 'events.forward', 'event': {'seq': 1}})
            result = await communicator.receive_output()
            await communicator.disconnect()
            return result
        self.assertEqual(async_to_sync(scenario)()['code'], 4401)

    def test_ingest_principal_cannot_read_global_feed(self):
        Profile.objects.create(user=self.user, role='ingest', display_name='gateway')
        async def scenario():
            communicator = self._communicator()
            await communicator.connect()
            await communicator.send_json_to({'type': 'auth', 'token': self.token})
            result = await communicator.receive_output()
            await communicator.disconnect()
            return result
        self.assertEqual(async_to_sync(scenario)()['code'], 4401)

    def test_disabled_user_cannot_receive_event(self):
        self._reject_after_change(lambda: User.objects.filter(pk=self.user.pk).update(is_active=False))

    def test_expired_token_cannot_receive_event(self):
        self._reject_after_change(lambda: Token.objects.filter(key=self.token).update(created=timezone.now() - timedelta(days=365)))

    def _reject_after_change(self, mutation):
        async def scenario():
            communicator = self._communicator()
            await communicator.connect()
            await communicator.send_json_to({'type': 'auth', 'token': self.token})
            for _ in range(3):
                await communicator.receive_json_from()
            await database_sync_to_async(mutation)()
            await get_channel_layer().group_send(EVENTS_GROUP, {'type': 'events.forward', 'event': {'seq': 1}})
            result = await communicator.receive_output()
            await communicator.disconnect()
            return result
        self.assertEqual(async_to_sync(scenario)()['code'], 4401)

    def test_invalid_json_closes_without_authentication(self):
        async def scenario():
            communicator = self._communicator()
            await communicator.connect()
            await communicator.send_to(text_data='{invalid')
            result = await communicator.receive_output()
            await communicator.disconnect()
            return result
        self.assertEqual(async_to_sync(scenario)()['code'], 4400)

    @override_settings(WEBSOCKET_AUTH_TIMEOUT_SECONDS=0.02, WEBSOCKET_AUTH_RECHECK_SECONDS=0.02)
    def test_idle_revocation_closes_without_waiting_for_event(self):
        async def scenario():
            communicator = self._communicator()
            await communicator.connect()
            await communicator.send_json_to({'type': 'auth', 'token': self.token})
            for _ in range(3):
                await communicator.receive_json_from()
            await database_sync_to_async(Token.objects.filter(key=self.token).delete)()
            result = await communicator.receive_output()
            await communicator.disconnect()
            return result
        self.assertEqual(async_to_sync(scenario)()['code'], 4401)


class RealtimeViewHookTests(TestCase):
    """Prove the view write-points actually feed the live-event bus."""

    def setUp(self):
        _reset_realtime_state()
        self.client = APIClient()
        self.operator = User.objects.create_user(username='realtime-op@example.com', email='realtime-op@example.com', password='demo-password')
        Profile.objects.create(user=self.operator, display_name='运维员', role=Profile.Role.OPERATOR)
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {Token.objects.create(user=self.operator).key}')
        self.asset = Asset.objects.create(code='FAN-01', name='风机', zone='UT-ZB', asset_type='执行器')

    def _reading(self, event_id, value):
        return {
            'eventId': event_id,
            'assetCode': self.asset.code,
            'metricKey': 'temperature',
            'metric': '环境温度',
            'value': value,
            'unit': '°C',
            'quality': 'good',
            'recordedAt': timezone.now().isoformat(),
        }

    def test_telemetry_ingest_publishes_telemetry_event(self):
        response = self.client.post('/api/telemetry/', {'readings': [self._reading('it-1', 25.0)]}, format='json')
        self.assertEqual(response.status_code, 201)
        events = replay_since(0)
        self.assertEqual([event['type'] for event in events], ['telemetry', 'asset'])
        self.assertEqual(events[0]['payload']['assetCode'], 'FAN-01')
        self.assertEqual(events[0]['payload']['value'], 25.0)
        self.assertEqual(events[1]['payload']['code'], 'FAN-01')
        self.assertIsNotNone(events[1]['payload']['lastSeenAt'])

    def test_breached_threshold_publishes_alert_event(self):
        Threshold.objects.create(key='temperature', label='环境温度', warning=28, alarm=32, unit='°C')
        response = self.client.post('/api/telemetry/', {'readings': [self._reading('it-2', 40.0)]}, format='json')
        self.assertEqual(response.status_code, 201)
        events = replay_since(0)
        self.assertEqual([event['type'] for event in events], ['telemetry', 'alert', 'asset'])
        self.assertEqual(events[1]['payload']['severity'], 'critical')
        self.assertEqual(events[2]['payload']['status'], 'alarm')
