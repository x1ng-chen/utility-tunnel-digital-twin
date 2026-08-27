from dataclasses import dataclass
from typing import Optional
from uuid import uuid4

from django.utils import timezone

from .models import Alert, Asset, Telemetry, Threshold
from .services import audit


ACTIVE_ALERT_STATES = (Alert.Status.OPEN, Alert.Status.ACKNOWLEDGED)


@dataclass(frozen=True)
class RuleResult:
    action: str
    alert_id: Optional[int] = None


def evaluate_threshold(reading: Telemetry, threshold: Threshold, actor, request_id: str) -> RuleResult:
    """Apply one deterministic threshold rule while the caller holds the asset lock."""
    if reading.quality != Telemetry.Quality.GOOD:
        return RuleResult('skipped_quality')
    if Telemetry.objects.filter(
        asset=reading.asset,
        metric_key=threshold.key,
        recorded_at__gt=reading.recorded_at,
    ).exclude(pk=reading.pk).exists():
        return RuleResult('skipped_stale')

    rule_key = threshold.key
    active = Alert.objects.select_for_update().filter(
        asset=reading.asset,
        rule_key=rule_key,
        status__in=ACTIVE_ALERT_STATES,
    ).first()
    severity = Alert.Severity.CRITICAL if reading.value >= threshold.alarm else Alert.Severity.WARNING
    breached = reading.value >= threshold.warning
    detail = (
        f'{threshold.label} current value {reading.value:g}{reading.unit}; '
        f'warning {threshold.warning:g}{threshold.unit}, alarm {threshold.alarm:g}{threshold.unit}.'
    )

    if breached and active:
        previous_severity = active.severity
        active.severity = severity
        active.detail = detail
        active.last_observed_value = reading.value
        active.save(update_fields=['severity', 'detail', 'last_observed_value'])
        recompute_asset_status(reading.asset)
        if previous_severity != severity:
            escalated = severity == Alert.Severity.CRITICAL
            action = 'alert.auto_escalated' if escalated else 'alert.auto_deescalated'
            audit(actor, action, 'alert', active.pk, {'ruleKey': rule_key, 'from': previous_severity, 'to': severity, 'value': reading.value}, request_id)
            return RuleResult('escalated' if escalated else 'deescalated', active.pk)
        return RuleResult('suppressed_duplicate', active.pk)

    if breached:
        alert = Alert.objects.create(
            code=f'ALM-AUTO-{timezone.now():%y%m%d}-{uuid4().hex[:6].upper()}',
            asset=reading.asset,
            severity=severity,
            category=f'阈值规则 · {threshold.label}',
            status=Alert.Status.OPEN,
            title=f'{threshold.label}超过{ "报警" if severity == Alert.Severity.CRITICAL else "预警" }阈值',
            detail=detail,
            rule_key=rule_key,
            last_observed_value=reading.value,
            opened_at=reading.recorded_at,
        )
        recompute_asset_status(reading.asset)
        audit(actor, 'alert.auto_created', 'alert', alert.pk, {'ruleKey': rule_key, 'value': reading.value, 'severity': severity}, request_id)
        return RuleResult('created', alert.pk)

    if active:
        active.status = Alert.Status.RESOLVED
        active.resolved_at = reading.recorded_at
        active.last_observed_value = reading.value
        active.detail = detail
        active.save(update_fields=['status', 'resolved_at', 'last_observed_value', 'detail'])
        audit(actor, 'alert.auto_resolved', 'alert', active.pk, {'ruleKey': rule_key, 'value': reading.value}, request_id)
        recompute_asset_status(reading.asset)
        return RuleResult('resolved', active.pk)

    return RuleResult('normal')


def recompute_asset_status(asset: Asset) -> None:
    active_severities = Alert.objects.filter(
        asset=asset,
        status__in=ACTIVE_ALERT_STATES,
    ).values_list('severity', flat=True)
    if Alert.Severity.CRITICAL in active_severities:
        target = Asset.Status.ALARM
    elif active_severities:
        target = Asset.Status.WARNING
    else:
        target = Asset.Status.NORMAL
    if asset.status == target:
        return
    asset.status = target
    asset.save(update_fields=['status', 'updated_at'])
