"""Authenticated process-local live feed. Tokens are never URL parameters."""
from __future__ import annotations

import asyncio
import json
from datetime import timedelta

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.conf import settings
from django.utils import timezone
from rest_framework.authtoken.models import Token

from .realtime import EVENTS_GROUP, replay_snapshot


@database_sync_to_async
def validate_bearer_token(token):
    if not isinstance(token, str) or len(token) != 40:
        return None
    record = Token.objects.select_related('user', 'user__profile').filter(key=token).first()
    if record is None or not record.user.is_active:
        return None
    if record.created + timedelta(seconds=settings.API_TOKEN_TTL_SECONDS) <= timezone.now():
        return None
    # Match REST AuthenticatedRead; machine ingest principals cannot subscribe.
    profile = getattr(record.user, 'profile', None)
    if profile and profile.role == 'ingest':
        return None
    return record.user


def _header(scope, name):
    for key, value in scope.get('headers', []):
        if key.lower() == name:
            return value.decode('utf-8', errors='replace')
    return None


class EventsConsumer(AsyncJsonWebsocketConsumer):
    async def receive(self, text_data=None, bytes_data=None, **kwargs):
        if text_data is None or len(text_data) > 4096:
            await self.close(code=4400)
            return
        try:
            content = json.loads(text_data)
        except (ValueError, TypeError):
            await self.close(code=4400)
            return
        await self.receive_json(content)

    async def connect(self):
        self.authenticated = False
        self.guard = None
        if _header(self.scope, b'origin') not in settings.WEBSOCKET_ALLOWED_ORIGINS:
            await self.close(code=4403)
            return
        if self.scope.get('query_string'):
            await self.close(code=4401)
            return
        await self.accept()
        self.guard = asyncio.create_task(self._watch_credentials())

    async def _watch_credentials(self):
        await asyncio.sleep(getattr(settings, 'WEBSOCKET_AUTH_TIMEOUT_SECONDS', 5))
        if not self.authenticated:
            await self.close(code=4408)
            return
        while self.authenticated:
            if not await validate_bearer_token(self.token):
                self.authenticated = False
                await self.channel_layer.group_discard(EVENTS_GROUP, self.channel_name)
                await self.close(code=4401)
                return
            await asyncio.sleep(getattr(settings, 'WEBSOCKET_AUTH_RECHECK_SECONDS', 5))

    async def receive_json(self, content, **kwargs):
        if self.authenticated or not isinstance(content, dict) or content.get('type') != 'auth':
            await self.close(code=4400)
            return
        cursor, epoch = content.get('cursor'), content.get('epoch')
        if (cursor is not None and (type(cursor) is not int or cursor < 0)) or (
            epoch is not None and (not isinstance(epoch, str) or len(epoch) > 64)
        ):
            await self.close(code=4400)
            return
        self.token = content.get('token')
        if not await validate_bearer_token(self.token):
            await self.close(code=4401)
            return
        self.authenticated = True
        await self.channel_layer.group_add(EVENTS_GROUP, self.channel_name)
        state, reason, events = replay_snapshot(epoch, cursor)
        await self.send_json({'type': 'hello', **state})
        if reason:
            await self.send_json({'type': 'reset', 'reason': reason, **state})
        else:
            for event in events:
                await self.send_json(event)
        await self.send_json({'type': 'ready', **state})

    async def disconnect(self, code):
        self.authenticated = False
        if self.guard:
            self.guard.cancel()
            try:
                await self.guard
            except asyncio.CancelledError:
                pass
        if self.channel_layer is not None:
            await self.channel_layer.group_discard(EVENTS_GROUP, self.channel_name)

    async def events_forward(self, event):
        if not self.authenticated:
            return
        if not await validate_bearer_token(self.token):
            self.authenticated = False
            await self.channel_layer.group_discard(EVENTS_GROUP, self.channel_name)
            await self.close(code=4401)
            return
        await self.send_json(event['event'])
