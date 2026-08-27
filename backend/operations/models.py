from django.contrib.auth.models import User
from django.db import models


class Profile(models.Model):
    class Role(models.TextChoices):
        ADMINISTRATOR = 'administrator', '管理员'
        OPERATOR = 'operator', '运维员'
        VIEWER = 'viewer', '查看者'

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    display_name = models.CharField(max_length=80, blank=True)
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.OPERATOR)

    def __str__(self) -> str:
        return self.display_name or self.user.email or self.user.username


class Asset(models.Model):
    class Status(models.TextChoices):
        NORMAL = 'normal', '正常'
        WARNING = 'warning', '关注'
        ALARM = 'alarm', '告警'
        OFFLINE = 'offline', '离线'
        UNKNOWN = 'unknown', '未知'

    class IntegrationStatus(models.TextChoices):
        VERIFIED = 'verified', '已验证'
        FIRMWARE_CONNECTED = 'firmware_connected', '固件已接入'
        CALIBRATION_REQUIRED = 'calibration_required', '待标定'
        PENDING_VERIFICATION = 'pending_verification', '待验证'
        OPTIONAL = 'optional', '可选模块'
        NON_OPERATIONAL = 'non_operational', '非运行资产'

    class LocationSource(models.TextChoices):
        UNASSIGNED = 'unassigned', '未配置'
        DEMO_ANCHOR = 'demo_anchor', '演示锚点'
        CONFIGURED = 'configured', '人工配置'
        SURVEYED = 'surveyed', '现场测绘'
        GPS = 'gps', 'GPS 定位'

    code = models.CharField(max_length=40, unique=True)
    name = models.CharField(max_length=120)
    zone = models.CharField(max_length=40)
    asset_type = models.CharField(max_length=60)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.NORMAL)
    hardware_code = models.CharField(max_length=20, unique=True, null=True, blank=True)
    integration_status = models.CharField(max_length=30, choices=IntegrationStatus.choices, default=IntegrationStatus.PENDING_VERIFICATION)
    interface = models.CharField(max_length=80, blank=True)
    capabilities = models.JSONField(default=list, blank=True)
    mesh = models.CharField(max_length=80, blank=True)
    position = models.JSONField(default=dict, blank=True)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    location_source = models.CharField(max_length=20, choices=LocationSource.choices, default=LocationSource.UNASSIGNED)
    installation_note = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    version = models.PositiveIntegerField(default=1)
    last_seen_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['code']
        indexes = [
            models.Index(fields=['zone', 'integration_status'], name='asset_zone_integration_idx'),
        ]
        constraints = [
            models.CheckConstraint(
                check=(models.Q(latitude__isnull=True, longitude__isnull=True) | models.Q(latitude__isnull=False, longitude__isnull=False)),
                name='asset_coordinates_paired',
            ),
            models.CheckConstraint(
                check=(models.Q(latitude__isnull=True) | models.Q(latitude__gte=-90, latitude__lte=90)),
                name='asset_latitude_range',
            ),
            models.CheckConstraint(
                check=(models.Q(longitude__isnull=True) | models.Q(longitude__gte=-180, longitude__lte=180)),
                name='asset_longitude_range',
            ),
            models.CheckConstraint(
                check=(
                    models.Q(latitude__isnull=True, longitude__isnull=True, location_source='unassigned')
                    | (models.Q(latitude__isnull=False, longitude__isnull=False) & ~models.Q(location_source='unassigned'))
                ),
                name='asset_location_source_consistent',
            ),
        ]


class Alert(models.Model):
    class Severity(models.TextChoices):
        INFO = 'info', '提示'
        WARNING = 'warning', '警告'
        CRITICAL = 'critical', '严重'

    class Status(models.TextChoices):
        OPEN = 'open', '待确认'
        ACKNOWLEDGED = 'acknowledged', '已确认'
        RESOLVED = 'resolved', '已解决'
        CLOSED = 'closed', '已关闭'

    code = models.CharField(max_length=50, unique=True)
    asset = models.ForeignKey(Asset, on_delete=models.SET_NULL, null=True, related_name='alerts')
    severity = models.CharField(max_length=20, choices=Severity.choices)
    category = models.CharField(max_length=80)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.OPEN)
    title = models.CharField(max_length=160)
    detail = models.TextField()
    opened_at = models.DateTimeField()
    acknowledged_at = models.DateTimeField(null=True, blank=True)
    acknowledged_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='acknowledged_alerts')
    resolved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-opened_at']
        indexes = [
            models.Index(fields=['status', '-opened_at'], name='alert_status_opened_idx'),
            models.Index(fields=['asset', 'status'], name='alert_asset_status_idx'),
        ]


class WorkOrder(models.Model):
    class Priority(models.TextChoices):
        LOW = 'low', '低'
        NORMAL = 'normal', '普通'
        HIGH = 'high', '高'
        URGENT = 'urgent', '紧急'

    class Status(models.TextChoices):
        DRAFT = 'draft', '草稿'
        OPEN = 'open', '待分派'
        ASSIGNED = 'assigned', '已分派'
        IN_PROGRESS = 'in_progress', '处理中'
        PENDING_REVIEW = 'pending_review', '待复核'
        COMPLETED = 'completed', '已完成'
        CANCELLED = 'cancelled', '已取消'

    code = models.CharField(max_length=50, unique=True)
    source_alert = models.ForeignKey(Alert, on_delete=models.SET_NULL, null=True, blank=True, related_name='work_orders')
    asset = models.ForeignKey(Asset, on_delete=models.PROTECT, related_name='work_orders')
    title = models.CharField(max_length=180)
    description = models.TextField(blank=True)
    priority = models.CharField(max_length=20, choices=Priority.choices, default=Priority.NORMAL)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.OPEN)
    assignee = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='assigned_work_orders')
    created_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name='created_work_orders')
    due_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='reviewed_work_orders')
    completed_at = models.DateTimeField(null=True, blank=True)
    version = models.PositiveIntegerField(default=1)
    idempotency_key = models.CharField(max_length=80, unique=True, null=True, blank=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status', '-updated_at'], name='wo_status_updated_idx'),
            models.Index(fields=['asset', 'status'], name='wo_asset_status_idx'),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['source_alert'],
                condition=models.Q(source_alert__isnull=False),
                name='work_order_source_alert_unique',
            ),
        ]


class Telemetry(models.Model):
    class Quality(models.TextChoices):
        GOOD = 'good', '良好'
        SUSPECT = 'suspect', '可疑'
        BAD = 'bad', '异常'
        MISSING = 'missing', '缺失'

    asset = models.ForeignKey(Asset, on_delete=models.CASCADE, related_name='telemetry')
    metric = models.CharField(max_length=80)
    value = models.FloatField()
    unit = models.CharField(max_length=20)
    quality = models.CharField(max_length=20, choices=Quality.choices, default=Quality.GOOD)
    recorded_at = models.DateTimeField()

    class Meta:
        ordering = ['-recorded_at']
        indexes = [models.Index(fields=['asset', '-recorded_at'], name='telemetry_asset_time_idx')]


class Threshold(models.Model):
    key = models.CharField(max_length=40, unique=True)
    label = models.CharField(max_length=80)
    warning = models.FloatField()
    alarm = models.FloatField()
    unit = models.CharField(max_length=20)
    version = models.PositiveIntegerField(default=1)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.CheckConstraint(check=models.Q(warning__gte=0), name='threshold_warning_non_negative'),
            models.CheckConstraint(check=models.Q(alarm__gt=models.F('warning')), name='threshold_alarm_above_warning'),
        ]


class AuditLog(models.Model):
    actor = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='audit_entries')
    action = models.CharField(max_length=100)
    resource_type = models.CharField(max_length=60)
    resource_id = models.CharField(max_length=80, blank=True)
    detail = models.JSONField(default=dict, blank=True)
    request_id = models.CharField(max_length=80, blank=True)
    occurred_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-occurred_at']
        indexes = [models.Index(fields=['action', '-occurred_at'], name='audit_action_time_idx')]


class ReportExport(models.Model):
    class Status(models.TextChoices):
        COMPLETED = 'completed', '已完成'
        FAILED = 'failed', '失败'

    report_type = models.CharField(max_length=40)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.COMPLETED)
    file_name = models.CharField(max_length=180)
    idempotency_key = models.CharField(max_length=80, unique=True, null=True, blank=True, editable=False)
    requested_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name='report_exports')
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
