"""Bounded MQTT dispatch for explicitly approved controller actions."""

import json
import threading
from typing import Any

from django.conf import settings
import paho.mqtt.client as mqtt


class CommandDispatchError(RuntimeError):
    """The command could not be safely handed to the local broker."""


ACK_STATUSES = {'accepted', 'rejected', 'duplicate', 'expired'}


def matching_command_ack(payload: Any, command_id: str) -> dict[str, Any] | None:
    """Ignore malformed or unrelated MQTT frames instead of reporting an acknowledgement."""
    if not isinstance(payload, dict):
        return None
    status = payload.get('status')
    if (payload.get('schema') != 'ut.command.ack.v1' or payload.get('cmdId') != command_id
            or not isinstance(status, str) or status not in ACK_STATUSES
            or not isinstance(payload.get('reason'), str)):
        return None
    return payload


def publish_controller_command(command: dict[str, Any]) -> dict[str, Any] | None:
    """Publish one command and return its matching acknowledgement when available."""
    command_id = command['cmdId']
    ack_topic = 'ut/v1/CTRL-01/cmd_ack'
    connected = threading.Event()
    subscribed = threading.Event()
    acknowledged = threading.Event()
    callback_error: list[str] = []
    received_ack: list[dict[str, Any]] = []
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f'ut-platform-{command_id[-12:]}')
    if settings.MQTT_COMMAND_USERNAME:
        client.username_pw_set(settings.MQTT_COMMAND_USERNAME, settings.MQTT_COMMAND_PASSWORD)

    def on_connect(mqtt_client, _userdata, _flags, reason_code, _properties):
        connection_code = getattr(reason_code, 'value', reason_code)
        if connection_code != 0:
            callback_error.append(f'broker connection rejected ({reason_code})')
            connected.set()
            return
        result, _mid = mqtt_client.subscribe(ack_topic, qos=1)
        if result != mqtt.MQTT_ERR_SUCCESS:
            callback_error.append('could not subscribe to controller acknowledgement topic')
        connected.set()

    def on_subscribe(_mqtt_client, _userdata, _mid, granted_qos, _properties):
        if not granted_qos:
            callback_error.append('broker rejected acknowledgement subscription')
        subscribed.set()

    def on_message(_mqtt_client, _userdata, message):
        try:
            payload = json.loads(message.payload.decode('utf-8'))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return
        ack = matching_command_ack(payload, command_id)
        if ack is not None:
            received_ack.append(ack)
            acknowledged.set()

    client.on_connect = on_connect
    client.on_subscribe = on_subscribe
    client.on_message = on_message
    timeout = settings.MQTT_COMMAND_ACK_TIMEOUT_SECONDS
    try:
        client.connect(settings.MQTT_COMMAND_BROKER_HOST, settings.MQTT_COMMAND_BROKER_PORT, keepalive=10)
        client.loop_start()
        if not connected.wait(timeout) or callback_error:
            raise CommandDispatchError(callback_error[0] if callback_error else 'broker connection timed out')
        if not subscribed.wait(timeout) or callback_error:
            raise CommandDispatchError(callback_error[0] if callback_error else 'acknowledgement subscription timed out')
        info = client.publish('ut/v1/CTRL-01/cmd', json.dumps(command, separators=(',', ':')), qos=1, retain=False)
        if info.rc != mqtt.MQTT_ERR_SUCCESS:
            raise CommandDispatchError('broker did not accept the command publish')
        info.wait_for_publish(timeout=timeout)
        if not info.is_published():
            raise CommandDispatchError('broker did not confirm the command publish')
        acknowledged.wait(timeout)
        return received_ack[0] if received_ack else None
    except OSError as exc:
        raise CommandDispatchError('could not connect to the local command broker') from exc
    finally:
        client.loop_stop()
        client.disconnect()
