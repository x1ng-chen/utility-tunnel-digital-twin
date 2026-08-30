from datetime import timedelta
from decimal import Decimal
from math import isfinite
import re

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import serializers

from .models import Alert, Asset, AuditLog, HardwareBinding, Profile, RegistrationRequest, ReportExport, SpatialFeature, Telemetry, Threshold, WorkOrder


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

    def update(self, instance, validated_data):
        """Persist only API-owned columns so the production role stays least-privileged."""
        for attribute, value in validated_data.items():
            setattr(instance, attribute, value)
        instance.save(update_fields=[*validated_data.keys(), 'updated_at'])
        return instance

    def validate_hardwareCode(self, value):
        return value or None

    def validate_mesh(self, value):
        """Keep model-node names deterministic and unambiguous for the 3D twin."""
        normalized = value.strip().upper()
        if not normalized:
            return ''
        if not re.fullmatch(r'[A-Z0-9][A-Z0-9_-]{1,79}', normalized):
            raise serializers.ValidationError('Model node names use only uppercase letters, numbers, hyphens and underscores.')
        conflicts = Asset.objects.filter(mesh__iexact=normalized)
        if self.instance:
            conflicts = conflicts.exclude(pk=self.instance.pk)
        if conflicts.exists():
            raise serializers.ValidationError('This model node name is already assigned to another asset.')
        return normalized

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


def _coordinate_pair(value):
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise serializers.ValidationError('GeoJSON coordinates must be [longitude, latitude] pairs.')
    longitude, latitude = value
    if any(isinstance(item, bool) or not isinstance(item, (int, float)) or not isfinite(item) for item in (longitude, latitude)):
        raise serializers.ValidationError('GeoJSON coordinates must be finite numbers.')
    if not -180 <= longitude <= 180 or not -90 <= latitude <= 90:
        raise serializers.ValidationError('GeoJSON coordinates are outside WGS84 bounds.')
    return [float(longitude), float(latitude)]


def _normalize_geometry(geometry):
    if not isinstance(geometry, dict):
        raise serializers.ValidationError('geometry must be a GeoJSON object.')
    geometry_type = geometry.get('type')
    coordinates = geometry.get('coordinates')
    if geometry_type == 'Point':
        return {'type': geometry_type, 'coordinates': _coordinate_pair(coordinates)}
    if geometry_type == 'LineString':
        if not isinstance(coordinates, list) or not 2 <= len(coordinates) <= 2000:
            raise serializers.ValidationError('LineString must contain 2 to 2000 coordinate pairs.')
        return {'type': geometry_type, 'coordinates': [_coordinate_pair(point) for point in coordinates]}
    if geometry_type == 'Polygon':
        if not isinstance(coordinates, list) or not 1 <= len(coordinates) <= 50:
            raise serializers.ValidationError('Polygon must contain 1 to 50 rings.')
        rings = []
        for ring in coordinates:
            if not isinstance(ring, list) or not 4 <= len(ring) <= 2000:
                raise serializers.ValidationError('Each Polygon ring must contain 4 to 2000 coordinate pairs.')
            normalized_ring = [_coordinate_pair(point) for point in ring]
            if normalized_ring[0] != normalized_ring[-1]:
                raise serializers.ValidationError('Polygon rings must be closed.')
            rings.append(normalized_ring)
        return {'type': geometry_type, 'coordinates': rings}
    raise serializers.ValidationError('geometry.type must be Point, LineString or Polygon.')


class SpatialFeatureSerializer(serializers.ModelSerializer):
    layerType = serializers.CharField(source='layer_type', read_only=True)
    sourceReference = serializers.CharField(source='source_reference', read_only=True)
    accuracyM = serializers.DecimalField(source='accuracy_m', max_digits=8, decimal_places=3, allow_null=True, read_only=True)
    capturedAt = serializers.DateTimeField(source='captured_at', allow_null=True, read_only=True)
    verifiedAt = serializers.DateTimeField(source='verified_at', allow_null=True, read_only=True)

    class Meta:
        model = SpatialFeature
        fields = ['id', 'code', 'name', 'layerType', 'geometry', 'crs', 'source', 'sourceReference', 'accuracyM', 'capturedAt', 'verifiedAt', 'status', 'description', 'version', 'created_at', 'updated_at']


class SpatialFeatureMutationSerializer(serializers.ModelSerializer):
    code = serializers.RegexField(r'^[A-Z0-9][A-Z0-9_-]{1,39}$', max_length=40)
    layerType = serializers.ChoiceField(source='layer_type', choices=SpatialFeature.LayerType.choices)
    sourceReference = serializers.CharField(source='source_reference', allow_blank=True, max_length=180, required=False)
    accuracyM = serializers.DecimalField(source='accuracy_m', max_digits=8, decimal_places=3, min_value=Decimal('0.001'), allow_null=True, required=False)
    capturedAt = serializers.DateTimeField(source='captured_at', allow_null=True, required=False)
    verifiedAt = serializers.DateTimeField(source='verified_at', allow_null=True, required=False)
    geometry = serializers.JSONField()

    class Meta:
        model = SpatialFeature
        fields = ['code', 'name', 'layerType', 'geometry', 'crs', 'source', 'sourceReference', 'accuracyM', 'capturedAt', 'verifiedAt', 'status', 'description']
        extra_kwargs = {'crs': {'required': False}, 'description': {'allow_blank': True, 'required': False}}

    def validate_crs(self, value):
        if value != 'EPSG:4326':
            raise serializers.ValidationError('Only EPSG:4326 WGS84 geometry is accepted by this API.')
        return value

    def validate_geometry(self, value):
        return _normalize_geometry(value)

    def validate(self, attrs):
        status = attrs.get('status', self.instance.status if self.instance else SpatialFeature.Status.DRAFT)
        source = attrs.get('source', self.instance.source if self.instance else None)
        verified_at = attrs.get('verified_at', self.instance.verified_at if self.instance else None)
        source_reference = attrs.get('source_reference', self.instance.source_reference if self.instance else '')
        if status == SpatialFeature.Status.PUBLISHED and (not verified_at or not source_reference.strip()):
            raise serializers.ValidationError({'status': 'Published GIS features require verifiedAt and sourceReference.'})
        if not source:
            raise serializers.ValidationError({'source': 'A governed spatial data source is required.'})
        return attrs


class HardwareBindingSerializer(serializers.ModelSerializer):
    assetCode = serializers.CharField(source='asset.code', read_only=True)
    deviceIdentifier = serializers.CharField(source='device_identifier', read_only=True)
    lastHeartbeatAt = serializers.DateTimeField(source='last_heartbeat_at', allow_null=True, read_only=True)
    expectedIntervalSeconds = serializers.IntegerField(source='expected_interval_seconds', read_only=True)

    class Meta:
        model = HardwareBinding
        fields = ['id', 'assetCode', 'protocol', 'deviceIdentifier', 'endpoint', 'expectedIntervalSeconds', 'status', 'lastHeartbeatAt', 'version', 'created_at', 'updated_at']


class HardwareBindingMutationSerializer(serializers.ModelSerializer):
    assetCode = serializers.RegexField(r'^[A-Z0-9][A-Z0-9_-]{1,39}$', write_only=True, required=False)
    deviceIdentifier = serializers.CharField(source='device_identifier', max_length=80, required=False)
    expectedIntervalSeconds = serializers.IntegerField(source='expected_interval_seconds', min_value=1, max_value=86400, required=False)

    class Meta:
        model = HardwareBinding
        fields = ['assetCode', 'protocol', 'deviceIdentifier', 'endpoint', 'expectedIntervalSeconds', 'status']
        extra_kwargs = {
            'endpoint': {'max_length': 200},
            'protocol': {'required': False},
            'status': {'required': False},
        }

    def validate_deviceIdentifier(self, value):
        normalized = value.strip()
        if not normalized:
            raise serializers.ValidationError('device_identifier is required.')
        return normalized

    def validate_endpoint(self, value):
        normalized = value.strip()
        if not normalized or any(character.isspace() for character in normalized):
            raise serializers.ValidationError('endpoint must be a non-empty identifier without whitespace.')
        return normalized

    def validate(self, attrs):
        asset_code = attrs.pop('assetCode', None)
        if asset_code:
            asset = Asset.objects.filter(code=asset_code, is_active=True).first()
            if not asset:
                raise serializers.ValidationError({'assetCode': 'An active asset with this code is required.'})
            if self.instance and asset.pk != self.instance.asset_id:
                raise serializers.ValidationError({'assetCode': 'A hardware binding cannot be moved to another asset.'})
            attrs['asset'] = asset
        elif not self.instance:
            raise serializers.ValidationError({'assetCode': 'This field is required.'})
        return attrs


class AlertSerializer(serializers.ModelSerializer):
    assetCode = serializers.CharField(source='asset.code', allow_null=True, read_only=True)
    openedAt = serializers.DateTimeField(source='opened_at', read_only=True)
    acknowledgedAt = serializers.DateTimeField(source='acknowledged_at', allow_null=True, read_only=True)
    acknowledgedBy = serializers.SerializerMethodField()
    resolvedAt = serializers.DateTimeField(source='resolved_at', allow_null=True, read_only=True)
    ruleKey = serializers.CharField(source='rule_key', allow_null=True, read_only=True)
    lastObservedValue = serializers.FloatField(source='last_observed_value', allow_null=True, read_only=True)

    class Meta:
        model = Alert
        fields = ['id', 'code', 'assetCode', 'severity', 'category', 'status', 'title', 'detail', 'ruleKey', 'lastObservedValue', 'openedAt', 'acknowledgedAt', 'acknowledgedBy', 'resolvedAt']

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
    eventId = serializers.CharField(source='event_id', allow_null=True, read_only=True)
    metricKey = serializers.CharField(source='metric_key', read_only=True)
    recordedAt = serializers.DateTimeField(source='recorded_at', read_only=True)
    ingestedAt = serializers.DateTimeField(source='ingested_at', read_only=True)

    class Meta:
        model = Telemetry
        fields = ['id', 'eventId', 'assetCode', 'metricKey', 'metric', 'value', 'unit', 'quality', 'recordedAt', 'ingestedAt']


class TelemetryReadingSerializer(serializers.Serializer):
    eventId = serializers.RegexField(r'^[A-Za-z0-9._:-]{1,80}$', max_length=80)
    assetCode = serializers.RegexField(r'^[A-Z0-9][A-Z0-9_-]{1,39}$', max_length=40)
    metricKey = serializers.RegexField(r'^[a-z][a-z0-9_.-]{1,39}$', max_length=40)
    metric = serializers.CharField(max_length=80)
    value = serializers.FloatField(min_value=-1_000_000_000, max_value=1_000_000_000)
    unit = serializers.CharField(max_length=20)
    quality = serializers.ChoiceField(choices=Telemetry.Quality.choices, default=Telemetry.Quality.GOOD)
    recordedAt = serializers.DateTimeField()

    def validate_value(self, value):
        if not isfinite(value):
            raise serializers.ValidationError('Telemetry value must be finite.')
        return value

    def validate_recordedAt(self, value):
        now = timezone.now()
        if value > now + timedelta(minutes=5):
            raise serializers.ValidationError('recordedAt cannot be more than five minutes in the future.')
        if value < now - timedelta(days=30):
            raise serializers.ValidationError('recordedAt cannot be more than 30 days old.')
        return value


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
    contentSha256 = serializers.CharField(source='content_sha256', read_only=True)
    rowCount = serializers.IntegerField(source='row_count', read_only=True)

    class Meta:
        model = ReportExport
        fields = ['id', 'reportType', 'status', 'fileName', 'contentSha256', 'rowCount', 'createdAt', 'completedAt']


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


class RegistrationRequestSerializer(serializers.ModelSerializer):
    requestedRole = serializers.CharField(source='requested_role', read_only=True)
    reviewNote = serializers.CharField(source='review_note', read_only=True)
    reviewedAt = serializers.DateTimeField(source='reviewed_at', read_only=True)
    setupExpiresAt = serializers.DateTimeField(source='setup_expires_at', read_only=True)
    passwordSetAt = serializers.DateTimeField(source='password_set_at', read_only=True)
    createdAt = serializers.DateTimeField(source='created_at', read_only=True)
    reviewerName = serializers.SerializerMethodField()

    class Meta:
        model = RegistrationRequest
        fields = ['id', 'account', 'display_name', 'requestedRole', 'status', 'reviewNote', 'reviewerName', 'reviewedAt', 'setupExpiresAt', 'passwordSetAt', 'createdAt']

    def get_reviewerName(self, obj):
        if not obj.reviewed_by:
            return None
        return obj.reviewed_by.get_full_name() or getattr(getattr(obj.reviewed_by, 'profile', None), 'display_name', '') or obj.reviewed_by.email
