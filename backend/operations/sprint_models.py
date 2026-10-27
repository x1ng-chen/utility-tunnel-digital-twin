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


class ReviewExperience(models.Model):
    id=models.UUIDField(primary_key=True,default=uuid.uuid4,editable=False)
    source_run=models.ForeignKey(AgentRun,on_delete=models.PROTECT,related_name='experience_candidates')
    owner=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT)
    parent=models.ForeignKey('self',on_delete=models.PROTECT,null=True,blank=True)
    station_id=models.CharField(max_length=4)
    asset_code=models.CharField(max_length=50)
    asset_kind=models.CharField(max_length=30)
    metric_key=models.CharField(max_length=80,blank=True)
    category=models.CharField(max_length=30)
    lesson=models.CharField(max_length=300)
    source_refs=models.JSONField(default=list)
    source_scope=models.CharField(max_length=30)
    layout_version=models.CharField(max_length=100)
    knowledge_version=models.CharField(max_length=64)
    rule_version=models.CharField(max_length=40)
    status=models.CharField(max_length=20,default='candidate')
    revision=models.PositiveIntegerField(default=1)
    content_hash=models.CharField(max_length=64)
    audit=models.JSONField(default=list)
    created_at=models.DateTimeField(auto_now_add=True)
    updated_at=models.DateTimeField(auto_now=True)

    class Meta:
        constraints=[models.UniqueConstraint(fields=['owner','source_run','content_hash'],name='review_experience_capture_once'),
            models.UniqueConstraint(fields=['content_hash'],condition=models.Q(status='approved'),name='experience_active_unique')]
        indexes=[models.Index(fields=['status','station_id','rule_version'],name='experience_lookup_idx')]
