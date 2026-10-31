"""Paired software-mechanics matrix; generation is always a marked stub."""
import copy
import json
from pathlib import Path
import uuid
from unittest.mock import patch
from django.conf import settings
from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError
from django.test import override_settings
from rest_framework.test import APIClient
from operations.agent_context import require_evaluation_database
from operations.agent_evaluation import entries
from operations.agent_scenarios import seed_scenario
from operations.sprint_agents import freeze, process_one
from operations.sprint_models import AgentRun
from operations.sprint_views import serialize

KINDS={**{f'INS-{i:02}':'inspection' for i in range(1,5)},
    **{f'DIA-{i:02}':'diagnosis' for i in range(1,5)},
    'ORD-01':'draft','ORD-02':'draft','ORD-03':'draft','ORD-04':'review'}


def generative_stub(messages,deadline,final_round,**kwargs):
    """Test-only workflow driver; not an actual diagnostic model or answer key."""
    role=messages[0]['content'].split('你当前独立角色是')[1].split('。')[0]
    context=json.loads(messages[1]['content']);task=context['task'];kind=task['kind']
    products=[json.loads(m['content']) for m in messages if m['role']=='tool']
    seen={p['tool'] for p in products};target=task.get('asset_code','MQ4-05')
    todo=[]
    if role in {'evidence','single'}:
        todo=([('station_snapshot',{'station_id':'all'})] if kind=='inspection' else
            [('asset_snapshot',{'asset_code':target}),('active_work_orders',{'asset_code':target})] if kind=='draft' else
            [('review_work_order',{'work_order_code':task['work_order_code']})] if kind=='review' else
            [('collect_station_evidence',{})])
    elif role=='diagnosis':
        todo=[('knowledge_search',{'query':'风机采集质量与工单确认'})]
        if kind=='draft':
            todo.append(('draft_work_order',{'asset_code':target,'title':'模拟测试维护草案',
                'description':'仅用于编排验收，待人工核查和确认。','priority':'normal'}))
    elif role=='review':
        todo=[('collect_station_evidence',{})]
    for name,args in todo:
        if name not in seen and not final_round:
            return {'content':None,'tool_calls':[{'id':f'call-{role}-{len(products)}','type':'function',
                'function':{'name':name,'arguments':json.dumps(args)}}],
                '_provider':{'model':'EXPLICIT_GENERATIVE_STUB','usage':{'prompt_tokens':0,'completion_tokens':0,'total_tokens':0},'finishReason':'tool_calls'}}
    good=[p['id'] for p in products if p.get('status')=='ok']
    if not good: good=[p['id'] for p in context.get('routedEvidence',[]) if p.get('status')=='ok']
    output={'summary':'模拟生成式模型桩：只验证编排，不评价诊断正确率。','evidence_ids':good[:12],
        'missing':[],'request_evidence':'','candidates':[],'next_checks':[]}
    if role=='review': output.update(decision='pass',findings=[])
    return {'content':json.dumps(output,ensure_ascii=False),'_provider':{'model':'EXPLICIT_GENERATIVE_STUB',
        'usage':{'prompt_tokens':0,'completion_tokens':0,'total_tokens':0},'finishReason':'stop'}}


def decision_stub(state,options,timeout=5):
    return {'status':'selected','selectedOption':options[0]['id'],'attempted':True,'model':'EXPLICIT_DECISION_STUB',
        'modelRevision':'STUB_NOT_REAL_MODEL','probabilities':{},'usage':None,'runtime':{},'fallbackReason':None}


class Command(BaseCommand):
    help='A/B/C mechanics matrix. --local-model uses only AnyJev; DeepSeek is always stubbed.'

    def add_arguments(self,p):
        p.add_argument('--offline',action='store_true')
        p.add_argument('--local-model',action='store_true')
        p.add_argument('--reset',action='store_true',help='Reset only the dedicated .agent-capabilities sandbox.')
        p.add_argument('--runtime-root',default='D:/shixi/utility-tunnel-runtime/anyjev')

    def handle(self,*args,**o):
        selected=entries('composite')
        if not o['offline'] and not o['local_model']:
            self.stdout.write(json.dumps({'paidCalls':False,'cases':[s['id'] for s in selected],'arms':['baseline','active','routed']}));return
        if o['offline'] and o['local_model']: raise CommandError('Choose offline or local-model, not both.')
        root=require_evaluation_database()
        if root.name!='.agent-capabilities' or not o['reset']:
            raise CommandError('Use config.agent_capability_settings and explicit --reset; old acceptance databases are untouched.')
        token=''
        if o['local_model']:
            token=(Path(o['runtime_root'])/'service-token.txt').read_text(encoding='ascii').strip()
        destination=root/('matrix-local.json' if o['local_model'] else 'matrix-offline.json')
        records=[]
        for entry in selected:
            seed_scenario(entry['scenario'],reset=True,with_model=False)
            # DemoSession provides the scene generation expected by the frozen demo contract.
            from operations.sprint_models import DemoSession
            DemoSession.objects.get_or_create(pk=1,defaults={'case_id':entry['scenario']})
            user=User.objects.get(username='agent-eval-'+entry['role'])
            kind=KINDS[entry['id']]
            payload={'kind':kind,'station_id':'all' if kind=='inspection' else 'P5','mode':'multi','prompt':entry['prompt']}
            if kind=='draft': payload['asset_code']='MQ4-05'
            if kind=='review': payload['work_order_code']='WO-SIM-001'
            frozen=freeze(payload,user)
            for arm in ('baseline','active','routed'):
                client=APIClient(HTTP_HOST='127.0.0.1');client.force_authenticate(user)
                with override_settings(DEEPSEEK_API_KEY='EXPLICIT_GENERATIVE_STUB',
                        AGENT_ACTIVE_DIAGNOSIS_ENABLED=arm!='baseline',ANYJEV_ENABLED=arm=='routed',
                        ANYJEV_URL='http://127.0.0.1:8110',ANYJEV_TOKEN=token), \
                        patch('operations.ai_assistant._completion',side_effect=generative_stub):
                    response=client.post('/api/assistant/runs/',payload,format='json',HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()))
                    record={'caseId':entry['id'],'task':kind,'arm':arm,'httpStatus':response.status_code,
                        'snapshotHash':frozen['sha256'],'source':frozen['source'],'generativeModel':'EXPLICIT_GENERATIVE_STUB',
                        'decisionModel':'LOCAL_ANYJEV' if o['local_model'] and arm=='routed' else 'STUB_OR_DISABLED'}
                    record['snapshot']=copy.deepcopy(frozen)
                    if response.status_code==202:
                        run=AgentRun.objects.get(pk=response.data['id']);run.snapshot=copy.deepcopy(frozen);run.save(update_fields=['snapshot'])
                        if o['offline']:
                            with patch('operations.decision_router.route_decision',side_effect=decision_stub): process_one()
                        else: process_one()
                        run.refresh_from_db();record['run']=serialize(run)
                    else: record['response']=response.data
                    records.append(record)
                destination.write_text(json.dumps({'complete':False,'records':records},ensure_ascii=False,indent=2),encoding='utf-8')
        summary={'complete':True,'paidCalls':False,'generativeModel':'EXPLICIT_GENERATIVE_STUB',
            'decisionModel':'LOCAL_ANYJEV' if o['local_model'] else 'EXPLICIT_DECISION_STUB',
            'humanScoring':'NOT_RUN','fieldDiagnosisAccuracyProven':False,
            'boundary':'软件编排对照；生成式Agent为桩，不是三Agent真实模型收益或诊断准确率。',
            'arms':{arm:{'attempts':sum(r['arm']==arm for r in records),
                'finishedRuns':sum(r['arm']==arm and r.get('run',{}).get('status')=='completed' for r in records),
                'contractPassed':sum(r['arm']==arm and r.get('run',{}).get('result',{}).get('taskContract',{}).get('passed') is True for r in records),
                'permissionRefusals':sum(r['arm']==arm and r['httpStatus']==403 for r in records)} for arm in ('baseline','active','routed')},
            'records':records}
        destination.write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
        self.stdout.write(json.dumps({k:v for k,v in summary.items() if k!='records'},ensure_ascii=False))
