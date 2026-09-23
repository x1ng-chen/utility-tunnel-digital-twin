from dataclasses import dataclass, field
from datetime import timedelta
from uuid import uuid4

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .models import Alert, Asset, HardwareBinding
from .services import audit
from .telemetry_rules import ACTIVE_ALERT_STATES, recompute_asset_status


CONNECTIVITY_RULE_KEY = 'connectivity.offline'


def binding_is_online(binding: HardwareBinding, now=None) -> bool:
    now = now or timezone.now()
    if binding.status != HardwareBinding.Status.CONNECTED:
        return False
    observed_at = binding.last_heartbeat_at or binding.asset.last_seen_at
    if not observed_at:
        return False
    grace_seconds = max(
        settings.DEVICE_OFFLINE_MIN_GRACE_SECONDS,
        binding.expected_interval_seconds * settings.DEVICE_OFFLINE_GRACE_MULTIPLIER,
    )
    return observed_at >= now - timedelta(seconds=grace_seconds)


def count_online_assets(now=None) -> int:
    now = now or timezone.now()
    bindings = HardwareBinding.objects.select_related('asset').filter(
        asset__is_active=True,
        status=HardwareBinding.Status.CONNECTED,
    )
    return sum(binding_is_online(binding, now) for binding in bindings)


@dataclass
class ConnectivityResult:
    online: int = 0
    offline: int = 0
    alerts_created: int = 0
    alerts_resolved: int = 0
    # These are internal hand-off values for post-commit browser fan-out.  They
    # intentionally expose identifiers rather than model instances, so the
    # callback reloads only committed state.
    changed_alert_ids: set[int] = field(default_factory=set)
    changed_asset_ids: set[int] = field(default_factory=set)


@dataclass
class ConnectivityChanges:
    """Connectivity mutations made while a telemetry batch is locked."""

    updated_bindings: int = 0
    changed_alert_ids: set[int] = field(default_factory=set)
    changed_asset_ids: set[int] = field(default_factory=set)


def schedule_connectivity_realtime_events(alert_ids, asset_ids) -> None:
    """Publish connectivity mutations only after the outer transaction commits.

    The live-event bus is intentionally process-local at present.  This helper
    does not attempt to turn it into an outbox or cross-process broker; it only
    preserves the existing delivery contract by ensuring clients cannot observe
    a connectivity change that is subsequently rolled back.
    """
    alert_ids = tuple(sorted(set(alert_ids)))
    asset_ids = tuple(sorted(set(asset_ids)))
    if not alert_ids and not asset_ids:
        return

    def publish_committed_changes():
        # Import lazily: REST-only Django commands still remain importable when
        # Channels is intentionally absent from a constrained environment.
        from .realtime import publish_alert_by_id, publish_asset

        for alert_id in alert_ids:
            publish_alert_by_id(alert_id)
        for asset in Asset.objects.filter(pk__in=asset_ids).order_by('pk'):
            publish_asset(asset)

    transaction.on_commit(publish_committed_changes)


def mark_assets_connected(assets, actor, request_id='', now=None) -> ConnectivityChanges:
    """Record receipt-time heartbeats and clear stale communication alerts."""
    now = now or timezone.now()
    asset_ids = [asset.pk for asset in assets]
    bindings = HardwareBinding.objects.select_for_update(of=('self',)).select_related('asset').filter(
        asset_id__in=asset_ids,
    ).exclude(status=HardwareBinding.Status.INACTIVE)
    changes = ConnectivityChanges()
    for binding in bindings:
        before_status = binding.asset.status
        binding.status = HardwareBinding.Status.CONNECTED
        binding.last_heartbeat_at = now
        binding.save(update_fields=['status', 'last_heartbeat_at', 'updated_at'])
        active = Alert.objects.select_for_update().filter(
            asset=binding.asset,
            rule_key=CONNECTIVITY_RULE_KEY,
            status__in=ACTIVE_ALERT_STATES,
        ).first()
        if active:
            active.status = Alert.Status.RESOLVED
            active.resolved_at = now
            active.detail = f'设备于 {now.isoformat()} 恢复上报。'
            active.save(update_fields=['status', 'resolved_at', 'detail'])
            audit(actor, 'alert.connectivity_resolved', 'alert', active.pk, {'assetCode': binding.asset.code}, request_id)
            changes.changed_alert_ids.add(active.pk)
        recompute_asset_status(binding.asset)
        if binding.asset.status != before_status:
            changes.changed_asset_ids.add(binding.asset.pk)
        changes.updated_bindings += 1
    return changes


def reconcile_connectivity(now=None) -> ConnectivityResult:
    """Persist connected/offline state and one deduplicated communication alert."""
    now = now or timezone.now()
    result = ConnectivityResult()
    with transaction.atomic():
        bindings = HardwareBinding.objects.select_for_update(of=('self',)).select_related('asset').filter(
            asset__is_active=True,
            status=HardwareBinding.Status.CONNECTED,
        ).order_by('pk')
        for binding in bindings:
            asset = binding.asset
            active = Alert.objects.select_for_update().filter(
                asset=asset,
                rule_key=CONNECTIVITY_RULE_KEY,
                status__in=ACTIVE_ALERT_STATES,
            ).first()
            if binding_is_online(binding, now):
                result.online += 1
                before_status = asset.status
                if active:
                    active.status = Alert.Status.RESOLVED
                    active.resolved_at = now
                    active.detail = f'设备于 {now.isoformat()} 恢复上报。'
                    active.save(update_fields=['status', 'resolved_at', 'detail'])
                    audit(None, 'alert.connectivity_resolved', 'alert', active.pk, {'assetCode': asset.code})
                    result.alerts_resolved += 1
                    result.changed_alert_ids.add(active.pk)
                recompute_asset_status(asset)
                if asset.status != before_status:
                    result.changed_asset_ids.add(asset.pk)
                continue

            result.offline += 1
            if asset.status != Asset.Status.OFFLINE:
                asset.status = Asset.Status.OFFLINE
                asset.save(update_fields=['status', 'updated_at'])
                result.changed_asset_ids.add(asset.pk)
            if not active:
                active = Alert.objects.create(
                    code=f'ALM-COMM-{timezone.now():%y%m%d}-{uuid4().hex[:6].upper()}',
                    asset=asset,
                    severity=Alert.Severity.WARNING,
                    category='通信状态',
                    status=Alert.Status.OPEN,
                    title=f'{asset.name} 通信中断',
                    detail=f'超过约定上报周期仍未收到数据；期望间隔 {binding.expected_interval_seconds} 秒。',
                    rule_key=CONNECTIVITY_RULE_KEY,
                    opened_at=now,
                )
                audit(None, 'alert.connectivity_created', 'alert', active.pk, {
                    'assetCode': asset.code,
                    'expectedIntervalSeconds': binding.expected_interval_seconds,
                })
                result.alerts_created += 1
                result.changed_alert_ids.add(active.pk)
    schedule_connectivity_realtime_events(result.changed_alert_ids, result.changed_asset_ids)
    return result
