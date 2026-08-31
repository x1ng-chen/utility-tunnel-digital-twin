from django.conf import settings
from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.db import transaction

from operations.models import Profile


class Command(BaseCommand):
    help = 'Create or repair the passwordless machine principal used for telemetry ingestion.'

    @transaction.atomic
    def handle(self, *args, **options):
        username = settings.INGEST_PRINCIPAL_USERNAME
        user, created = User.objects.get_or_create(
            username=username,
            defaults={'email': '', 'is_active': True},
        )
        user.is_active = True
        user.is_staff = False
        user.is_superuser = False
        user.set_unusable_password()
        user.save(update_fields=['is_active', 'is_staff', 'is_superuser', 'password'])
        Profile.objects.update_or_create(
            user=user,
            defaults={'display_name': 'IoTDA telemetry ingest', 'role': Profile.Role.INGEST},
        )
        verb = 'created' if created else 'updated'
        self.stdout.write(self.style.SUCCESS(f'Ingest principal {username} {verb}; password login is disabled.'))
