from datetime import timedelta
from collections.abc import Mapping
from math import isfinite
from uuid import uuid4
from django.conf import settings
from django.contrib.auth import authenticate
from django.contrib.auth.models import User
from django.db import connection, transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework import status
from rest_framework.authentication import TokenAuthentication
from rest_framework.authtoken.models import Token
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Alert, Asset, AuditLog, Profile, ReportExport, Telemetry, Threshold, WorkOrder
from .permissions import AuthenticatedRead
from .serializers import AlertSerializer, AssetSerializer, AuditSerializer, ReportExportSerializer, TelemetrySerializer, ThresholdSerializer, WorkOrderSerializer
from .services import actor_name, audit
from .throttling import LoginRateThrottle


def request_id(request) -> str:
    return getattr(request, 'request_id', request.headers.get('X-Request-Id', ''))


def object_payload(request):
    """Return an object payload or ``None`` for malformed JSON bodies."""
    return request.data if isinstance(request.data, Mapping) else None


def error_response(code: str, message: str, status_code: int):
    return Response({'error': code, 'message': message, 'details': {}}, status=status_code)


def paginated(queryset, serializer_class, request):
    try:
        page = max(1, int(request.query_params.get('page', '1')))
        page_size = min(100, max(1, int(request.query_params.get('pageSize', '20'))))
    except ValueError:
        return error_response('invalid_request', 'page and pageSize must be numbers.', 400)
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


def work_order_code() -> str:
    """Generate a collision-resistant human-readable work-order code."""
    return f'WO-{timezone.now():%y%m%d}-{uuid4().hex[:6].upper()}'


class HealthView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request):
        return Response({'status': 'ok', 'service': 'utility-tunnel-django', 'time': timezone.now()})


class ReadyView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request):
        try:
            with connection.cursor() as cursor:
                cursor.execute('SELECT 1')
                cursor.fetchone()
        except Exception:
            return error_response('not_ready', 'Database is not ready.', 503)
        return Response({'status': 'ready', 'service': 'utility-tunnel-django', 'time': timezone.now()})


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
        user = User.objects.filter(email__iexact=email, is_active=True).first()
        authenticated = authenticate(username=user.username if user else email, password=password)
        if not authenticated:
            return error_response('invalid_credentials', 'Invalid email or password.', 401)
        token = Token.objects.filter(user=authenticated).first()
        if token and token.created + timedelta(seconds=settings.API_TOKEN_TTL_SECONDS) <= timezone.now():
            token.delete()
            token = None
        token = token or Token.objects.create(user=authenticated)
        profile, _ = Profile.objects.get_or_create(user=authenticated, defaults={'display_name': authenticated.get_full_name() or authenticated.email})
        authenticated.last_login = timezone.now()
        authenticated.save(update_fields=['last_login'])
        audit(authenticated, 'auth.login', 'app_user', authenticated.pk, {'email': authenticated.email}, request_id(request))
        return Response({'accessToken': token.key, 'tokenType': 'Bearer', 'user': {'id': authenticated.pk, 'email': authenticated.email, 'displayName': profile.display_name or authenticated.email, 'role': profile.role}})


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


class DashboardView(APIView):
    permission_classes = [AuthenticatedRead]

    def get(self, request):
        return Response({
            'assets': {'total': Asset.objects.count(), 'online': Asset.objects.exclude(status=Asset.Status.OFFLINE).count()},
            'health': {'value': 100 if not Asset.objects.filter(status=Asset.Status.ALARM).exists() else 72},
            'openAlerts': Alert.objects.filter(status=Alert.Status.OPEN).count(),
            'activeWorkOrders': WorkOrder.objects.exclude(status__in=[WorkOrder.Status.COMPLETED, WorkOrder.Status.CANCELLED]).count(),
            'telemetry': TelemetrySerializer(Telemetry.objects.select_related('asset').first()).data if Telemetry.objects.exists() else None,
        })


class AssetListView(APIView):
    permission_classes = [AuthenticatedRead]

    def get(self, request):
        queryset = Asset.objects.all()
        search = request.query_params.get('search', '').strip()
        if search:
            queryset = queryset.filter(Q(code__icontains=search) | Q(name__icontains=search) | Q(zone__icontains=search))
        if request.query_params.get('status'):
            asset_status = request.query_params['status']
            if asset_status not in Asset.Status.values:
                return error_response('invalid_request', 'status is not a valid asset status.', 400)
            queryset = queryset.filter(status=asset_status)
        if request.query_params.get('zone'):
            queryset = queryset.filter(zone=request.query_params['zone'])
        return paginated(queryset, AssetSerializer, request)


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
        with transaction.atomic():
            alert = Alert.objects.select_for_update().select_related('asset').filter(pk=pk).first()
            if not alert or not alert.asset or alert.status not in {Alert.Status.OPEN, Alert.Status.ACKNOWLEDGED}:
                return error_response('invalid_state', 'Alert is not eligible for a work order.', 409)
            if WorkOrder.objects.filter(source_alert=alert).exists():
                return error_response('conflict', 'A linked work order already exists.', 409)
            order = WorkOrder.objects.create(code=work_order_code(), source_alert=alert, asset=alert.asset, title=f'处置 {alert.code}：{alert.title}', priority=WorkOrder.Priority.URGENT if alert.severity == Alert.Severity.CRITICAL else WorkOrder.Priority.HIGH, created_by=request.user, due_at=timezone.now() + timedelta(hours=8))
            audit(request.user, 'work_order.created_from_alert', 'work_order', order.pk, {'alertCode': alert.code}, request_id(request))
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
        return paginated(queryset, WorkOrderSerializer, request)

    def post(self, request):
        if not can_write(request):
            return error_response('forbidden', 'Work order permission is required.', 403)
        payload = object_payload(request)
        if payload is None:
            return error_response('invalid_request', 'A JSON object body is required.', 400)
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
        order = WorkOrder.objects.create(code=work_order_code(), asset=asset, title=title, description=description_value.strip(), priority=priority, created_by=request.user)
        audit(request.user, 'work_order.created_manual', 'work_order', order.pk, {'assetCode': asset.code}, request_id(request))
        return Response(WorkOrderSerializer(order).data, status=201)


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
        with transaction.atomic():
            order = WorkOrder.objects.select_for_update().select_related('source_alert', 'asset').filter(pk=pk).first()
            if not order:
                return error_response('not_found', 'Work order not found.', 404)
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
        queryset = Telemetry.objects.select_related('asset')
        if request.query_params.get('assetCode'):
            queryset = queryset.filter(asset__code=request.query_params['assetCode'])
        return paginated(queryset, TelemetrySerializer, request)


class ThresholdListView(APIView):
    permission_classes = [AuthenticatedRead]

    def get(self, request):
        return Response({'items': ThresholdSerializer(Threshold.objects.all(), many=True).data})


class ThresholdDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def put(self, request, key):
        if role(request) != Profile.Role.ADMINISTRATOR:
            return error_response('forbidden', 'Threshold write permission is required.', 403)
        payload = object_payload(request)
        if payload is None:
            return error_response('invalid_request', 'A JSON object body is required.', 400)
        try:
            threshold = Threshold.objects.get(key=key)
            warning = float(payload.get('warning'))
            alarm = float(payload.get('alarm'))
        except (Threshold.DoesNotExist, TypeError, ValueError):
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
        if request.query_params.get('action'):
            queryset = queryset.filter(action__icontains=request.query_params['action'])
        return paginated(queryset, AuditSerializer, request)


class ReportExportView(APIView):
    permission_classes = [AuthenticatedRead]

    def get(self, request):
        return paginated(ReportExport.objects.all(), ReportExportSerializer, request)

    def post(self, request):
        payload = object_payload(request)
        if payload is None:
            return error_response('invalid_request', 'A JSON object body is required.', 400)
        report_value = payload.get('report', '')
        if not isinstance(report_value, str):
            return error_response('invalid_request', 'A valid report type is required.', 400)
        report_type = report_value.strip()
        if report_type not in {'alerts', 'workOrders', 'assets', 'daily'}:
            return error_response('invalid_request', 'A valid report type is required.', 400)
        record = ReportExport.objects.create(report_type=report_type, file_name=f'utility-tunnel-{report_type}-{timezone.now():%Y%m%d%H%M%S}.csv', requested_by=request.user, completed_at=timezone.now())
        audit(request.user, 'report.export', 'report_export', record.pk, {'report': report_type}, request_id(request))
        return Response(ReportExportSerializer(record).data, status=201)
