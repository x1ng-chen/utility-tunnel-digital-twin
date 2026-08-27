from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from django.db.migrations.executor import MigrationExecutor


class Command(BaseCommand):
    help = 'Validate production security settings, database connectivity, and migration state.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--allow-non-production',
            action='store_true',
            help='Run database and migration probes outside production without enforcing production-only settings.',
        )
        parser.add_argument(
            '--skip-migrations',
            action='store_true',
            help='Skip the applied-migration probe in non-production environments only.',
        )

    def handle(self, *args, **options):
        production = settings.IS_PRODUCTION
        if not production and not options['allow_non_production']:
            raise CommandError('DJANGO_ENV must be production. Use --allow-non-production only for CI or local verification.')

        if production:
            failures = []
            if settings.DEBUG:
                failures.append('DEBUG must be false')
            if settings.SECURE_SSL_REDIRECT is not True:
                failures.append('SECURE_SSL_REDIRECT must be enabled')
            if settings.SECURE_HSTS_SECONDS <= 0:
                failures.append('SECURE_HSTS_SECONDS must be greater than zero')
            if settings.SECURE_PROXY_SSL_HEADER != ('HTTP_X_FORWARDED_PROTO', 'https'):
                failures.append('SECURE_PROXY_SSL_HEADER must trust X-Forwarded-Proto behind the TLS reverse proxy')
            database = settings.DATABASES['default']
            if database['ENGINE'] != 'django.db.backends.postgresql':
                failures.append('DATABASES.default must use PostgreSQL')
            sslmode = database.get('OPTIONS', {}).get('sslmode', '')
            if sslmode not in {'require', 'verify-ca', 'verify-full'}:
                failures.append('PostgreSQL sslmode must require TLS')
            if settings.CACHE_BACKEND.endswith('LocMemCache'):
                failures.append('a shared cache backend is required')
            if any(not origin.lower().startswith('https://') for origin in settings.CORS_ALLOWED_ORIGINS):
                failures.append('CORS_ALLOWED_ORIGINS must contain HTTPS origins only')
            if any(not origin.lower().startswith('https://') for origin in settings.CSRF_TRUSTED_ORIGINS):
                failures.append('DJANGO_CSRF_TRUSTED_ORIGINS must contain HTTPS origins only')
            if failures:
                raise CommandError('Production preflight failed: ' + '; '.join(failures))

        skip_migrations = options['skip_migrations'] and not production
        try:
            with connection.cursor() as cursor:
                cursor.execute('SELECT 1')
                cursor.fetchone()
            plan = []
            if not skip_migrations:
                executor = MigrationExecutor(connection)
                plan = executor.migration_plan(executor.loader.graph.leaf_nodes())
        except Exception as exc:
            raise CommandError(f'Database preflight failed: {exc}') from exc
        if plan:
            pending = ', '.join(f'{migration.app_label}.{migration.name}' for migration, _ in plan[:8])
            suffix = ' ...' if len(plan) > 8 else ''
            raise CommandError(f'Pending migrations must be applied before traffic: {pending}{suffix}')

        migration_message = 'migration state probe skipped by explicit non-production flag' if skip_migrations else 'migrations are ready'
        self.stdout.write(self.style.SUCCESS(f'Production preflight passed: security settings, database connectivity, and {migration_message}.'))
