from datetime import timedelta
from collections.abc import Mapping
from math import isfinite
import re
from uuid import uuid4
from django.conf import settings
from django.contrib.auth import authenticate
from django.contrib.auth.hashers import make_password
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import IntegrityError, connection, transaction
from django.db.models import Avg, Count, Max, Min, Q
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework import status
from rest_framework.authentication import TokenAuthentication
from rest_framework.authtoken.models import Token
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Alert, Asset, AuditLog, HardwareBinding, Profile, RegistrationRequest, ReportExport, SpatialFeature, Telemetry, Threshold, WorkOrder
from .permissions import AuthenticatedRead
from .serializers import AdminUserSerializer, AlertSerializer, AssetMutationSerializer, AssetSerializer, AuditSerializer, HardwareBindingMutationSerializer, HardwareBindingSerializer, RegistrationRequestSerializer, ReportExportSerializer, SpatialFeatureMutationSerializer, SpatialFeatureSerializer, TelemetryReadingSerializer, TelemetrySerializer, ThresholdSerializer, WorkOrderSerializer
from .services import actor_name, audit
from .telemetry_rules import evaluate_threshold
from .throttling import LoginRateThrottle


def request_id(request) -> str:
    return getattr(request, 'request_id', request.headers.get('X-Request-Id', ''))


def object_payload(request):
    """Return an object payload or ``None`` for malformed JSON bodies."""
    return request.data if isinstance(request.data, Mapping) else None


ACCOUNT_PATTERN = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_.@-]{2,79}$')


def validate_registration_account(value):
    if not isinstance(value, str):
        return None
    account = value.strip().lower()
    return account if ACCOUNT_PATTERN.fullmatch(account) else None


def error_response(code: str, message: str, status_code: int, details=None):
    return Response({'error': code, 'message': message, 'details': details or {}}, status=status_code)


def paginated(queryset, serializer_class, request, ordering=('-id',)):
    try:
        page = max(1, int(request.query_params.get('page', '1')))
        page_size = min(100, max(1, int(request.query_params.get('pageSize', '20'))))
    except ValueError:
        return error_response('invalid_request', 'page and pageSize must be numbers.', 400)
    # Every paginated endpoint uses a stable newest-first order. Without an
    # explicit order, concurrent inserts can make records move between pages.
    queryset = queryset.order_by(*ordering)
    total = queryset.count()
    items = queryset[(page - 1) * page_size:page * page_size]
    page_count = (total + page_size - 1) // page_size if total else 0
    return Response({
        'items': serializer_class(items, many=True).data,
        'page': page,
        'pageSize': page_size,
        'total': total,
        'pageCount': page_count,
        'hasNext': page < page_count,
        'hasPrevious': page > 1 and page_count > 0,
    })


def role(request) -> str:
    if request.user.is_superuser:
        return Profile.Role.ADMINISTRATOR
    return getattr(getattr(request.user, 'profile', None), 'role', Profile.Role.VIEWER)


def can_write(request) -> bool:
    return role(request) in {Profile.Role.ADMINISTRATOR, Profile.Role.OPERATOR}


def is_admin(request) -> bool:
    return role(request) == Profile.Role.ADMINISTRATOR


def work_order_code() -> str:
    """Generate a collision-resistant human-readable work-order code."""
    return f'WO-{timezone.now():%y%m%d}-{uuid4().hex[:6].upper()}'


IDEMPOTENCY_KEY_PATTERN = re.compile(r'^[A-Za-z0-9._:-]{1,80}$')


def get_idempotency_key(request):
    value = request.headers.get('Idempotency-Key', '').strip()
    if not value:
        return None, None
    if not IDEMPOTENCY_KEY_PATTERN.fullmatch(value):
        return None, error_response('invalid_request', 'Idempotency-Key must contain 1-80 safe characters.', 400)
    return value, None


def datetime_filter(request, key: str):
    """Parse an ISO-8601 query value and normalize it to an aware datetime."""
    value = request.query_params.get(key, '').strip()
    if not value:
        return None, None
    parsed = parse_datetime(value)
    if parsed is None:
        return None, error_response('invalid_request', f'{key} must be a valid ISO-8601 datetime.', 400)
    if timezone.is_naive(parsed):
        parsed = timezone.make_aware(parsed, timezone.get_current_timezone())
    return parsed, None


def telemetry_matches(reading, payload) -> bool:
    return (
        reading.asset.code == payload['assetCode']
        and reading.metric_key == payload['metricKey']
        and reading.metric == payload['metric']
        and reading.value == payload['value']
        and reading.unit == payload['unit']
        and reading.quality == payload['quality']
        and reading.recorded_at == payload['recordedAt']
    )


def filtered_telemetry(request):
    queryset = Telemetry.objects.select_related('asset')
    asset_code = request.query_params.get('assetCode', '').strip()
    metric_key = request.query_params.get('metricKey', '').strip()
    quality = request.query_params.get('quality', '').strip()
    if asset_code:
        if not re.fullmatch(r'[A-Z0-9][A-Z0-9_-]{1,39}', asset_code):
            return None, error_response('invalid_request', 'assetCode is not valid.', 400)
        queryset = queryset.filter(asset__code=asset_code)
    if metric_key:
        if not re.fullmatch(r'[a-z][a-z0-9_.-]{1,39}', metric_key):
            return None, error_response('invalid_request', 'metricKey is not valid.', 400)
        queryset = queryset.filter(metric_key=metric_key)
    if quality:
        if quality not in Telemetry.Quality.values:
            return None, error_response('invalid_request', 'quality is not valid.', 400)
        queryset = queryset.filter(quality=quality)
    recorded_from, error = datetime_filter(request, 'recordedFrom')
    if error:
        return None, error
    recorded_to, error = datetime_filter(request, 'recordedTo')
    if error:
        return None, error
    if recorded_from and recorded_to and recorded_from > recorded_to:
        return None, error_response('invalid_request', 'recordedFrom must be earlier than recordedTo.', 400)
    if recorded_from:
        queryset = queryset.filter(recorded_at__gte=recorded_from)
    if recorded_to:
        queryset = queryset.filter(recorded_at__lte=recorded_to)
    return queryset, None


def _geometry_points(geometry):
    coordinates = geometry.get('coordinates', [])
    if geometry.get('type') == 'Point':
        return [coordinates]
    if geometry.get('type') == 'LineString':
        return coordinates
    if geometry.get('type') == 'Polygon':
        return [point for ring in coordinates for point in ring]
    return []


def _parse_bbox(request):
    value = request.query_params.get('bbox', '').strip()
    if not value:
        return None, None
    try:
        min_longitude, min_latitude, max_longitude, max_latitude = [float(item) for item in value.split(',')]
    except ValueError:
        return None, error_response('invalid_request', 'bbox must be minLongitude,minLatitude,maxLongitude,maxLatitude.', 400)
    values = (min_longitude, min_latitude, max_longitude, max_latitude)
    if not all(isfinite(item) for item in values) or not (-180 <= min_longitude <= 180 and -180 <= max_longitude <= 180 and -90 <= min_latitude <= 90 and -90 <= max_latitude <= 90) or min_longitude > max_longitude or min_latitude > max_latitude:
        return None, error_response('invalid_request', 'bbox is outside WGS84 bounds or inverted.', 400)
    return values, None


def _intersects_bbox(geometry, bbox):
    if bbox is None:
        return True
    min_longitude, min_latitude, max_longitude, max_latitude = bbox
    points = _geometry_points(geometry)
    if not points:
        return False
    geometry_min_longitude = min(point[0] for point in points)
    geometry_max_longitude = max(point[0] for point in points)
    geometry_min_latitude = min(point[1] for point in points)
    geometry_max_latitude = max(point[1] for point in points)
    # Envelope intersection deliberately avoids false negatives for lines or
    # polygons that cross the requested viewport without a vertex inside it.
    return not (
        geometry_max_longitude < min_longitude
        or geometry_min_longitude > max_longitude
        or geometry_max_latitude < min_latitude
        or geometry_min_latitude > max_latitude
    )


def _geojson_feature(feature):
    data = SpatialFeatureSerializer(feature).data
    return {
        'type': 'Feature',
        'id': str(feature.pk),
        'geometry': data.pop('geometry'),
        'properties': data,
    }


class HealthView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request):
        return Response({'status': 'ok', 'service': 'utility-tunnel-django', 'version': settings.APP_VERSION, 'commit': settings.APP_COMMIT_SHA, 'time': timezone.now()})


class ReadyView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request):
        started = timezone.now()
        try:
            with connection.cursor() as cursor:
                cursor.execute('SELECT 1')
                cursor.fetchone()
        except Exception:
            return error_response('not_ready', 'Database is not ready.', 503)
        latency_ms = round((timezone.now() - started).total_seconds() * 1000, 2)
        return Response({'status': 'ready', 'service': 'utility-tunnel-django', 'checks': {'database': 'ok'}, 'latencyMs': latency_ms, 'time': timezone.now()})


class LoginView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [LoginRateThrottle]

    def post(self, request):
        payload = object_payload(request)
        if payload is None:
            return error_response('invalid_request', 'A JSON object body is required.', 400)
        email_value = payload.get('email', '')
        password_value = payload.get('password', '')
        if not isinstance(email_value, str) or not isinstance(password_value, str):
            return error_response('invalid_request', 'Email and password must be strings.', 400)
        email = email_value.strip().lower()
        password = password_value
        if not email or not password:
            return error_response('invalid_request', 'Email and password are required.', 400)
        matching_users = User.objects.filter(email__iexact=email, is_active=True)
        if matching_users.count() != 1:
            return error_response('invalid_credentials', 'Invalid email or password.', 401)
        user = matching_users.first()
        authenticated = authenticate(username=user.username if user else email, password=password)
        if not authenticated:
            return error_response('invalid_credentials', 'Invalid email or password.', 401)
        with transaction.atomic():
            token, created = Token.objects.select_for_update().get_or_create(user=authenticated)
            if not created and token.created + timedelta(seconds=settings.API_TOKEN_TTL_SECONDS) <= timezone.now():
                token.delete()
                token = Token.objects.create(user=authenticated)
            profile, _ = Profile.objects.get_or_create(
                user=authenticated,
                defaults={
                    'display_name': authenticated.get_full_name() or authenticated.email,
                    'role': Profile.Role.ADMINISTRATOR if authenticated.is_superuser else Profile.Role.OPERATOR,
                },
            )
            authenticated.last_login = timezone.now()
            authenticated.save(update_fields=['last_login'])
            audit(authenticated, 'auth.login', 'app_user', authenticated.pk, {'email': authenticated.email}, request_id(request))
        return Response({'accessToken': token.key, 'tokenType': 'Bearer', 'user': {'id': authenticated.pk, 'email': authenticated.email, 'displayName': profile.display_name or authenticated.email, 'role': Profile.Role.ADMINISTRATOR if authenticated.is_superuser else profile.role}})


class MeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        profile, _ = Profile.objects.get_or_create(user=request.user, defaults={'display_name': request.user.email})
        return Response({'id': request.user.pk, 'email': request.user.email, 'displayName': profile.display_name or request.user.email, 'role': role(request)})


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        Token.objects.filter(user=request.user).delete()
        audit(request.user, 'auth.logout', 'app_user', request.user.pk, request_id=request_id(request))
        return Response(status=204)


class RegistrationRequestView(APIView):
    """Public account application endpoint; it never creates an active user."""

    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [LoginRateThrottle]

    def post(self, request):
        payload = object_payload(request)
        if payload is None:
            return error_response('invalid_request', 'A JSON object body is required.', 400)
        account = validate_registration_account(payload.get('account'))
        display_name = payload.get('displayName')
        requested_role = payload.get('role')
        password_value = payload.get('password')
        if not account or not isinstance(display_name, str) or not display_name.strip() or not isinstance(password_value, str):
            return error_response('invalid_request', '请填写账号、姓名和密码。', 400)
        if requested_role not in {Profile.Role.OPERATOR, Profile.Role.VIEWER}:
            return error_response('invalid_request', '只能申请运维员或查看者账号。', 400)
        if len(password_value) < 8:
            return error_response('invalid_request', '密码至少需要 8 位。', 400)
        try:
            validate_password(password_value)
        except ValidationError:
            return error_response('invalid_request', '密码强度不足，请使用更复杂的密码。', 400)
        if User.objects.filter(Q(email__iexact=account) | Q(username__iexact=account)).exists():
            return error_response('conflict', '该账号已存在，请直接登录。', 409)
        if RegistrationRequest.objects.filter(account__iexact=account, status=RegistrationRequest.Status.PENDING).exists():
            return error_response('conflict', '该账号的申请正在审批中，请勿重复提交。', 409)
        application = RegistrationRequest.objects.create(
            account=account,
            display_name=display_name.strip()[:80],
            requested_role=requested_role,
            password_hash=make_password(password_value),
        )
        return Response({'id': application.pk, 'status': application.status, 'message': '申请已提交，请等待管理员审批。'}, status=status.HTTP_201_CREATED)


class AdminRegistrationRequestListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not is_admin(request):
            return error_response('forbidden', 'Administrator permission is required.', 403)
        queryset = RegistrationRequest.objects.select_related('reviewed_by', 'created_user')
        requested_status = request.query_params.get('status', RegistrationRequest.Status.PENDING)
        if requested_status not in RegistrationRequest.Status.values:
            return error_response('invalid_request', 'status is not valid.', 400)
        return paginated(queryset.filter(status=requested_status), RegistrationRequestSerializer, request, ordering=('-created_at', '-id'))


class AdminRegistrationRequestDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def patch(self, request, pk):
        if not is_admin(request):
            return error_response('forbidden', 'Administrator permission is required.', 403)
        payload = object_payload(request)
        if payload is None:
            return error_response('invalid_request', 'A JSON object body is required.', 400)
        next_status = payload.get('status')
        review_note = payload.get('reviewNote', '')
        if next_status not in {RegistrationRequest.Status.APPROVED, RegistrationRequest.Status.REJECTED}:
            return error_response('invalid_request', 'status must be approved or rejected.', 400)
        if not isinstance(review_note, str):
            return error_response('invalid_request', 'reviewNote must be a string.', 400)
        with transaction.atomic():
            application = RegistrationRequest.objects.select_for_update().filter(pk=pk).first()
            if not application:
                return error_response('not_found', 'Registration request not found.', 404)
            if application.status != RegistrationRequest.Status.PENDING:
                return error_response('conflict', '该申请已处理，不能重复审批。', 409)
            application.status = next_status
            application.review_note = review_note.strip()[:300]
            application.reviewed_by = request.user
            application.reviewed_at = timezone.now()
            if next_status == RegistrationRequest.Status.APPROVED:
                if User.objects.filter(Q(email__iexact=application.account) | Q(username__iexact=application.account)).exists():
                    return error_response('conflict', '该账号已存在，无法批准申请。', 409)
                user = User(username=f'user-{uuid4().hex}', email=application.account, password=application.password_hash)
                user.save()
                Profile.objects.create(user=user, display_name=application.display_name, role=application.requested_role)
                application.created_user = user
                action = 'registration.approved'
            else:
                action = 'registration.rejected'
            application.save(update_fields=['status', 'review_note', 'reviewed_by', 'reviewed_at', 'created_user'])
            audit(request.user, action, 'registration_request', application.pk, {'account': application.account, 'role': application.requested_role}, request_id(request))
        return Response(RegistrationRequestSerializer(application).data)


class AdminUserListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not is_admin(request):
            return error_response('forbidden', 'Administrator permission is required.', 403)
        queryset = User.objects.select_related('profile').order_by('-date_joined', '-id')
        search = request.query_params.get('search', '').strip()
        if search:
            queryset = queryset.filter(Q(email__icontains=search) | Q(first_name__icontains=search) | Q(last_name__icontains=search) | Q(profile__display_name__icontains=search))
        active = request.query_params.get('active')
        if active:
            if active not in {'true', 'false'}:
                return error_response('invalid_request', 'active must be true or false.', 400)
            queryset = queryset.filter(is_active=active == 'true')
        return paginated(queryset, AdminUserSerializer, request)

    def post(self, request):
        if not is_admin(request):
            return error_response('forbidden', 'Administrator permission is required.', 403)
        payload = object_payload(request)
        if payload is None:
            return error_response('invalid_request', 'A JSON object body is required.', 400)
        email_value = payload.get('email', '')
        password_value = payload.get('password', '')
        display_name = payload.get('displayName', '')
        requested_role = payload.get('role', Profile.Role.OPERATOR)
        if not isinstance(email_value, str) or not isinstance(password_value, str) or not isinstance(display_name, str) or not isinstance(requested_role, str):
            return error_response('invalid_request', 'email, password, displayName and role must be strings.', 400)
        email = email_value.strip().lower()
        if not email or len(email) > 254:
            return error_response('invalid_request', 'A valid email is required.', 400)
        try:
            validate_email(email)
        except ValidationError:
            return error_response('invalid_request', 'A valid email is required.', 400)
        if User.objects.filter(email__iexact=email).exists():
            return error_response('conflict', 'A user with this email already exists.', 409)
        if requested_role not in Profile.Role.values:
            return error_response('invalid_request', 'role is not valid.', 400)
        if requested_role == Profile.Role.ADMINISTRATOR:
            return error_response('conflict', '系统仅保留一个管理员账号，不能新增管理员。', 409)
        if not password_value or len(password_value) < 12:
            return error_response('invalid_request', 'password must contain at least 12 characters.', 400)
        try:
            validate_password(password_value)
        except ValidationError:
            return error_response('invalid_request', 'password does not meet security requirements.', 400)
        with transaction.atomic():
            user = User.objects.create_user(username=f'user-{uuid4().hex}', email=email, password=password_value)
            profile = Profile.objects.create(user=user, display_name=display_name.strip()[:80], role=requested_role)
            audit(request.user, 'admin.user.created', 'app_user', user.pk, {'email': email, 'role': profile.role}, request_id(request))
        return Response(AdminUserSerializer(user).data, status=201)


class AdminUserDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def patch(self, request, pk):
        if not is_admin(request):
            return error_response('forbidden', 'Administrator permission is required.', 403)
        payload = object_payload(request)
        if payload is None:
            return error_response('invalid_request', 'A JSON object body is required.', 400)
        with transaction.atomic():
            user = User.objects.select_for_update().select_related('profile').filter(pk=pk).first()
            if not user:
                return error_response('not_found', 'User not found.', 404)
            default_role = Profile.Role.ADMINISTRATOR if user.is_superuser else Profile.Role.OPERATOR
            profile, _ = Profile.objects.get_or_create(user=user, defaults={'display_name': user.email, 'role': default_role})
            next_role = payload.get('role', Profile.Role.ADMINISTRATOR if user.is_superuser else profile.role)
            next_active = payload.get('isActive', user.is_active)
            next_name = payload.get('displayName', profile.display_name)
            password_value = payload.get('password')
            if not isinstance(next_role, str) or next_role not in Profile.Role.values:
                return error_response('invalid_request', 'role is not valid.', 400)
            if not isinstance(next_active, bool) or not isinstance(next_name, str):
                return error_response('invalid_request', 'isActive must be boolean and displayName must be a string.', 400)
            if password_value is not None and (not isinstance(password_value, str) or len(password_value) < 12):
                return error_response('invalid_request', 'password must contain at least 12 characters.', 400)
            if user.pk == request.user.pk and (not next_active or next_role != Profile.Role.ADMINISTRATOR):
                return error_response('conflict', 'You cannot disable or demote your own administrator account.', 409)
            if user.is_superuser and (not next_active or next_role != Profile.Role.ADMINISTRATOR):
                return error_response('conflict', 'The superuser administrator cannot be disabled or demoted here.', 409)
            currently_admin = profile.role == Profile.Role.ADMINISTRATOR or user.is_superuser
            if not currently_admin and next_role == Profile.Role.ADMINISTRATOR:
                return error_response('conflict', '系统仅保留一个管理员账号，不能提升其他账号。', 409)
            removing_admin = currently_admin and (not next_active or next_role != Profile.Role.ADMINISTRATOR)
            if removing_admin:
                remaining = Profile.objects.filter(role=Profile.Role.ADMINISTRATOR, user__is_active=True).exclude(user_id=user.pk).exists() or User.objects.filter(is_superuser=True, is_active=True).exclude(pk=user.pk).exists()
                if not remaining:
                    return error_response('conflict', 'At least one active administrator is required.', 409)
            if password_value is not None:
                try:
                    validate_password(password_value, user=user)
                except ValidationError:
                    return error_response('invalid_request', 'password does not meet security requirements.', 400)
                user.set_password(password_value)
            user.is_active = next_active
            user.save(update_fields=['is_active', 'password'])
            profile.display_name = next_name.strip()[:80]
            profile.role = next_role
            profile.save(update_fields=['display_name', 'role'])
            audit(request.user, 'admin.user.updated', 'app_user', user.pk, {'role': profile.role, 'isActive': user.is_active, 'passwordChanged': password_value is not None}, request_id(request))
        return Response(AdminUserSerializer(user).data)


class DashboardView(APIView):
    permission_classes = [AuthenticatedRead]

    def get(self, request):
        latest_telemetry = Telemetry.objects.select_related('asset').order_by('-recorded_at', '-id').first()
        return Response({
            'assets': {'total': Asset.objects.filter(is_active=True).count(), 'online': Asset.objects.filter(is_active=True, status__in=[Asset.Status.NORMAL, Asset.Status.WARNING, Asset.Status.ALARM]).count()},
            'health': {'value': 100 if not Asset.objects.filter(is_active=True, status=Asset.Status.ALARM).exists() else 72},
            'openAlerts': Alert.objects.filter(status=Alert.Status.OPEN).count(),
            'activeWorkOrders': WorkOrder.objects.exclude(status__in=[WorkOrder.Status.COMPLETED, WorkOrder.Status.CANCELLED]).count(),
            'telemetry': TelemetrySerializer(latest_telemetry).data if latest_telemetry else None,
        })


class TwinModelReadinessView(APIView):
    """Read-only Blender handoff contract; it does not assert model-file existence."""
    permission_classes = [AuthenticatedRead]

    def get(self, request):
        assets = Asset.objects.filter(is_active=True).only('code', 'mesh', 'updated_at').order_by('code')
        active_assets = list(assets)
        missing_mesh_codes = [asset.code for asset in active_assets if not asset.mesh]
        invalid_mesh_codes = [
            asset.code for asset in active_assets
            if asset.mesh and not re.fullmatch(r'[A-Z0-9][A-Z0-9_-]{1,79}', asset.mesh)
        ]
        mapped_asset_count = len(active_assets) - len(missing_mesh_codes) - len(invalid_mesh_codes)
        latest_update = max((asset.updated_at for asset in active_assets), default=None)
        return Response({
            'status': 'ready' if not missing_mesh_codes and not invalid_mesh_codes else 'blocked',
            'summary': {
                'activeAssetCount': len(active_assets),
                'mappedAssetCount': mapped_asset_count,
                'unmappedAssetCount': len(missing_mesh_codes) + len(invalid_mesh_codes),
            },
            'missingMeshCodes': missing_mesh_codes,
            'invalidMeshCodes': invalid_mesh_codes,
            'contract': {
                'nodeNamePattern': 'A-Z, 0-9, hyphen and underscore',
                'nodeNamesUnique': True,
                'modelFileVerified': False,
            },
            'updatedAt': latest_update,
        })


class AssetListView(APIView):
    permission_classes = [AuthenticatedRead]

    def get(self, request):
        queryset = Asset.objects.all()
        search = request.query_params.get('search', '').strip()
        if search:
            queryset = queryset.filter(Q(code__icontains=search) | Q(hardware_code__icontains=search) | Q(name__icontains=search) | Q(zone__icontains=search) | Q(interface__icontains=search))
        if request.query_params.get('status'):
            asset_status = request.query_params['status']
            if asset_status not in Asset.Status.values:
                return error_response('invalid_request', 'status is not a valid asset status.', 400)
            queryset = queryset.filter(status=asset_status)
        if request.query_params.get('zone'):
            queryset = queryset.filter(zone=request.query_params['zone'])
        if request.query_params.get('integrationStatus'):
            integration_status = request.query_params['integrationStatus']
            if integration_status not in Asset.IntegrationStatus.values:
                return error_response('invalid_request', 'integrationStatus is not valid.', 400)
            queryset = queryset.filter(integration_status=integration_status)
        if request.query_params.get('hardwareCode'):
            queryset = queryset.filter(hardware_code=request.query_params['hardwareCode'].strip())
        if request.query_params.get('hasLocation'):
            has_location = request.query_params['hasLocation'].lower()
            if has_location not in {'true', 'false'}:
                return error_response('invalid_request', 'hasLocation must be true or false.', 400)
            queryset = queryset.filter(latitude__isnull=has_location == 'false', longitude__isnull=has_location == 'false')
        active_filter = request.query_params.get('isActive', 'true').lower()
        if active_filter not in {'true', 'false', 'all'}:
            return error_response('invalid_request', 'isActive must be true, false or all.', 400)
        if active_filter == 'all' and not is_admin(request):
            return error_response('forbidden', 'Administrator permission is required to list all asset lifecycle states.', 403)
        if active_filter != 'all':
            queryset = queryset.filter(is_active=active_filter == 'true')
        return paginated(queryset, AssetSerializer, request)

    def post(self, request):
        if not is_admin(request):
            return error_response('forbidden', 'Administrator asset permission is required.', 403)
        payload = object_payload(request)
        if payload is None:
            return error_response('invalid_request', 'A JSON object body is required.', 400)
        serializer = AssetMutationSerializer(data=payload)
        if not serializer.is_valid():
            return error_response('validation_error', 'Asset data is invalid.', 400, serializer.errors)
        try:
            with transaction.atomic():
                asset = serializer.save(version=1)
                audit(request.user, 'asset.created', 'asset', asset.pk, {'code': asset.code, 'hardwareCode': asset.hardware_code}, request_id(request))
        except IntegrityError:
            return error_response('conflict', 'Asset code or hardware code already exists.', 409)
        return Response(AssetSerializer(asset).data, status=201)


class AssetDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def patch(self, request, pk):
        if not is_admin(request):
            return error_response('forbidden', 'Administrator asset permission is required.', 403)
        payload = object_payload(request)
        if payload is None:
            return error_response('invalid_request', 'A JSON object body is required.', 400)
        payload = payload.copy()
        requested_version = payload.pop('version', None)
        if isinstance(requested_version, bool):
            return error_response('invalid_request', 'version must be a positive number.', 400)
        try:
            requested_version = int(requested_version)
        except (TypeError, ValueError):
            return error_response('invalid_request', 'version is required and must be a positive number.', 400)
        if requested_version < 1:
            return error_response('invalid_request', 'version must be a positive number.', 400)
        if not payload:
            return error_response('invalid_request', 'At least one asset field must be supplied.', 400)
        try:
            with transaction.atomic():
                asset = Asset.objects.select_for_update().filter(pk=pk).first()
                if not asset:
                    return error_response('not_found', 'Asset not found.', 404)
                if requested_version != asset.version:
                    return error_response('version_conflict', 'Asset was changed by another request.', 409)
                serializer = AssetMutationSerializer(asset, data=payload, partial=True)
                if not serializer.is_valid():
                    return error_response('validation_error', 'Asset data is invalid.', 400, serializer.errors)
                deactivating = asset.is_active and serializer.validated_data.get('is_active') is False
                if deactivating and (
                    asset.alerts.filter(status__in=[Alert.Status.OPEN, Alert.Status.ACKNOWLEDGED]).exists()
                    or asset.work_orders.exclude(status__in=[WorkOrder.Status.COMPLETED, WorkOrder.Status.CANCELLED]).exists()
                ):
                    return error_response('asset_in_use', 'Resolve active alerts and work orders before deactivating this asset.', 409)
                changed_fields = sorted(payload.keys())
                asset = serializer.save(version=asset.version + 1)
                audit(request.user, 'asset.updated', 'asset', asset.pk, {'code': asset.code, 'fields': changed_fields, 'version': asset.version}, request_id(request))
        except IntegrityError:
            return error_response('conflict', 'Asset code or hardware code already exists.', 409)
        return Response(AssetSerializer(asset).data)


class SpatialFeatureListView(APIView):
    permission_classes = [AuthenticatedRead]

    def get(self, request):
        queryset = SpatialFeature.objects.all()
        layer_type = request.query_params.get('layerType', '').strip()
        if layer_type:
            if layer_type not in SpatialFeature.LayerType.values:
                return error_response('invalid_request', 'layerType is not valid.', 400)
            queryset = queryset.filter(layer_type=layer_type)
        requested_status = request.query_params.get('status', SpatialFeature.Status.PUBLISHED).strip()
        if requested_status == 'all':
            if not is_admin(request):
                return error_response('forbidden', 'Administrator permission is required to list unpublished GIS features.', 403)
        elif requested_status in SpatialFeature.Status.values:
            queryset = queryset.filter(status=requested_status)
        else:
            return error_response('invalid_request', 'status is not valid.', 400)
        bbox, error = _parse_bbox(request)
        if error:
            return error
        features = [_geojson_feature(feature) for feature in queryset[:1000] if _intersects_bbox(feature.geometry, bbox)]
        return Response({'type': 'FeatureCollection', 'features': features, 'meta': {'crs': 'EPSG:4326', 'count': len(features), 'bounded': bbox is not None}})

    def post(self, request):
        if not is_admin(request):
            return error_response('forbidden', 'Administrator GIS permission is required.', 403)
        payload = object_payload(request)
        if payload is None:
            return error_response('invalid_request', 'A JSON object body is required.', 400)
        serializer = SpatialFeatureMutationSerializer(data=payload)
        if not serializer.is_valid():
            return error_response('validation_error', 'GIS feature data is invalid.', 400, serializer.errors)
        try:
            with transaction.atomic():
                feature = serializer.save(version=1)
                audit(request.user, 'gis.feature.created', 'spatial_feature', feature.pk, {'code': feature.code, 'layerType': feature.layer_type, 'status': feature.status}, request_id(request))
        except IntegrityError:
            return error_response('conflict', 'GIS feature code already exists.', 409)
        return Response(_geojson_feature(feature), status=201)


class SpatialFeatureDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def patch(self, request, pk):
        if not is_admin(request):
            return error_response('forbidden', 'Administrator GIS permission is required.', 403)
        payload = object_payload(request)
        if payload is None:
            return error_response('invalid_request', 'A JSON object body is required.', 400)
        payload = payload.copy()
        requested_version = payload.pop('version', None)
        try:
            requested_version = int(requested_version)
        except (TypeError, ValueError):
            return error_response('invalid_request', 'version is required and must be a positive number.', 400)
        if requested_version < 1 or not payload:
            return error_response('invalid_request', 'version and at least one GIS feature field are required.', 400)
        try:
            with transaction.atomic():
                feature = SpatialFeature.objects.select_for_update().filter(pk=pk).first()
                if not feature:
                    return error_response('not_found', 'GIS feature not found.', 404)
                if feature.version != requested_version:
                    return error_response('version_conflict', 'GIS feature was changed by another request.', 409)
                serializer = SpatialFeatureMutationSerializer(feature, data=payload, partial=True)
                if not serializer.is_valid():
                    return error_response('validation_error', 'GIS feature data is invalid.', 400, serializer.errors)
                fields = sorted(payload)
                feature = serializer.save(version=feature.version + 1)
                audit(request.user, 'gis.feature.updated', 'spatial_feature', feature.pk, {'code': feature.code, 'fields': fields, 'version': feature.version}, request_id(request))
        except IntegrityError:
            return error_response('conflict', 'GIS feature code already exists.', 409)
        return Response(_geojson_feature(feature))


class SpatialFeatureImportView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        if not is_admin(request):
            return error_response('forbidden', 'Administrator GIS permission is required.', 403)
        payload = object_payload(request)
        features = payload.get('features') if payload and payload.get('type') == 'FeatureCollection' else None
        if not isinstance(features, list) or not 1 <= len(features) <= 100:
            return error_response('invalid_request', 'A GeoJSON FeatureCollection with 1 to 100 features is required.', 400)
        serializers = []
        for index, item in enumerate(features):
            if not isinstance(item, Mapping) or item.get('type') != 'Feature' or not isinstance(item.get('properties'), Mapping):
                return error_response('validation_error', 'Each import item must be a GeoJSON Feature with properties.', 400, {str(index): 'invalid_feature'})
            feature_payload = {**item['properties'], 'geometry': item.get('geometry')}
            serializer = SpatialFeatureMutationSerializer(data=feature_payload)
            if not serializer.is_valid():
                return error_response('validation_error', 'GIS import data is invalid; no records were created.', 400, {str(index): serializer.errors})
            serializers.append(serializer)
        try:
            with transaction.atomic():
                created = [serializer.save(version=1) for serializer in serializers]
                audit(request.user, 'gis.feature.imported', 'spatial_feature', 'bulk', {'count': len(created), 'codes': [feature.code for feature in created]}, request_id(request))
        except IntegrityError:
            return error_response('conflict', 'One or more GIS feature codes already exist; no records were created.', 409)
        return Response({'type': 'FeatureCollection', 'features': [_geojson_feature(feature) for feature in created], 'meta': {'created': len(created), 'crs': 'EPSG:4326'}}, status=201)


class HardwareBindingListView(APIView):
    permission_classes = [AuthenticatedRead]

    def get(self, request):
        queryset = HardwareBinding.objects.select_related('asset')
        asset_code = request.query_params.get('assetCode', '').strip()
        if asset_code:
            queryset = queryset.filter(asset__code=asset_code)
        return paginated(queryset, HardwareBindingSerializer, request, ordering=('asset__code',))

    def post(self, request):
        if not is_admin(request):
            return error_response('forbidden', 'Administrator hardware binding permission is required.', 403)
        payload = object_payload(request)
        if payload is None:
            return error_response('invalid_request', 'A JSON object body is required.', 400)
        serializer = HardwareBindingMutationSerializer(data=payload)
        if not serializer.is_valid():
            return error_response('validation_error', 'Hardware binding data is invalid.', 400, serializer.errors)
        try:
            with transaction.atomic():
                binding = serializer.save(version=1)
                audit(request.user, 'hardware.binding.created', 'hardware_binding', binding.pk, {'assetCode': binding.asset.code, 'protocol': binding.protocol, 'status': binding.status}, request_id(request))
        except IntegrityError:
            return error_response('conflict', 'An active binding or device identifier already exists.', 409)
        return Response(HardwareBindingSerializer(binding).data, status=201)


class HardwareBindingDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def patch(self, request, pk):
        if not is_admin(request):
            return error_response('forbidden', 'Administrator hardware binding permission is required.', 403)
        payload = object_payload(request)
        if payload is None:
            return error_response('invalid_request', 'A JSON object body is required.', 400)
        payload = payload.copy()
        requested_version = payload.pop('version', None)
        try:
            requested_version = int(requested_version)
        except (TypeError, ValueError):
            return error_response('invalid_request', 'version is required and must be a positive number.', 400)
        if requested_version < 1 or not payload:
            return error_response('invalid_request', 'version and at least one hardware binding field are required.', 400)
        try:
            with transaction.atomic():
                binding = HardwareBinding.objects.select_for_update().select_related('asset').filter(pk=pk).first()
                if not binding:
                    return error_response('not_found', 'Hardware binding not found.', 404)
                if binding.version != requested_version:
                    return error_response('version_conflict', 'Hardware binding was changed by another request.', 409)
                serializer = HardwareBindingMutationSerializer(binding, data=payload, partial=True)
                if not serializer.is_valid():
                    return error_response('validation_error', 'Hardware binding data is invalid.', 400, serializer.errors)
                fields = sorted(payload)
                binding = serializer.save(version=binding.version + 1)
                audit(request.user, 'hardware.binding.updated', 'hardware_binding', binding.pk, {'assetCode': binding.asset.code, 'fields': fields, 'version': binding.version}, request_id(request))
        except IntegrityError:
            return error_response('conflict', 'deviceIdentifier already exists.', 409)
        return Response(HardwareBindingSerializer(binding).data)


class AlertListView(APIView):
    permission_classes = [AuthenticatedRead]

    def get(self, request):
        queryset = Alert.objects.select_related('asset', 'acknowledged_by')
        if request.query_params.get('status'):
            alert_status = request.query_params['status']
            if alert_status not in Alert.Status.values:
                return error_response('invalid_request', 'status is not a valid alert status.', 400)
            queryset = queryset.filter(status=alert_status)
        if request.query_params.get('severity'):
            severity = request.query_params['severity']
            if severity not in Alert.Severity.values:
                return error_response('invalid_request', 'severity is not a valid alert severity.', 400)
            queryset = queryset.filter(severity=severity)
        opened_from, error = datetime_filter(request, 'openedFrom')
        if error:
            return error
        opened_to, error = datetime_filter(request, 'openedTo')
        if error:
            return error
        if opened_from:
            queryset = queryset.filter(opened_at__gte=opened_from)
        if opened_to:
            queryset = queryset.filter(opened_at__lte=opened_to)
        if opened_from and opened_to and opened_from > opened_to:
            return error_response('invalid_request', 'openedFrom must be earlier than openedTo.', 400)
        return paginated(queryset, AlertSerializer, request)


class AlertAcknowledgeView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        if not can_write(request):
            return error_response('forbidden', 'Alert acknowledgement permission is required.', 403)
        with transaction.atomic():
            alert = Alert.objects.select_for_update().filter(pk=pk).first()
            if not alert:
                return error_response('not_found', 'Alert not found.', 404)
            # Acknowledgement is intentionally idempotent.  A second click,
            # browser retry, or another operator completing the same action
            # must return the current result rather than an opaque 409.
            if alert.status == Alert.Status.ACKNOWLEDGED:
                return Response(AlertSerializer(alert).data)
            if alert.status != Alert.Status.OPEN:
                return error_response('invalid_state', 'Only open alerts can be acknowledged.', 409)
            alert.status = Alert.Status.ACKNOWLEDGED
            alert.acknowledged_at = timezone.now()
            alert.acknowledged_by = request.user
            alert.save(update_fields=['status', 'acknowledged_at', 'acknowledged_by'])
            audit(request.user, 'alert.acknowledged', 'alert', alert.pk, {'code': alert.code}, request_id(request))
        return Response(AlertSerializer(alert).data)


class AlertWorkOrderView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        if not can_write(request):
            return error_response('forbidden', 'Work order permission is required.', 403)
        try:
            with transaction.atomic():
                alert = Alert.objects.select_for_update().select_related('asset').filter(pk=pk).first()
                if not alert or not alert.asset:
                    return error_response('invalid_state', 'Alert is not eligible for a work order.', 409)
                existing = WorkOrder.objects.select_related('asset', 'source_alert', 'assignee').filter(source_alert=alert).first()
                if existing:
                    return Response(WorkOrderSerializer(existing).data)
                if alert.status not in {Alert.Status.OPEN, Alert.Status.ACKNOWLEDGED}:
                    return error_response('invalid_state', 'Alert is not eligible for a work order.', 409)
                order = WorkOrder.objects.create(code=work_order_code(), source_alert=alert, asset=alert.asset, title=f'处置 {alert.code}：{alert.title}', priority=WorkOrder.Priority.URGENT if alert.severity == Alert.Severity.CRITICAL else WorkOrder.Priority.HIGH, created_by=request.user, due_at=timezone.now() + timedelta(hours=8))
                audit(request.user, 'work_order.created_from_alert', 'work_order', order.pk, {'alertCode': alert.code}, request_id(request))
        except IntegrityError:
            # A concurrent request may create the same linked order first.
            existing = WorkOrder.objects.select_related('asset', 'source_alert', 'assignee').filter(source_alert_id=pk).first()
            if existing:
                return Response(WorkOrderSerializer(existing).data)
            return error_response('conflict', 'A linked work order already exists.', 409)
        return Response(WorkOrderSerializer(order).data, status=201)


class WorkOrderListView(APIView):
    permission_classes = [AuthenticatedRead]

    def get(self, request):
        queryset = WorkOrder.objects.select_related('asset', 'source_alert', 'assignee')
        if request.query_params.get('status'):
            work_order_status = request.query_params['status']
            if work_order_status not in WorkOrder.Status.values:
                return error_response('invalid_request', 'status is not a valid work order status.', 400)
            queryset = queryset.filter(status=work_order_status)
        if request.query_params.get('search'):
            search = request.query_params['search'].strip()
            queryset = queryset.filter(Q(code__icontains=search) | Q(title__icontains=search) | Q(asset__code__icontains=search))
        updated_from, error = datetime_filter(request, 'updatedFrom')
        if error:
            return error
        updated_to, error = datetime_filter(request, 'updatedTo')
        if error:
            return error
        if updated_from:
            queryset = queryset.filter(updated_at__gte=updated_from)
        if updated_to:
            queryset = queryset.filter(updated_at__lte=updated_to)
        if updated_from and updated_to and updated_from > updated_to:
            return error_response('invalid_request', 'updatedFrom must be earlier than updatedTo.', 400)
        return paginated(queryset, WorkOrderSerializer, request)

    def post(self, request):
        if not can_write(request):
            return error_response('forbidden', 'Work order permission is required.', 403)
        payload = object_payload(request)
        if payload is None:
            return error_response('invalid_request', 'A JSON object body is required.', 400)
        request_key, key_error = get_idempotency_key(request)
        if key_error:
            return key_error
        if request_key:
            existing = WorkOrder.objects.select_related('asset', 'source_alert', 'assignee').filter(idempotency_key=request_key).first()
            if existing:
                if existing.created_by_id != request.user.pk:
                    return error_response('conflict', 'Idempotency-Key is already used by another user.', 409)
                same_payload = (
                    str(payload.get('assetCode', '')).strip() == existing.asset.code
                    and str(payload.get('title', '')).strip() == existing.title
                    and str(payload.get('description', '')).strip() == existing.description
                    and payload.get('priority', WorkOrder.Priority.NORMAL) == existing.priority
                )
                if not same_payload:
                    return error_response('conflict', 'Idempotency-Key cannot be reused with a different payload.', 409)
                return Response(WorkOrderSerializer(existing).data, status=200)
        asset_code = payload.get('assetCode')
        title_value = payload.get('title', '')
        description_value = payload.get('description', '')
        if not isinstance(asset_code, str) or not isinstance(title_value, str) or not isinstance(description_value, str):
            return error_response('invalid_request', 'assetCode, title and description must be strings.', 400)
        asset = Asset.objects.filter(code=asset_code.strip()).first()
        title = title_value.strip()
        priority = payload.get('priority', WorkOrder.Priority.NORMAL)
        if not asset or not title or not isinstance(priority, str) or priority not in WorkOrder.Priority.values:
            return error_response('invalid_request', 'A valid assetCode and title are required.', 400)
        try:
            with transaction.atomic():
                order = WorkOrder.objects.create(code=work_order_code(), asset=asset, title=title, description=description_value.strip(), priority=priority, created_by=request.user, idempotency_key=request_key)
                audit(request.user, 'work_order.created_manual', 'work_order', order.pk, {'assetCode': asset.code}, request_id(request))
        except IntegrityError:
            # A simultaneous retry may win the unique idempotency constraint.
            if request_key:
                existing = WorkOrder.objects.select_related('asset', 'source_alert', 'assignee').filter(idempotency_key=request_key).first()
                if existing and existing.created_by_id == request.user.pk:
                    return Response(WorkOrderSerializer(existing).data, status=200)
            return error_response('conflict', 'Work order could not be created because a unique value already exists.', 409)
        response = Response(WorkOrderSerializer(order).data, status=201)
        if request_key:
            response['Idempotency-Key'] = request_key
        return response


TRANSITIONS = {
    WorkOrder.Status.DRAFT: {WorkOrder.Status.OPEN, WorkOrder.Status.CANCELLED},
    WorkOrder.Status.OPEN: {WorkOrder.Status.ASSIGNED, WorkOrder.Status.CANCELLED},
    WorkOrder.Status.ASSIGNED: {WorkOrder.Status.IN_PROGRESS, WorkOrder.Status.CANCELLED},
    WorkOrder.Status.IN_PROGRESS: {WorkOrder.Status.PENDING_REVIEW, WorkOrder.Status.CANCELLED},
    WorkOrder.Status.PENDING_REVIEW: {WorkOrder.Status.COMPLETED, WorkOrder.Status.IN_PROGRESS},
    WorkOrder.Status.COMPLETED: set(),
    WorkOrder.Status.CANCELLED: set(),
}


class WorkOrderTransitionView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        if not can_write(request):
            return error_response('forbidden', 'Work order permission is required.', 403)
        payload = object_payload(request)
        if payload is None:
            return error_response('invalid_request', 'A JSON object body is required.', 400)
        target = payload.get('to')
        if not isinstance(target, str):
            return error_response('invalid_request', 'to must be a work order status string.', 400)
        requested_version = payload.get('version')
        if requested_version is not None:
            try:
                requested_version = int(requested_version)
            except (TypeError, ValueError):
                return error_response('invalid_request', 'version must be a number.', 400)
            if requested_version < 1:
                return error_response('invalid_request', 'version must be a positive number.', 400)
        with transaction.atomic():
            order = WorkOrder.objects.select_for_update().select_related('source_alert', 'asset').filter(pk=pk).first()
            if not order:
                return error_response('not_found', 'Work order not found.', 404)
            if requested_version is not None and requested_version != order.version:
                return error_response('version_conflict', 'Work order was changed by another request.', 409)
            if target not in TRANSITIONS.get(order.status, set()):
                return error_response('invalid_transition', 'Invalid work order transition.', 409)
            if target == WorkOrder.Status.COMPLETED and role(request) != Profile.Role.ADMINISTRATOR:
                return error_response('forbidden', 'Administrator review permission is required.', 403)
            previous = order.status
            order.status = target
            if target == WorkOrder.Status.ASSIGNED:
                order.assignee = request.user
            if target == WorkOrder.Status.COMPLETED:
                order.completed_at = timezone.now()
                order.reviewed_by = request.user
                if order.source_alert and order.source_alert.status in {Alert.Status.OPEN, Alert.Status.ACKNOWLEDGED}:
                    order.source_alert.status = Alert.Status.RESOLVED
                    order.source_alert.resolved_at = timezone.now()
                    order.source_alert.save(update_fields=['status', 'resolved_at'])
                    if not Alert.objects.filter(asset=order.asset, status__in=[Alert.Status.OPEN, Alert.Status.ACKNOWLEDGED]).exclude(pk=order.source_alert_id).exists():
                        order.asset.status = Asset.Status.NORMAL
                        order.asset.save(update_fields=['status', 'updated_at'])
            order.version += 1
            # Keep the runtime database role least-privileged: transition writes
            # only the lifecycle fields instead of every model column.
            order.save(update_fields=['status', 'assignee', 'completed_at', 'reviewed_by', 'version', 'updated_at'])
            audit(request.user, 'work_order.transitioned', 'work_order', order.pk, {'from': previous, 'to': target}, request_id(request))
        return Response(WorkOrderSerializer(order).data)


class TelemetryListView(APIView):
    permission_classes = [AuthenticatedRead]

    def get(self, request):
        queryset, error = filtered_telemetry(request)
        if error:
            return error
        return paginated(queryset, TelemetrySerializer, request, ordering=('-recorded_at', '-id'))

    def post(self, request):
        if not can_write(request):
            return error_response('forbidden', 'Telemetry ingestion permission is required.', 403)
        payload = object_payload(request)
        if payload is None or not isinstance(payload.get('readings'), list):
            return error_response('invalid_request', 'A JSON object with a readings array is required.', 400)
        readings = payload['readings']
        if not 1 <= len(readings) <= 100:
            return error_response('invalid_request', 'readings must contain between 1 and 100 items.', 400)
        serializer = TelemetryReadingSerializer(data=readings, many=True)
        if not serializer.is_valid():
            return error_response('validation_error', 'Telemetry batch is invalid.', 400, serializer.errors)
        validated = serializer.validated_data
        event_ids = [item['eventId'] for item in validated]
        if len(event_ids) != len(set(event_ids)):
            return error_response('validation_error', 'eventId values must be unique within a batch.', 400, {'eventId': ['Duplicate eventId in batch.']})

        try:
            with transaction.atomic():
                asset_codes = {item['assetCode'] for item in validated}
                assets = Asset.objects.select_for_update().filter(code__in=asset_codes).in_bulk(field_name='code')
                invalid_assets = sorted(code for code in asset_codes if code not in assets or not assets[code].is_active)
                if invalid_assets:
                    return error_response('validation_error', 'Telemetry references missing or inactive assets.', 400, {'assetCode': invalid_assets})
                metric_keys = {item['metricKey'] for item in validated}
                thresholds = Threshold.objects.filter(key__in=metric_keys).in_bulk(field_name='key')
                unit_errors = sorted({item['metricKey'] for item in validated if item['metricKey'] in thresholds and item['unit'] != thresholds[item['metricKey']].unit})
                if unit_errors:
                    return error_response('validation_error', 'Telemetry units must match configured threshold units.', 400, {'metricKey': unit_errors})

                existing = Telemetry.objects.select_related('asset').filter(event_id__in=event_ids).in_bulk(field_name='event_id')
                for item in validated:
                    prior = existing.get(item['eventId'])
                    if prior and not telemetry_matches(prior, item):
                        return error_response(
                            'idempotency_conflict',
                            'An eventId was already used with different telemetry data.',
                            409,
                            {'eventId': item['eventId']},
                        )

                stored = []
                created_count = 0
                duplicate_count = 0
                rule_counts = {}
                for item in validated:
                    prior = existing.get(item['eventId'])
                    if prior:
                        stored.append(prior)
                        duplicate_count += 1
                        continue
                    asset = assets[item['assetCode']]
                    reading = Telemetry.objects.create(
                        asset=asset,
                        event_id=item['eventId'],
                        metric_key=item['metricKey'],
                        metric=item['metric'],
                        value=item['value'],
                        unit=item['unit'],
                        quality=item['quality'],
                        recorded_at=item['recordedAt'],
                    )
                    if asset.last_seen_at is None or item['recordedAt'] > asset.last_seen_at:
                        asset.last_seen_at = item['recordedAt']
                        asset.save(update_fields=['last_seen_at', 'updated_at'])
                    threshold = thresholds.get(item['metricKey'])
                    action = evaluate_threshold(reading, threshold, request.user, request_id(request)).action if threshold else 'no_rule'
                    rule_counts[action] = rule_counts.get(action, 0) + 1
                    stored.append(reading)
                    created_count += 1
                if created_count:
                    audit(request.user, 'telemetry.batch_ingested', 'telemetry_batch', '', {'created': created_count, 'duplicates': duplicate_count, 'rules': rule_counts}, request_id(request))
        except IntegrityError:
            return error_response('conflict', 'Telemetry ingestion conflicted with a concurrent request. Retry the same eventId values.', 409)
        return Response({
            'items': TelemetrySerializer(stored, many=True).data,
            'created': created_count,
            'duplicates': duplicate_count,
            'rules': rule_counts,
        }, status=201 if created_count else 200)


class TelemetrySummaryView(APIView):
    permission_classes = [AuthenticatedRead]

    def get(self, request):
        queryset, error = filtered_telemetry(request)
        if error:
            return error
        aggregate = queryset.aggregate(
            sample_count=Count('id'),
            started_at=Min('recorded_at'),
            ended_at=Max('recorded_at'),
            metric_count=Count('metric_key', distinct=True),
            unit_count=Count('unit', distinct=True),
        )
        comparable = aggregate['metric_count'] <= 1 and aggregate['unit_count'] <= 1
        values = queryset.aggregate(minimum=Min('value'), maximum=Max('value'), average=Avg('value')) if comparable else {'minimum': None, 'maximum': None, 'average': None}
        quality_counts = {quality: 0 for quality in Telemetry.Quality.values}
        for row in queryset.values('quality').annotate(count=Count('id')):
            quality_counts[row['quality']] = row['count']
        latest = queryset.order_by('-recorded_at', '-id').first()
        return Response({
            'sampleCount': aggregate['sample_count'],
            'comparable': comparable,
            'minimum': values['minimum'],
            'maximum': values['maximum'],
            'average': values['average'],
            'startedAt': aggregate['started_at'],
            'endedAt': aggregate['ended_at'],
            'qualityCounts': quality_counts,
            'latest': TelemetrySerializer(latest).data if latest else None,
        })


class ThresholdListView(APIView):
    permission_classes = [AuthenticatedRead]

    def get(self, request):
        return Response({'items': ThresholdSerializer(Threshold.objects.order_by('key'), many=True).data})


class ThresholdDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def put(self, request, key):
        if role(request) != Profile.Role.ADMINISTRATOR:
            return error_response('forbidden', 'Threshold write permission is required.', 403)
        payload = object_payload(request)
        if payload is None:
            return error_response('invalid_request', 'A JSON object body is required.', 400)
        with transaction.atomic():
            try:
                threshold = Threshold.objects.select_for_update().get(key=key)
            except Threshold.DoesNotExist:
                return error_response('not_found', 'Threshold not found.', 404)
            try:
                warning = float(payload.get('warning'))
                alarm = float(payload.get('alarm'))
            except (TypeError, ValueError):
                return error_response('invalid_request', 'A valid threshold key and values are required.', 400)
            if not isfinite(warning) or not isfinite(alarm) or warning < 0 or alarm <= warning:
                return error_response('invalid_request', 'Alarm must be greater than warning.', 400)
            if payload.get('version') is not None:
                try:
                    version = int(payload['version'])
                except (TypeError, ValueError):
                    return error_response('invalid_request', 'version must be a number.', 400)
                if version != threshold.version:
                    return error_response('version_conflict', 'Threshold was changed by another request.', 409)
            threshold.warning, threshold.alarm, threshold.version = warning, alarm, threshold.version + 1
            threshold.save(update_fields=['warning', 'alarm', 'version', 'updated_at'])
            audit(request.user, 'setting.threshold.update', 'threshold', threshold.key, {'version': threshold.version}, request_id(request))
            return Response(ThresholdSerializer(threshold).data)


class AuditListView(APIView):
    permission_classes = [AuthenticatedRead]

    def get(self, request):
        queryset = AuditLog.objects.select_related('actor')
        action = request.query_params.get('action', '').strip()
        if action:
            queryset = queryset.filter(action__icontains=action)
        search = request.query_params.get('search', '').strip()
        if search:
            queryset = queryset.filter(
                Q(action__icontains=search)
                | Q(resource_type__icontains=search)
                | Q(resource_id__icontains=search)
                | Q(actor__email__icontains=search)
            )
        occurred_from, error = datetime_filter(request, 'occurredFrom')
        if error:
            return error
        occurred_to, error = datetime_filter(request, 'occurredTo')
        if error:
            return error
        if occurred_from:
            queryset = queryset.filter(occurred_at__gte=occurred_from)
        if occurred_to:
            queryset = queryset.filter(occurred_at__lte=occurred_to)
        if occurred_from and occurred_to and occurred_from > occurred_to:
            return error_response('invalid_request', 'occurredFrom must be earlier than occurredTo.', 400)
        return paginated(queryset, AuditSerializer, request)


class ReportExportView(APIView):
    permission_classes = [AuthenticatedRead]

    def get(self, request):
        return paginated(ReportExport.objects.all(), ReportExportSerializer, request)

    def post(self, request):
        payload = object_payload(request)
        if payload is None:
            return error_response('invalid_request', 'A JSON object body is required.', 400)
        request_key, key_error = get_idempotency_key(request)
        if key_error:
            return key_error
        report_value = payload.get('report', '')
        if not isinstance(report_value, str):
            return error_response('invalid_request', 'A valid report type is required.', 400)
        report_type = report_value.strip()
        if report_type not in {'alerts', 'workOrders', 'assets', 'daily'}:
            return error_response('invalid_request', 'A valid report type is required.', 400)
        if request_key:
            existing = ReportExport.objects.filter(idempotency_key=request_key).first()
            if existing:
                if existing.requested_by_id != request.user.pk:
                    return error_response('conflict', 'Idempotency-Key is already used by another user.', 409)
                if existing.report_type != report_type:
                    return error_response('conflict', 'Idempotency-Key cannot be reused with a different report.', 409)
                return Response(ReportExportSerializer(existing).data, status=200)
        try:
            with transaction.atomic():
                record = ReportExport.objects.create(report_type=report_type, file_name=f'utility-tunnel-{report_type}-{timezone.now():%Y%m%d%H%M%S}.csv', requested_by=request.user, completed_at=timezone.now(), idempotency_key=request_key)
                audit(request.user, 'report.export', 'report_export', record.pk, {'report': report_type}, request_id(request))
        except IntegrityError:
            if request_key:
                existing = ReportExport.objects.filter(idempotency_key=request_key).first()
                if existing and existing.requested_by_id == request.user.pk:
                    return Response(ReportExportSerializer(existing).data, status=200)
            return error_response('conflict', 'Report export could not be created because a unique value already exists.', 409)
        response = Response(ReportExportSerializer(record).data, status=201)
        if request_key:
            response['Idempotency-Key'] = request_key
        return response
