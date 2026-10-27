import time
import json
import logging
from django.core.management.base import BaseCommand
from django.db import close_old_connections,OperationalError
from operations.sprint_demo import initialize,tick


class Command(BaseCommand):
    help='Dedicated .agent-demo sampler. No model calls, MQTT or real devices.'
    def add_arguments(self,p):
        p.add_argument('--initialize',action='store_true'); p.add_argument('--without-model',action='store_true')
        p.add_argument('--once',action='store_true')
        p.add_argument('--duration-seconds',type=int,default=0)
    def handle(self,*args,**o):
        if o['initialize']: initialize(not o['without_model'])
        logging.getLogger('operations.request').setLevel(logging.WARNING)
        started=time.monotonic(); ticks=0; lock_retries=0
        while True:
            close_old_connections()
            try: ticks+=int(tick())
            except OperationalError as exc:
                if 'locked' not in str(exc).lower(): raise
                # tick is atomic: retry next cycle without fabricating samples or timestamps.
                lock_retries+=1
                self.stderr.write(json.dumps({'event':'sqlite_lock_retry','count':lock_retries}))
            if o['once']: return
            if o['duration_seconds'] and time.monotonic()-started>=o['duration_seconds']:
                self.stdout.write(json.dumps({'durationSeconds':round(time.monotonic()-started,2),'ticks':ticks,'lockRetries':lock_retries,'source':'SIMULATED_TEST'})); return
            time.sleep(2)
