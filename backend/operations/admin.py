from django.contrib import admin
from .models import Alert, Asset, AuditLog, Profile, RegistrationRequest, ReportExport, Telemetry, Threshold, WorkOrder

for model in [Profile, RegistrationRequest, Asset, Alert, WorkOrder, Telemetry, Threshold, AuditLog, ReportExport]:
    admin.site.register(model)
