import uuid
from django.conf import settings
from django.db import models


class AgentRun(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    request_key = models.CharField(max_length=80)
    input = models.JSONField(default=dict)
    status = models.CharField(max_length=20, default='queued')
    stage = models.CharField(max_length=40, default='queued')
    snapshot = models.JSONField(default=dict)
    steps = models.JSONField(default=list)
    result = models.JSONField(default=dict)
    runtime = models.JSONField(default=dict)
    error = models.CharField(max_length=500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True)
    finished_at = models.DateTimeField(null=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['owner', 'request_key'], name='agent_run_request_unique'),
            models.UniqueConstraint(fields=['owner'], condition=models.Q(status__in=['queued', 'running']),
                                    name='agent_run_one_active_user'),
        ]
        indexes = [models.Index(fields=['status', 'created_at'], name='agent_run_queue_idx')]


class DemoSession(models.Model):
    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
    generation = models.UUIDField(default=uuid.uuid4)
    case_id = models.CharField(max_length=20, default='INS-01')
    running = models.BooleanField(default=False)
    phase = models.PositiveSmallIntegerField(default=0)
    tick = models.PositiveIntegerField(default=0)
    outputs = models.JSONField(default=dict)
    last_tick_at = models.DateTimeField(null=True)
    updated_at = models.DateTimeField(auto_now=True)


class SimulatedAction(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    run = models.ForeignKey(AgentRun, on_delete=models.PROTECT, related_name='actions')
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    generation = models.UUIDField()
    asset_code = models.CharField(max_length=30)
    intent = models.CharField(max_length=30)
    value = models.PositiveSmallIntegerField()
    state = models.CharField(max_length=30, default='proposed')
    expires_at = models.DateTimeField()
    events = models.JSONField(default=list)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['run','asset_code','intent','value'],name='sim_action_once_per_proposal')]
