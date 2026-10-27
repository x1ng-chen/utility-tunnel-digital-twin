"""Explicit paid switch; paired arms share the exact immutable evidence packet."""
import json
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4
from django.conf import settings
from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError
from dotenv import dotenv_values
from rest_framework.test import APIClient
from operations.agent_context import require_evaluation_database
from operations.agent_evaluation import entries,prepare_regression
from operations.agent_scenarios import seed_scenario
from operations.agent_runbooks import RUNBOOKS
from operations.sprint_agents import freeze,process_one,clean
from operations.sprint_models import AgentRun
from operations.sprint_knowledge import version,search
from operations.models import WorkOrder
from operations.sprint_views import serialize


class Command(BaseCommand):
    help='Three/single Agent evaluation; default only lists cases. --live incurs provider charges.'
    def add_arguments(self,p):
        p.add_argument('--suite',choices=['smoke','composite','regression'],default='smoke')
        p.add_argument('--mode',choices=['multi','single','paired'],default='multi')
        p.add_argument('--case',action='append',dest='cases')
        p.add_argument('--live',action='store_true'); p.add_argument('--key-env-file')
        p.add_argument('--confirm-test-proposals',action='store_true')
    def handle(self,*args,**o):
        root=require_evaluation_database()
        if root.name!='.agent-eval-sprint': raise CommandError('Use config.sprint_eval_settings; do not reset existing evaluation records.')
        selected=[e for e in entries(o['suite']) if not o['cases'] or e['id'] in o['cases']]
        if not selected: raise CommandError('No matching cases.')
        if not o['live']:
            self.stdout.write(json.dumps({'paidCalls':False,'cases':[e['id'] for e in selected]},ensure_ascii=False)); return
        if o['key_env_file']:
            # Read only the authorized model key, never echo or copy other secrets.
            settings.DEEPSEEK_API_KEY=dotenv_values(o['key_env_file']).get('DEEPSEEK_API_KEY','').strip()
        if not settings.DEEPSEEK_API_KEY: raise CommandError('DeepSeek key unavailable; no model called.')
        stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
        fingerprint=hashlib.sha256(b''.join(p.read_bytes() for p in sorted((settings.BASE_DIR/'operations').rglob('*.py')))).hexdigest()
        destination=root/'runs'/f'{stamp}-{o["suite"]}-{o["mode"]}.jsonl'
        destination.parent.mkdir(exist_ok=True)
        for entry in selected:
            seed_scenario(entry['scenario'],reset=True)
            prepare_regression(entry['id'])
            kind='inspection' if entry['id'].startswith('INS-') else 'draft' if entry['id'].startswith('W0') or entry['id'] in {'ORD-01','ORD-02','ORD-03'} else 'review' if entry['id']=='ORD-04' else 'diagnosis'
            payload={'kind':kind,'station_id':'all' if kind=='inspection' else 'P5','prompt':entry['prompt']}
            if kind=='draft': payload['asset_code']='MQ4-05'
            if kind=='review': payload['work_order_code']='WO-SIM-001'
            frozen=freeze(payload)
            packet={'question':entry['prompt'],'snapshot':frozen,'runbooks':RUNBOOKS,
                'knowledge':search(entry['prompt']), 'source':'SIMULATED_TEST',
                'manualGroup':'NOT_RUN','humanScoring':'PENDING','expectedOutcomesIncluded':False,
                'evaluationProtocolVersion':'2026-10-27-v2-full-frozen-knowledge',
                'budget':{'deadlineSeconds':120,'modelCalls':12,'toolCalls':12}}
            packet_path=destination.parent/f'{stamp}-{entry["id"]}-packet.json'
            packet_path.write_text(json.dumps(clean(packet),ensure_ascii=False,indent=2),encoding='utf-8')
            for mode in (['single','multi'] if o['mode']=='paired' else [o['mode']]):
                user=User.objects.get(username=f'agent-eval-{entry["role"]}')
                client=APIClient(HTTP_HOST='127.0.0.1');client.force_authenticate(user)
                before=WorkOrder.objects.count()
                response=client.post('/api/assistant/runs/',{**payload,'mode':mode},format='json',HTTP_IDEMPOTENCY_KEY=str(uuid4()))
                original_order_ids=set(WorkOrder.objects.values_list('pk',flat=True))
                record={'caseId':entry['id'],'mode':mode,'packet':packet_path.name,'knowledgeVersion':version(),'codeFingerprint':fingerprint,
                    'evaluationProtocolVersion':packet['evaluationProtocolVersion'],'budget':packet['budget'],
                    'source':'SIMULATED_TEST','createHttpStatus':response.status_code,'humanScoring':'PENDING',
                    'naturalLanguageFullyVerified':False}
                if response.status_code==202:
                    run=AgentRun.objects.get(pk=response.data['id']);run.snapshot=frozen;run.save(update_fields=['snapshot'])
                    if entry['id']=='S05':
                        from unittest.mock import patch
                        with patch('operations.ai_assistant._completion',side_effect=TimeoutError('CONTROLLED_TIMEOUT_NOT_PROVIDER_FAILURE')): process_one()
                        record['controlledFaultInjection']=True
                    else: process_one()
                    run.refresh_from_db();record['run']=serialize(run)
                    record['noUnconfirmedWorkOrder']=WorkOrder.objects.count()==before
                    if o['confirm_test_proposals'] and entry['id'] in {'ORD-01','W04'} and run.result.get('proposals'):
                        proposal=run.result['proposals'][0]
                        p={k:proposal[k] for k in ('assetCode','title','description','priority')}
                        key='sprint-confirm-'+str(run.pk)
                        first=client.post('/api/work-orders/',p,format='json',HTTP_IDEMPOTENCY_KEY=key)
                        again=client.post('/api/work-orders/',p,format='json',HTTP_IDEMPOTENCY_KEY=key)
                        record['programConfirmation']={'notHuman':True,'first':first.status_code,'retry':again.status_code,
                            'code':first.data.get('code'),'unique':first.data.get('code')==again.data.get('code') and WorkOrder.objects.count()==before+1}
                    record['status']=run.status
                    if o['mode']=='paired':
                        # Remove only program-confirmed test orders before the next arm.
                        new_orders=WorkOrder.objects.exclude(pk__in=original_order_ids)
                        record['betweenArmReset']={'testOrdersRemoved':new_orders.count(),'snapshotHash':frozen['sha256']}
                        new_orders.delete()
                else:
                    record['status']='SERVER_PERMISSION_REJECTED' if response.status_code==403 else 'CREATE_FAILED'
                    record['response']=response.data
                with destination.open('a',encoding='utf-8') as f: f.write(json.dumps(clean(record),ensure_ascii=False)+'\n')
                self.stdout.write(json.dumps({'case':entry['id'],'mode':mode,'status':record['status'],
                    'error':record.get('run',{}).get('error'),'modelCalls':record.get('run',{}).get('runtime',{}).get('modelCalls')},ensure_ascii=False))
                calls=record.get('run',{}).get('runtime',{}).get('calls',[])
                if any(c.get('providerHttpStatus') in {401,402,403} for c in calls):
                    raise CommandError('Provider account/authentication unavailable; batch stopped, remaining arms NOT_RUN. Recorded responses retained: '+str(destination))
        self.stdout.write(str(destination))
