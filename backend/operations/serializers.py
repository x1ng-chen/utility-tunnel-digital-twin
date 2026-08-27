from rest_framework import serializers
from django.contrib.auth import get_user_model
from .models import Alert, Asset, AuditLog, Profile, ReportExport, Telemetry, Threshold, WorkOrder


class AssetSerializer(serializers.ModelSerializer):
    type = serializers.CharField(source='asset_type', read_only=True)
    lastSeenAt = serializers.DateTimeField(source='last_seen_at', read_only=True)

    class Meta:
        model = Asset
        fields = ['id', 'code', 'name', 'zone', 'type', 'status', 'mesh', 'position', 'lastSeenAt']


class AlertSerializer(serializers.ModelSerializer):
    assetCode = serializers.CharField(source='asset.code', allow_null=True, read_only=True)
    openedAt = serializers.DateTimeField(source='opened_at', read_only=True)
    acknowledgedAt = serializers.DateTimeField(source='acknowledged_at', allow_null=True, read_only=True)
    acknowledgedBy = serializers.SerializerMethodField()
    resolvedAt = serializers.DateTimeField(source='resolved_at', allow_null=True, read_only=True)

    class Meta:
        model = Alert
        fields = ['id', 'code', 'assetCode', 'severity', 'category', 'status', 'title', 'detail', 'openedAt', 'acknowledgedAt', 'acknowledgedBy', 'resolvedAt']

    def get_acknowledgedBy(self, obj):
        return obj.acknowledged_by.get_full_name() or obj.acknowledged_by.email if obj.acknowledged_by else None


class WorkOrderSerializer(serializers.ModelSerializer):
    sourceAlertId = serializers.IntegerField(source='source_alert_id', allow_null=True, read_only=True)
    assetCode = serializers.CharField(source='asset.code', read_only=True)
    assigneeName = serializers.SerializerMethodField()
    createdAt = serializers.DateTimeField(source='created_at', read_only=True)
    updatedAt = serializers.DateTimeField(source='updated_at', read_only=True)
    dueAt = serializers.DateTimeField(source='due_at', allow_null=True, read_only=True)
    completedAt = serializers.DateTimeField(source='completed_at', allow_null=True, read_only=True)

    class Meta:
        model = WorkOrder
        fields = ['id', 'code', 'sourceAlertId', 'assetCode', 'title', 'description', 'priority', 'status', 'assigneeName', 'dueAt', 'completedAt', 'createdAt', 'updatedAt', 'version']

    def get_assigneeName(self, obj):
        return obj.assignee.get_full_name() or obj.assignee.email if obj.assignee else None


class TelemetrySerializer(serializers.ModelSerializer):
    assetCode = serializers.CharField(source='asset.code', read_only=True)
    recordedAt = serializers.DateTimeField(source='recorded_at', read_only=True)

    class Meta:
        model = Telemetry
        fields = ['id', 'assetCode', 'metric', 'value', 'unit', 'quality', 'recordedAt']


class ThresholdSerializer(serializers.ModelSerializer):
    class Meta:
        model = Threshold
        fields = ['key', 'label', 'warning', 'alarm', 'unit', 'version']


class AuditSerializer(serializers.ModelSerializer):
    actorName = serializers.SerializerMethodField()
    resourceType = serializers.CharField(source='resource_type', read_only=True)
    resourceId = serializers.CharField(source='resource_id', read_only=True)
    requestId = serializers.CharField(source='request_id', read_only=True)
    occurredAt = serializers.DateTimeField(source='occurred_at', read_only=True)

    class Meta:
        model = AuditLog
        fields = ['id', 'actorName', 'action', 'resourceType', 'resourceId', 'detail', 'requestId', 'occurredAt']

    def get_actorName(self, obj):
        return obj.actor.get_full_name() or obj.actor.email if obj.actor else '系统'


class ReportExportSerializer(serializers.ModelSerializer):
    reportType = serializers.CharField(source='report_type', read_only=True)
    fileName = serializers.CharField(source='file_name', read_only=True)
    createdAt = serializers.DateTimeField(source='created_at', read_only=True)
    completedAt = serializers.DateTimeField(source='completed_at', read_only=True)

    class Meta:
        model = ReportExport
        fields = ['id', 'reportType', 'status', 'fileName', 'createdAt', 'completedAt']


class AdminUserSerializer(serializers.ModelSerializer):
    displayName = serializers.SerializerMethodField()
    role = serializers.SerializerMethodField()
    isActive = serializers.BooleanField(source='is_active', read_only=True)
    lastLogin = serializers.DateTimeField(source='last_login', allow_null=True, read_only=True)
    createdAt = serializers.DateTimeField(source='date_joined', read_only=True)

    class Meta:
        model = get_user_model()
        fields = ['id', 'email', 'displayName', 'role', 'isActive', 'lastLogin', 'createdAt']

    def get_displayName(self, obj):
        profile = getattr(obj, 'profile', None)
        return (profile.display_name if profile else '') or obj.get_full_name() or obj.email or obj.username

    def get_role(self, obj):
        if obj.is_superuser:
            return Profile.Role.ADMINISTRATOR
        return getattr(getattr(obj, 'profile', None), 'role', Profile.Role.VIEWER)
