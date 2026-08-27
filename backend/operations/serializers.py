from rest_framework import serializers
from math import isfinite
from django.contrib.auth import get_user_model
from .models import Alert, Asset, AuditLog, Profile, ReportExport, Telemetry, Threshold, WorkOrder


class AssetSerializer(serializers.ModelSerializer):
    type = serializers.CharField(source='asset_type', read_only=True)
    lastSeenAt = serializers.DateTimeField(source='last_seen_at', read_only=True)
    hardwareCode = serializers.CharField(source='hardware_code', allow_null=True, read_only=True)
    integrationStatus = serializers.CharField(source='integration_status', read_only=True)
    latitude = serializers.SerializerMethodField()
    longitude = serializers.SerializerMethodField()
    locationSource = serializers.CharField(source='location_source', read_only=True)
    installationNote = serializers.CharField(source='installation_note', read_only=True)
    isActive = serializers.BooleanField(source='is_active', read_only=True)

    class Meta:
        model = Asset
        fields = ['id', 'code', 'name', 'zone', 'type', 'status', 'hardwareCode', 'integrationStatus', 'interface', 'capabilities', 'mesh', 'position', 'latitude', 'longitude', 'locationSource', 'installationNote', 'isActive', 'version', 'lastSeenAt']

    def get_latitude(self, obj):
        return float(obj.latitude) if obj.latitude is not None else None

    def get_longitude(self, obj):
        return float(obj.longitude) if obj.longitude is not None else None


class AssetMutationSerializer(serializers.ModelSerializer):
    code = serializers.RegexField(r'^[A-Z0-9][A-Z0-9_-]{1,39}$', max_length=40)
    type = serializers.CharField(source='asset_type', max_length=60)
    hardwareCode = serializers.RegexField(r'^H-[0-9]{2,4}$', source='hardware_code', max_length=20, allow_null=True, allow_blank=True, required=False)
    integrationStatus = serializers.ChoiceField(source='integration_status', choices=Asset.IntegrationStatus.choices)
    locationSource = serializers.ChoiceField(source='location_source', choices=Asset.LocationSource.choices)
    installationNote = serializers.CharField(source='installation_note', allow_blank=True, max_length=1000, required=False)
    isActive = serializers.BooleanField(source='is_active', required=False)
    capabilities = serializers.ListField(child=serializers.CharField(max_length=80), max_length=20, required=False)
    position = serializers.JSONField(required=False)

    class Meta:
        model = Asset
        fields = ['code', 'name', 'zone', 'type', 'status', 'hardwareCode', 'integrationStatus', 'interface', 'capabilities', 'mesh', 'position', 'latitude', 'longitude', 'locationSource', 'installationNote', 'isActive']
        extra_kwargs = {
            'name': {'max_length': 120},
            'zone': {'max_length': 40},
            'status': {'required': False},
            'interface': {'allow_blank': True, 'max_length': 80, 'required': False},
            'mesh': {'allow_blank': True, 'max_length': 80, 'required': False},
            'latitude': {'allow_null': True, 'required': False},
            'longitude': {'allow_null': True, 'required': False},
        }

    def validate_hardwareCode(self, value):
        return value or None

    def validate_capabilities(self, value):
        normalized = [item.strip() for item in value if item.strip()]
        if len(normalized) != len(set(normalized)):
            raise serializers.ValidationError('Capabilities must not contain duplicates.')
        return normalized

    def validate_position(self, value):
        if not isinstance(value, dict):
            raise serializers.ValidationError('Position must be an object.')
        unknown = set(value) - {'x', 'y', 'z'}
        if unknown:
            raise serializers.ValidationError('Position supports only x, y and z.')
        normalized = {}
        for key in ('x', 'y', 'z'):
            if key not in value:
                continue
            coordinate = value[key]
            if isinstance(coordinate, bool) or not isinstance(coordinate, (int, float)):
                raise serializers.ValidationError(f'Position {key} must be a number.')
            if not isfinite(coordinate):
                raise serializers.ValidationError(f'Position {key} must be finite.')
            if key in {'x', 'y'} and not 0 <= coordinate <= 100:
                raise serializers.ValidationError(f'Position {key} must be between 0 and 100.')
            if key == 'z' and not -1000 <= coordinate <= 1000:
                raise serializers.ValidationError('Position z is out of range.')
            normalized[key] = coordinate
        return normalized

    def validate(self, attrs):
        instance = self.instance
        latitude = attrs.get('latitude', instance.latitude if instance else None)
        longitude = attrs.get('longitude', instance.longitude if instance else None)
        source = attrs.get('location_source', instance.location_source if instance else Asset.LocationSource.UNASSIGNED)
        if (latitude is None) != (longitude is None):
            raise serializers.ValidationError({'coordinates': 'Latitude and longitude must be supplied together.'})
        if latitude is None and source != Asset.LocationSource.UNASSIGNED:
            raise serializers.ValidationError({'locationSource': 'Assets without coordinates must use unassigned.'})
        if latitude is not None and source == Asset.LocationSource.UNASSIGNED:
            raise serializers.ValidationError({'locationSource': 'Located assets must declare a coordinate source.'})
        if latitude is not None and not -90 <= latitude <= 90:
            raise serializers.ValidationError({'latitude': 'Latitude must be between -90 and 90.'})
        if longitude is not None and not -180 <= longitude <= 180:
            raise serializers.ValidationError({'longitude': 'Longitude must be between -180 and 180.'})
        return attrs


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
