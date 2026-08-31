from django.contrib.auth.models import User
from django.core.cache import cache
from django.db import transaction

from .models import Alert, Asset, AuditLog, RegistrationRequest, SpatialFeature, TwinModelRelease, WorkOrder


def release_test_data_summary():
    """Return counts for namespaces reserved exclusively for automated tests."""
    return {
        'registrationRequests': RegistrationRequest.objects.filter(account__startswith='e2e-operator-').count(),
        'users': User.objects.filter(email__startswith='e2e-operator-').count(),
        'spatialFeatures': SpatialFeature.objects.filter(code__startswith='SEG-E2E-').count(),
        'assets': Asset.objects.filter(code__startswith='ENV-E2E').count(),
        'modelReleases': TwinModelRelease.objects.filter(version__startswith='e2e-model-').count(),
        'workOrders': WorkOrder.objects.filter(source_alert__code='ALM-260826-001').count(),
    }


def clean_release_test_data():
    """Delete deterministic browser-test data and restore its shared fixtures."""
    cache.delete('throttle_login_127.0.0.1')
    cache.delete('throttle_login_burst_127.0.0.1')
    model_files = []
    with transaction.atomic():
        test_order_ids = list(WorkOrder.objects.filter(source_alert__code='ALM-260826-001').values_list('id', flat=True))
        test_asset_ids = list(Asset.objects.filter(code__startswith='ENV-E2E').values_list('id', flat=True))
        test_feature_ids = list(SpatialFeature.objects.filter(code__startswith='SEG-E2E-').values_list('id', flat=True))
        test_release_ids = list(TwinModelRelease.objects.filter(version__startswith='e2e-model-').values_list('id', flat=True))
        AuditLog.objects.filter(resource_type='work_order', resource_id__in=[str(item) for item in test_order_ids]).delete()
        AuditLog.objects.filter(resource_type='asset', resource_id__in=[str(item) for item in test_asset_ids]).delete()
        AuditLog.objects.filter(resource_type='spatial_feature', resource_id__in=[str(item) for item in test_feature_ids]).delete()
        AuditLog.objects.filter(resource_type='twin_model_release', resource_id__in=[str(item) for item in test_release_ids]).delete()
        RegistrationRequest.objects.filter(account__startswith='e2e-operator-').delete()
        User.objects.filter(email__startswith='e2e-operator-').delete()
        SpatialFeature.objects.filter(code__startswith='SEG-E2E-').delete()
        for release in TwinModelRelease.objects.filter(pk__in=test_release_ids):
            if release.model_file:
                model_files.append(release.model_file)
            release.delete()
        Asset.objects.filter(code__startswith='ENV-E2E').delete()
        WorkOrder.objects.filter(pk__in=test_order_ids).delete()
        shared_alert = Alert.objects.filter(code='ALM-260826-001').first()
        if shared_alert:
            AuditLog.objects.filter(action='alert.acknowledged', resource_type='alert', resource_id=str(shared_alert.pk)).delete()
            shared_alert.status = Alert.Status.OPEN
            shared_alert.acknowledged_at = None
            shared_alert.acknowledged_by = None
            shared_alert.save(update_fields=['status', 'acknowledged_at', 'acknowledged_by'])
        if not TwinModelRelease.objects.filter(status=TwinModelRelease.Status.ACTIVE).exists():
            fallback = TwinModelRelease.objects.exclude(version__startswith='e2e-model-').filter(is_compatible=True).order_by('-activated_at', '-created_at').first()
            if fallback:
                fallback.status = TwinModelRelease.Status.ACTIVE
                fallback.save(update_fields=['status'])
    # File storage is external to the database transaction. Delete only after
    # database cleanup commits so a rollback can never leave a dangling row.
    for model_file in model_files:
        model_file.delete(save=False)
    return release_test_data_summary()
