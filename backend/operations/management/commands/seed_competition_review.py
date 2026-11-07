"""Load the released, anonymized P5 replay into the competition database."""
import json
import os
from pathlib import Path

from django.conf import settings
from django.contrib.auth.models import User
from django.core.files import File
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from operations.models import Alert, Asset, Profile, Telemetry, TwinModelRelease, WorkOrder, WorkOrderEvent
from operations.twin_presentation import V24_UNIFIED
from operations.views import validate_glb_upload


class Command(BaseCommand):
    help = "Load the fixed P5 competition replay and provision its viewer."

    def add_arguments(self, parser):
        parser.add_argument("evidence", type=Path)
        parser.add_argument("model", type=Path)

    def handle(self, evidence, model, **options):
        if not getattr(settings, "COMPETITION_REVIEW_MODE", False):
            raise CommandError("Competition review settings are required.")
        password = os.environ.get("COMPETITION_REVIEW_PASSWORD", "")
        if len(password) < 16:
            raise CommandError("Set a private review password of at least 16 characters.")
        data = json.loads(evidence.read_text(encoding="utf-8"))
        if data["alert"]["code"] != "ALM-AUTO-261106-D353FC" or len(data["observations"]) != 38:
            raise CommandError("Expected the released evidence for P5 alert 1234.")
        with model.open("rb") as stream:
            model_file = File(stream, name="utility-tunnel-v24-unified.glb")
            digest, metadata, error = validate_glb_upload(model_file)
            if error is not None or digest != V24_UNIFIED["modelSha256"]:
                raise CommandError("Expected the exact V24 unified GLB.")
            self.seed(data, model_file, digest, metadata, password)
        self.stdout.write("P5 replay ready: 38 historical observations and one completed order.")

    @transaction.atomic
    def seed(self, data, model_file, digest, metadata, password):
        actor, _ = User.objects.get_or_create(username="historical-operator", defaults={"is_active": False})
        if actor.is_active or actor.is_staff or actor.is_superuser:
            raise CommandError("Historical actor must be inactive and unprivileged.")
        viewer, _ = User.objects.get_or_create(username="reviewer")
        if viewer.is_staff or viewer.is_superuser:
            raise CommandError("Reviewer must be unprivileged.")
        viewer.is_active = True
        viewer.email = "reviewer@example.invalid"
        if not viewer.check_password(password):
            viewer.set_password(password)
        viewer.save(update_fields=["is_active", "email", "password"])
        Profile.objects.update_or_create(user=viewer, defaults={"display_name": "评审查看者", "role": Profile.Role.VIEWER})

        mesh = V24_UNIFIED["sensorMeshes"]["FLAME-05"]
        if mesh not in metadata["nodeNames"] or mesh in metadata["duplicateNodeNames"]:
            raise CommandError("The review model must uniquely locate FLAME-05.")
        asset, _ = Asset.objects.update_or_create(code="FLAME-05", defaults={
            "name": "FLAME-05 · P5", "zone": "P5", "asset_type": "sensor",
            "mesh": mesh, "status": Asset.Status.UNKNOWN,
        })
        TwinModelRelease.objects.filter(status=TwinModelRelease.Status.ACTIVE).exclude(sha256=digest).update(
            status=TwinModelRelease.Status.RETIRED)
        release = TwinModelRelease.objects.filter(sha256=digest).first()
        if release is None:
            release = TwinModelRelease(
                version="review-v24-unified", sha256=digest, size_bytes=model_file.size,
                original_name=model_file.name, uploaded_by=actor, activated_by=actor,
                node_count=metadata["nodeCount"], mesh_count=metadata["meshCount"],
                named_node_count=metadata["namedNodeCount"], node_names=sorted(metadata["nodeNames"]),
                duplicate_node_names=metadata["duplicateNodeNames"], node_inventory_available=True,
                is_compatible=True, notes="比赛评审 · P5 历史实测回放",
            )
            release.model_file.save(model_file.name, model_file, save=False)
        release.status = TwinModelRelease.Status.ACTIVE
        release.activated_at = release.activated_at or timezone.now()
        release.save()

        alert_data = data["alert"].copy()
        code = alert_data.pop("code")
        alert, _ = Alert.objects.update_or_create(code=code, defaults={"asset": asset, **alert_data})
        for sample in data["observations"]:
            fields = sample.copy()
            event_id = fields.pop("event_id")
            Telemetry.objects.update_or_create(event_id=event_id, defaults={"asset": asset, **fields})

        order_data = data["order"].copy()
        code = order_data.pop("code")
        created_at = order_data.pop("created_at")
        updated_at = order_data.pop("updated_at")
        order, _ = WorkOrder.objects.update_or_create(code=code, defaults={
            "asset": asset, "source_alert": alert, "created_by": actor, "reviewed_by": actor, **order_data,
        })
        WorkOrder.objects.filter(pk=order.pk).update(created_at=created_at, updated_at=updated_at)
        for record in data["events"]:
            fields = record.copy()
            occurred = fields.pop("created_at")
            event, _ = WorkOrderEvent.objects.get_or_create(
                work_order=order, event_type=fields.pop("event_type"), to_status=fields.pop("to_status"),
                defaults={"actor": actor, **fields},
            )
            WorkOrderEvent.objects.filter(pk=event.pk).update(created_at=occurred)
