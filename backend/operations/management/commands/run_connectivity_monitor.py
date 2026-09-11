"""Poll the API-owned heartbeat reconciliation endpoint for production use."""

from time import sleep
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = 'Ask the API process to reconcile connectivity, preserving its realtime fan-out ownership.'

    def add_arguments(self, parser):
        parser.add_argument('--once', action='store_true', help='Execute one protected reconciliation request and exit.')

    def _run_once(self):
        if not settings.CONNECTIVITY_MONITOR_TOKEN:
            raise CommandError('CONNECTIVITY_MONITOR_TOKEN is required for the connectivity monitor.')
        request = Request(
            settings.CONNECTIVITY_MONITOR_URL,
            method='POST',
            headers={
                'X-Connectivity-Monitor-Token': settings.CONNECTIVITY_MONITOR_TOKEN,
                # The monitor calls Daphne directly on the Docker-only
                # network. Production enables SECURE_SSL_REDIRECT, so this
                # trusted internal hop must state the public scheme explicitly
                # instead of following an impossible TLS redirect to :8000.
                'X-Forwarded-Proto': 'https',
                'Content-Length': '0',
            },
        )
        try:
            with urlopen(request, timeout=10) as response:
                if response.status != 200:
                    raise CommandError(f'Connectivity reconcile returned HTTP {response.status}.')
                return response.read().decode('utf-8')
        except HTTPError as exc:
            raise CommandError(f'Connectivity reconcile returned HTTP {exc.code}.') from exc
        except URLError as exc:
            raise CommandError(f'Connectivity reconcile request failed: {exc.reason}.') from exc

    def handle(self, *args, **options):
        while True:
            try:
                result = self._run_once()
                self.stdout.write(result)
            except CommandError as exc:
                # A transient API restart must not terminate the container.  A
                # configuration error remains visible in its logs and is also
                # rejected during production settings load when applicable.
                self.stderr.write(str(exc))
                if options['once']:
                    # Deployment diagnostics need a non-zero status if the
                    # API-owned reconciliation endpoint cannot be reached.
                    # The long-running container keeps retrying instead.
                    raise
            if options['once']:
                return
            sleep(settings.CONNECTIVITY_RECONCILE_INTERVAL_SECONDS)
