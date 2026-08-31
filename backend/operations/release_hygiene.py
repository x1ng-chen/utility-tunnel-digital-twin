from django.contrib.auth.models import User
from django.core.cache import cache

from .models import Asset, RegistrationRequest, SpatialFeature, TwinModelRelease, WorkOrder


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
    """Delete only deterministic browser-test namespaces and their files."""
    cache.delete('throttle_login_127.0.0.1')
    cache.delete('throttle_login_burst_127.0.0.1')
    RegistrationRequest.objects.filter(account__startswith='e2e-operator-').delete()
    User.objects.filter(email__startswith='e2e-operator-').delete()
    SpatialFeature.objects.filter(code__startswith='SEG-E2E-').delete()
    for release in TwinModelRelease.objects.filter(version__startswith='e2e-model-'):
        release.model_file.delete(save=False)
        release.delete()
    Asset.objects.filter(code__startswith='ENV-E2E').delete()
    WorkOrder.objects.filter(source_alert__code='ALM-260826-001').delete()
    return release_test_data_summary()
