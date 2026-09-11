"""Verify least-privilege database grants used by model publication.

This command is intentionally limited to the disposable CI/test database.  It
executes the public API as the application runtime database identity, rather
than merely inspecting SQL text, so an omitted model metadata column cannot
silently break a production upload or activation after release.
"""

import json
import struct
import tempfile
import uuid

from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.test import override_settings
from rest_framework.test import APIClient

from operations.models import Asset


def compatible_glb(asset_meshes: list[str]) -> SimpleUploadedFile:
    """Build the smallest valid GLB carrying every active asset mesh name."""
    scene = json.dumps({
        'asset': {'version': '2.0'},
        'nodes': [{'name': mesh} for mesh in asset_meshes],
    }, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
    scene += b' ' * (-len(scene) % 4)
    chunk = struct.pack('<I4s', len(scene), b'JSON') + scene
    content = struct.pack('<4sII', b'glTF', 2, 12 + len(chunk)) + chunk
    return SimpleUploadedFile('runtime-policy.glb', content, content_type='model/gltf-binary')


class Command(BaseCommand):
    help = 'CI-only runtime-role verification for model upload, activation and download permissions.'

    def handle(self, *args, **options):
        if settings.DJANGO_ENV != 'test':
            raise CommandError('verify_runtime_model_permissions is restricted to DJANGO_ENV=test.')

        meshes = list(
            Asset.objects.filter(is_active=True)
            .exclude(mesh='')
            .exclude(mesh__isnull=True)
            .order_by('code')
            .values_list('mesh', flat=True)
        )
        if not meshes:
            raise CommandError('The test seed has no active model mesh mappings.')

        client = APIClient()
        login = client.post(
            '/api/auth/login/',
            {'email': 'admin', 'password': '123'},
            format='json',
            HTTP_HOST='localhost',
        )
        if login.status_code != 200:
            raise CommandError(f'Runtime-role administrator login failed: {login.status_code} {login.content!r}')
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.json()['accessToken']}")

        # Verify the actual runtime identity without leaving a dangling CI
        # release or mutating the active model once the permission probe ends.
        # Database rollback requires no DELETE privilege, so it also preserves
        # the least-privilege assertion this command is designed to exercise.
        with transaction.atomic(), tempfile.TemporaryDirectory(prefix='ut-runtime-model-') as media_root, override_settings(MEDIA_ROOT=media_root):
            version = f'ci-runtime-{uuid.uuid4().hex[:12]}'
            created = client.post(
                '/api/twin/models/',
                {'version': version, 'notes': 'CI least-privilege publication verification', 'file': compatible_glb(meshes)},
                format='multipart',
                HTTP_HOST='localhost',
            )
            if created.status_code != 201:
                raise CommandError(f'Runtime-role model upload failed: {created.status_code} {created.content!r}')
            release = created.json()
            if not release.get('isCompatible') or release.get('missingAssetCodes'):
                raise CommandError(f'CI model fixture unexpectedly failed its mapping contract: {release!r}')

            activated = client.post(
                f"/api/twin/models/{release['id']}/activate/",
                format='json',
                HTTP_HOST='localhost',
            )
            if activated.status_code != 200 or activated.json().get('status') != 'active':
                raise CommandError(f'Runtime-role model activation failed: {activated.status_code} {activated.content!r}')

            model_file = client.get('/api/twin/model-file/', HTTP_HOST='localhost')
            if model_file.status_code != 200 or b''.join(model_file.streaming_content)[:4] != b'glTF':
                raise CommandError(f'Runtime-role model download failed: {model_file.status_code}')
            transaction.set_rollback(True)

        self.stdout.write(self.style.SUCCESS('Runtime-role model publication permissions verified.'))
