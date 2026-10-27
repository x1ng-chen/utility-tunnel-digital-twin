"""Natural wall-clock expiry check against the independent sampler, without model calls."""
import json
import time
from django.core.management.base import BaseCommand,CommandError
from django.db import close_old_connections
from operations.sprint_demo import guard,control,session_state
from operations.agent_operations import station_snapshot
from operations.sprint_agents import clean


class Command(BaseCommand):
    def add_arguments(self,p): p.add_argument('--pause-seconds',type=int,default=190)
    def handle(self,*a,**o):
        if not 185<=o['pause_seconds']<=300: raise CommandError('Pause must exceed the 180-second heartbeat expiry.')
        root=guard();soak=root/'concurrent-soak.json'
        if soak.exists() and not json.loads(soak.read_text(encoding='utf-8'))['complete']:
            raise CommandError('Complete the concurrent soak before pausing it.')
        before=session_state();control('pause');paused=session_state();start=time.monotonic()
        try:
            while time.monotonic()-start<o['pause_seconds']: time.sleep(max(.001,min(30,o['pause_seconds']-(time.monotonic()-start))))
            close_old_connections();expired=station_snapshot('all');unchanged=session_state()
            if unchanged['tick']!=paused['tick'] or unchanged['lastTickAt']!=paused['lastTickAt']:
                raise CommandError('Paused sampler unexpectedly changed timestamps.')
            if expired['scenario_usable_sensor_count']!=0: raise CommandError('Old observations incorrectly remained usable.')
            control('start');deadline=time.monotonic()+12
            while time.monotonic()<deadline:
                close_old_connections()
                if session_state()['tick']>paused['tick']: break
                time.sleep(.5)
            recovered=station_snapshot('all');after=session_state()
            if recovered['scenario_usable_sensor_count']!=31 or after['lastTickAt']==paused['lastTickAt']:
                raise CommandError('New observations did not recover all 31 modules.')
            result=clean({'status':'passed','pauseSeconds':round(time.monotonic()-start,2),
                'source':'SIMULATED_TEST','modelCalls':0,'before':before,'paused':paused,'after':after,
                'expiredScenarioUsable':expired['scenario_usable_sensor_count'],
                'recoveredScenarioUsable':recovered['scenario_usable_sensor_count'],'oldTimestampsUnmodified':True})
            (root/'natural-expiry.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
            self.stdout.write('Natural expiry and new observation recovery passed.')
        finally:
            control('start' if before['running'] else 'pause')
