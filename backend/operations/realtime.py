"""Minimal Django -> browser live-event bus (WebSocket fan-out).

Scope is deliberately narrow: this module only pushes changes that Django has
already persisted, down to connected browser sessions. It never touches the
upstream MQTT/embedded ingestion path, the iotda-gateway, or any broker/server
credential.

Design notes
------------
* Each published event receives a process-wide monotonically increasing ``seq``
  and is kept in a bounded replay buffer. A reconnecting client sends
  ``cursor`` (the last ``seq`` it saw) and the consumer replays ``seq > cursor``.
* Delivery is fanned out through the Django Channels *in-memory* channel layer,
  so publishing (sync DRF views) and consuming (async ASGI consumers) MUST run
  in the same process. Serve the whole app with ``daphne config.asgi:application``
  (or uvicorn); do not split a WSGI worker from an ASGI worker. Redis/RabbitMQ
  are intentionally not introduced for this demonstration.
* A server restart changes the epoch. Initial, expired and foreign cursors
  receive explicit reset frames requiring full REST ``refreshLive()``.

Version policy (documented contract deviation)
----------------------------------------------
* ``telemetry``  -> ``version = 1`` (immutable, append-only rows).
* ``asset``      -> ``asset.version`` (bumped by every PATCH).
* ``workOrder``  -> ``order.version`` (bumped by create and every transition).
* ``alert``      -> string ``time.time_ns()`` version; Alert has no
                    ``version`` column and every mutation changes state.
The client must use ``entityId + version`` purely as an idempotency key and sort
by ``seq``; ``version`` must not be assumed to equal the API optimistic-lock
version for entities without that column.
"""
from __future__ import annotations

import logging
import threading
import time
import uuid
from collections import deque

from asgiref.sync import async_to_sync
from django.utils import timezone

logger = logging.getLogger('operations.realtime')

EVENTS_GROUP = 'live-events'
REPLAY_BUFFER_SIZE = 2000
ALLOWED_EVENT_TYPES = {'telemetry', 'alert', 'asset', 'workOrder'}

_seq_lock = threading.Lock()
_seq_counter = 0
STREAM_EPOCH = uuid.uuid4().hex
# Items are full framed events (already carry their own ``seq``).
_buffer: deque[dict] = deque(maxlen=REPLAY_BUFFER_SIZE)


def _iso(value) -> str | None:
    if value is None:
        return None
    return value.isoformat()


def build_event(event_type: str, entity_id, version, updated_at, payload: dict) -> dict:
    if event_type not in ALLOWED_EVENT_TYPES:
        raise ValueError(f'Unsupported realtime event type: {event_type}')
    return {
        'type': event_type,
        'entityId': entity_id,
        'version': version,
        'updatedAt': _iso(updated_at),
        'payload': payload,
    }


def _channel_layer():
    # Import lazily so the REST app can still boot without channels installed;
    # realtime fan-out simply degrades to the replay buffer in that case.
    try:
        from channels.layers import get_channel_layer
        return get_channel_layer()
    except ImportError:
        return None


def publish_event(event_type: str, entity_id, version, updated_at, payload: dict) -> dict | None:
    """Assign a monotonic seq, buffer the event, and fan it out to live clients.

    Returns the framed event (including ``seq``) or ``None`` when no channel
    layer is configured. Fan-out failures are logged; invalid event types
    raise ValueError so programming errors are not silently swallowed.
    """
    event = build_event(event_type, entity_id, version, updated_at, payload)
    global _seq_counter
    with _seq_lock:
        _seq_counter += 1
        seq = _seq_counter
        framed = {'epoch': STREAM_EPOCH, 'seq': seq, **event}
        _buffer.append(framed)
    channel_layer = _channel_layer()
    if channel_layer is None:
        return None
    try:
        async_to_sync(channel_layer.group_send)(
            EVENTS_GROUP,
            {'type': 'events.forward', 'event': framed},
        )
    except Exception:  # pragma: no cover - best-effort fan-out
        logger.warning('Realtime fan-out failed for seq=%s type=%s', seq, event_type, exc_info=True)
    return framed


def replay_since(cursor: int | None) -> list[dict]:
    """Return buffered events with ``seq > cursor`` in ascending seq order."""
    if cursor is None or cursor < 0:
        cursor = 0
    with _seq_lock:
        return [event for event in _buffer if event['seq'] > cursor]


def replay_snapshot(epoch, cursor):
    """Atomic cursor validation; reset requires a complete REST refresh."""
    with _seq_lock:
        oldest = _buffer[0]['seq'] if _buffer else _seq_counter + 1
        state = {'epoch': STREAM_EPOCH, 'seq': _seq_counter, 'oldestSeq': oldest}
        reason = None
        if epoch is None or cursor is None:
            reason = 'initial'
        elif epoch != STREAM_EPOCH:
            reason = 'epoch_changed'
        elif cursor > _seq_counter:
            reason = 'cursor_ahead'
        elif cursor < oldest - 1:
            reason = 'cursor_expired'
        events = [] if reason else [item for item in _buffer if item['seq'] > cursor]
        return state, reason, events


def _synthetic_version() -> str:
    """Monotonic-in-practice version for entities without a version column."""
    return str(time.time_ns())


def publish_telemetry(reading) -> dict | None:
    from .serializers import TelemetrySerializer
    return publish_event('telemetry', reading.pk, 1, reading.ingested_at, TelemetrySerializer(reading).data)


def publish_alert(alert) -> dict | None:
    from .serializers import AlertSerializer
    return publish_event('alert', alert.pk, _synthetic_version(), timezone.now(), AlertSerializer(alert).data)


def publish_alert_by_id(alert_id) -> dict | None:
    from .models import Alert
    alert = Alert.objects.select_related('asset').filter(pk=alert_id).first()
    return publish_alert(alert) if alert else None


def publish_asset(asset) -> dict | None:
    from .serializers import AssetSerializer
    return publish_event('asset', asset.pk, asset.version, asset.updated_at, AssetSerializer(asset).data)


def publish_work_order(order) -> dict | None:
    from .serializers import WorkOrderSerializer
    return publish_event('workOrder', order.pk, order.version, order.updated_at, WorkOrderSerializer(order).data)
