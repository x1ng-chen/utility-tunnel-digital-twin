import json
import time
from django.core.management.base import BaseCommand,CommandError
from django.db import close_old_connections
from operations.sprint_demo import guard,control,session_state
from operations.sprint_agents import clean


class Command(BaseCommand):
    help='Observe the independent sampler; this command does not generate telemetry or call models.'
    def add_arguments(self,p): p.add_argument('--duration-seconds',type=int,default=1800)
    def handle(self,*a,**o):
        if not 10<=o['duration_seconds']<=3600: raise CommandError('10..3600 seconds required.')
        root=guard();control('start');started=time.monotonic();checkpoints=[]
        path=root/'concurrent-soak.json'
        while True:
            close_old_connections();s=session_state();elapsed=time.monotonic()-started
            checkpoints.append(clean({'elapsedSeconds':round(elapsed,2),'session':s}))
            complete=elapsed>=o['duration_seconds']
            record={'source':'SIMULATED_TEST','durationSeconds':round(elapsed,2),'complete':complete,
                'independentSampler':True,'modelCallsByMonitor':0,'checkpoints':checkpoints,
                'observedTicks':s['tick']-checkpoints[0]['session']['tick']}
            path.write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
            if complete:
                self.stdout.write(str(path));return
            time.sleep(min(30,max(.1,o['duration_seconds']-elapsed)))
