from django.urls import path
from .views import AdminUserDetailView, AdminUserListView, AlertAcknowledgeView, AlertListView, AlertWorkOrderView, AssetListView, AuditListView, DashboardView, HealthView, LoginView, LogoutView, MeView, ReadyView, ReportExportView, TelemetryListView, ThresholdDetailView, ThresholdListView, WorkOrderListView, WorkOrderTransitionView


urlpatterns = [
    path('health/', HealthView.as_view()),
    path('ready/', ReadyView.as_view()),
    path('auth/login/', LoginView.as_view()),
    path('auth/me/', MeView.as_view()),
    path('auth/logout/', LogoutView.as_view()),
    path('admin/users/', AdminUserListView.as_view()),
    path('admin/users/<int:pk>/', AdminUserDetailView.as_view()),
    path('dashboard/', DashboardView.as_view()),
    path('assets/', AssetListView.as_view()),
    path('alerts/', AlertListView.as_view()),
    path('alerts/<int:pk>/acknowledge/', AlertAcknowledgeView.as_view()),
    path('alerts/<int:pk>/work-order/', AlertWorkOrderView.as_view()),
    path('work-orders/', WorkOrderListView.as_view()),
    path('work-orders/<int:pk>/transition/', WorkOrderTransitionView.as_view()),
    path('telemetry/', TelemetryListView.as_view()),
    path('thresholds/', ThresholdListView.as_view()),
    path('thresholds/<str:key>/', ThresholdDetailView.as_view()),
    path('audit/', AuditListView.as_view()),
    path('report-exports/', ReportExportView.as_view()),
]
