import time
from django.core.management.base import BaseCommand
from django.db import close_old_connections
from operations.sprint_agents import process_one
from operations.sprint_views import expire_runs


class Command(BaseCommand):
    help='Run persisted Agent jobs. Paid calls only occur for explicitly submitted jobs.'
    def add_arguments(self,p):
        p.add_argument('--once',action='store_true')
        p.add_argument('--warm-knowledge',action='store_true')
    def handle(self,*args,**options):
        if options['warm_knowledge']:
            from operations.sprint_knowledge import search
            result=search('通风运行状态')
            self.stdout.write('Knowledge: '+result['mode'])
        while True:
            close_old_connections(); expire_runs()
            worked=process_one()
            if options['once']: return
            if not worked: time.sleep(.5)
