"""Explicit paid simulation smoke. Program confirmation is never called human approval."""
import json
from uuid import uuid4
from django.conf import settings
from django.contrib.auth.models import User
from django.core.management.base import BaseCommand,CommandError
from django.utils import timezone
from dotenv import dotenv_values
from rest_framework.test import APIClient
from operations.sprint_demo import guard
from operations.sprint_agents import Workflow,clean
from operations.sprint_models import AgentRun
from operations.sprint_views import serialize


class Command(BaseCommand):
    def add_arguments(self,p):
        p.add_argument('--live',action='store_true');p.add_argument('--key-env-file')
    def handle(self,*a,**o):
        root=guard()
        if not o['live']: self.stdout.write('No model or simulation action; explicit --live required.');return
        if o['key_env_file']: settings.DEEPSEEK_API_KEY=dotenv_values(o['key_env_file']).get('DEEPSEEK_API_KEY','').strip()
        if not settings.DEEPSEEK_API_KEY: raise CommandError('Missing key.')
        user=User.objects.get(username='agent-eval-operator')
        run=AgentRun.objects.create(owner=user,request_key=str(uuid4()),status='running',started_at=timezone.now(),
            input={'kind':'diagnosis','mode':'multi','station_id':'P5','control_request':{'asset_code':'FAN-01','intent':'pwm','value':60},
                'prompt':'这是明确的测试请求：核查冻结的双风机反馈、控制记录和适用手册，为FAN-01提出PWM=60的仿真动作建议并调用建议工具。不得执行，不创建工单。保持未知及反证，交独立复核。'})
        workflow=Workflow(run)
        try:
            result=workflow.perform();workflow.check()
            run.refresh_from_db();run.result=result;run.status='completed';run.finished_at=timezone.now();run.save()
        except Exception as exc:
            workflow.save();run.refresh_from_db();run.status='failed';run.error=str(exc);run.finished_at=timezone.now();run.save()
        record={'source':'SIMULATED_TEST','programConfirmationNotHuman':True,'run':serialize(run)}
        client=APIClient(HTTP_HOST='127.0.0.1');client.force_authenticate(user)
        if run.result.get('controlProposals'):
            proposal=client.post('/api/assistant/demo/commands/',{'runId':str(run.pk),'proposalIndex':0},format='json')
            record['proposalHttp']=proposal.status_code;record['proposal']=proposal.data
            if proposal.status_code==200:
                url='/api/assistant/demo/commands/'+proposal.data['actionId']+'/'
                first=client.post(url,{'action':'confirm'},format='json');again=client.post(url,{'action':'confirm'},format='json')
                record['confirmation']={'http':first.status_code,'response':first.data,'replay':again.data}
        path=root/('live-control-'+str(run.pk)+'.json')
        path.write_text(json.dumps(clean(record),ensure_ascii=False,indent=2),encoding='utf-8')
        self.stdout.write(str(path))
