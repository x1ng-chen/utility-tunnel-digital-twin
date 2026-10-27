import csv
import hashlib
import html
import io
import json
import re
from datetime import timedelta
from django.db import transaction, IntegrityError
from django.http import HttpResponse
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.conf import settings
from rest_framework.response import Response
from rest_framework.views import APIView
from .permissions import AuthenticatedRead
from .throttling import AiAssistantRateThrottle
from .sprint_models import AgentRun, SimulatedAction, DemoSession
from .sprint_agents import clean
from .sprint_knowledge import search
from .sprint_costs import calculate, example
from . import sprint_demo as demo
from .command_policy import build_command
from .agent_operations import INVENTORY


def role(user):
    return 'administrator' if user.is_superuser else getattr(getattr(user,'profile',None),'role','viewer')


def write(user): return role(user) in {'administrator','operator'}


def serialize(run):
    return clean({'id':str(run.pk),'status':run.status,'stage':run.stage,'input':run.input,
        'steps':run.steps,'result':run.result,'runtime':run.runtime,'error':run.error,
        'createdAt':run.created_at,'startedAt':run.started_at,'finishedAt':run.finished_at,
        'snapshotHash':run.snapshot.get('sha256'),'source':run.snapshot.get('source'),
        'actions':[{'id':str(a.pk),'assetCode':a.asset_code,'intent':a.intent,'value':a.value,
            'state':a.state,'expiresAt':a.expires_at,'events':a.events} for a in run.actions.all()]})


def expire_runs():
    now=timezone.now()
    for run in AgentRun.objects.filter(status='running',started_at__lt=now-timedelta(seconds=125)):
        partial={'partial':True,'taskOutcome':'incomplete','reply':'工作进程超过全局期限或已中断，任务未完成。',
            'evidence':[e for step in run.steps for e in step.get('traces',[])],
            'proposals':[],'controlProposals':[],'source':run.snapshot.get('source'),
            'snapshotHash':run.snapshot.get('sha256'),'naturalLanguageFullyVerified':False}
        if run.snapshot.get('guardRuleVersion'):
            from .agent_guardrails import derive
            partial['guardrails']=derive(run.snapshot,partial['evidence'])
            partial['guardrails']['violations']=[v for s in run.steps for v in s.get('guardViolations',[])]
            partial['experienceContext']=run.snapshot.get('experienceContext')
        AgentRun.objects.filter(pk=run.pk,status='running').update(status='failed',result=partial,
            error='工作进程超过全局期限或已中断。',finished_at=now)
    AgentRun.objects.filter(status='queued',created_at__lt=now-timedelta(minutes=5)).update(
        status='failed',error='排队超时，请检查工作进程。',finished_at=now)


class RunList(APIView):
    permission_classes=[AuthenticatedRead]
    throttle_classes=[AiAssistantRateThrottle]

    def get(self,request):
        expire_runs()
        return Response([serialize(r) for r in AgentRun.objects.filter(owner=request.user).order_by('-created_at')[:20]])

    def post(self,request):
        p=request.data
        if not isinstance(p,dict) or set(p)-{'kind','station_id','asset_code','work_order_code','prompt','mode','previous_run_id','control_request'}:
            return Response({'message':'无效任务字段。'},status=400)
        kind=p.get('kind','diagnosis')
        if not isinstance(kind,str) or kind not in {'inspection','diagnosis','draft','review'} or not isinstance(p.get('mode','multi'),str) or p.get('mode','multi') not in {'single','multi'}:
            return Response({'message':'无效任务类型。'},status=400)
        if not isinstance(p.get('station_id','P5'),str) or p.get('station_id','P5') not in {'all','P1','P2','P3','P4','P5'}:
            return Response({'message':'检测点不存在。'},status=400)
        if kind=='draft' and not write(request.user): return Response({'message':'只读角色不能生成草案。'},status=403)
        if 'control_request' in p:
            c=p['control_request']
            if not write(request.user): return Response(status=403)
            if p.get('mode','multi')!='multi': return Response({'message':'仿真动作需要三Agent独立复核。'},status=400)
            if kind!='diagnosis' or not isinstance(c,dict) or set(c)!={'asset_code','intent','value'}:
                return Response({'message':'仿真动作必须明确目标、类型和值。'},status=400)
            if c['asset_code'] not in ('FAN-01','FAN-02') or c['intent'] not in ('power','pwm') or type(c['value']) is not int or not 0<=c['value']<=(1 if c['intent']=='power' else 100):
                return Response({'message':'仿真动作参数无效。'},status=400)
        if kind=='draft' and not p.get('asset_code') or kind=='review' and not p.get('work_order_code'):
            return Response({'message':'明确任务缺少设备或工单目标。'},status=400)
        if not isinstance(p.get('prompt',''),str) or len(p.get('prompt',''))>2000:
            return Response({'message':'提示词最多2000字。'},status=400)
        for field in ('asset_code','work_order_code'):
            if field in p and (not isinstance(p[field],str) or not re.fullmatch(r'[A-Z0-9][A-Z0-9_-]{1,49}',p[field])):
                return Response({'message':'目标编码格式无效。'},status=400)
        previous=p.get('previous_run_id')
        if previous is not None and not isinstance(previous,str):
            return Response({'message':'先前任务编号无效。'},status=400)
        try:
            if previous and not AgentRun.objects.filter(pk=previous,owner=request.user,status='completed').exists():
                return Response({'message':'先前任务不可用。'},status=400)
        except ValidationError:
            return Response({'message':'先前任务编号无效。'},status=400)
        key=request.headers.get('Idempotency-Key','')
        if not re.fullmatch(r'[A-Za-z0-9._:-]{1,80}',key):
            return Response({'message':'需要1至80字符Idempotency-Key。'},status=400)
        payload={**p,'kind':kind,'mode':p.get('mode','multi'),'station_id':p.get('station_id','P5')}
        old=AgentRun.objects.filter(owner=request.user,request_key=key).first()
        if old: return Response(serialize(old),status=200 if old.input==payload else 409)
        expire_runs()
        try:
            with transaction.atomic():
                run=AgentRun.objects.create(owner=request.user,request_key=key,input=payload)
        except IntegrityError:
            return Response({'message':'当前已有运行任务或重复请求，请先等待或取消。'},status=409)
        return Response(serialize(run),status=202)


class RunDetail(APIView):
    permission_classes=[AuthenticatedRead]

    def get(self,request,pk):
        expire_runs()
        run=AgentRun.objects.filter(pk=pk,owner=request.user).first()
        return Response(serialize(run)) if run else Response(status=404)

    def post(self,request,pk):
        if request.data!={'action':'cancel'}: return Response({'message':'仅支持取消。'},status=400)
        AgentRun.objects.filter(pk=pk,owner=request.user,status__in=['queued','running']).update(
            status='cancelled',stage='cancelled',finished_at=timezone.now())
        return self.get(request,pk)


class RunExport(APIView):
    permission_classes=[AuthenticatedRead]

    def get(self,request,pk):
        run=AgentRun.objects.filter(pk=pk,owner=request.user).first()
        if not run: return Response(status=404)
        fmt=request.query_params.get('export_format','json')
        content=serialize(run)
        content['snapshot']=run.snapshot
        if fmt=='json':
            body=json.dumps(content,ensure_ascii=False,indent=2)
            mime='application/json'
        elif fmt=='html':
            body='<!doctype html><meta charset="utf-8"><title>运维证据报告</title><h1>运维证据报告</h1><p>来源、证据及复核意见见下；不是现场验收证明。</p><pre style="white-space:pre-wrap">'+html.escape(json.dumps(content,ensure_ascii=False,indent=2))+'</pre>'
            mime='text/html'
        elif fmt=='csv':
            stream=io.StringIO(); writer=csv.writer(stream)
            writer.writerow(['run','role','startedAt','output','source'])
            for step in run.steps:
                writer.writerow([str(run.pk),step['role'],step['startedAt'],json.dumps(step.get('output'),ensure_ascii=False),
                    json.dumps(run.snapshot.get('source'),ensure_ascii=False)])
            for key in ('guardrails','experienceContext'):
                if key in run.result:
                    writer.writerow([str(run.pk),'read_only:'+key,run.snapshot.get('capturedAt'),
                        json.dumps(run.result[key],ensure_ascii=False),json.dumps(run.snapshot.get('source'),ensure_ascii=False)])
            body='\ufeff'+stream.getvalue(); mime='text/csv'
        else: return Response(status=400)
        response=HttpResponse(body,content_type=mime+'; charset=utf-8')
        response['Content-Disposition']=f'attachment; filename="agent-{pk}.{fmt}"'
        response['X-Content-Type-Options']='nosniff'
        return response


class KnowledgeSearch(APIView):
    permission_classes=[AuthenticatedRead]
    def get(self,request):
        try: return Response(search(request.query_params.get('q',''),request.query_params.get('history')=='1'))
        except ValueError as exc: return Response({'message':str(exc)},status=400)


class CostEstimate(APIView):
    permission_classes=[AuthenticatedRead]
    def get(self,request): return Response({'example':example(),'configurationRequired':True})
    def post(self,request):
        try:
            if not isinstance(request.data,dict): raise ValueError('JSON object required.')
            # Client declarations are assumptions, never authenticated meter evidence.
            result=calculate({**request.data,'source':'ASSUMPTION_INPUT'})
            result['declaredSource']=request.data.get('source')
            return Response(result)
        except (ValueError,TypeError,KeyError,OverflowError) as exc: return Response({'message':str(exc)},status=400)


class DemoSessionView(APIView):
    permission_classes=[AuthenticatedRead]
    def get(self,request):
        return Response({'session':clean(demo.session_state()),'cases':demo.CASES})
    def post(self,request):
        if role(request.user)!='administrator': return Response(status=403)
        p=request.data
        if not isinstance(p,dict) or set(p)-{'action','caseId'}: return Response(status=400)
        try: return Response(clean(demo.control(p.get('action'),p.get('caseId'))))
        except ValueError as exc: return Response({'message':str(exc)},status=409)


def match_ack(action,ack):
    return (isinstance(ack,dict) and ack.get('cmdId')==str(action.pk)
        and ack.get('controllerId')==INVENTORY['fanControllers'][action.asset_code]
        and ack.get('generation')==str(action.generation) and ack.get('result')=='simulated_accepted')


class DemoCommands(APIView):
    permission_classes=[AuthenticatedRead]
    def post(self,request):
        demo.guard()
        if not write(request.user): return Response(status=403)
        p=request.data
        if not isinstance(p,dict) or set(p)-{'runId','proposalIndex'}: return Response(status=400)
        try:
            run=AgentRun.objects.get(pk=p['runId'],owner=request.user,status='completed')
            index=p['proposalIndex']
            if isinstance(index,bool) or not isinstance(index,int) or index<0: raise ValueError('无效动作编号。')
            if run.result.get('review',{}).get('decision')!='pass': raise ValueError('复核尚未通过。')
            from .agent_guardrails import VERSION
            report=run.result.get('guardrails')
            if not isinstance(report,dict) or report.get('version')!=VERSION or report.get('violations'):
                raise ValueError('规则版本变化或护栏已阻断，请重新核查。')
            item=run.result['controlProposals'][index]
            session=DemoSession.objects.get(pk=1)
            # A new scenario generation invalidates old reviewed proposals.
            if run.snapshot.get('demoGeneration')!=str(session.generation): raise ValueError('场景已变化，请重新核查。')
            if not run.finished_at or run.finished_at<timezone.now()-timedelta(seconds=120):
                raise ValueError('已复核建议超过120秒，请重新核查。')
            existing,_=SimulatedAction.objects.get_or_create(run=run,asset_code=item['asset_code'],intent=item['intent'],value=item['value'],
                defaults={'owner':request.user,'generation':session.generation,'expires_at':run.finished_at+timedelta(seconds=120)})
            return Response({'actionId':str(existing.pk),'state':existing.state,'assetCode':existing.asset_code,
                'intent':existing.intent,'value':existing.value,'expiresAt':existing.expires_at,'source':'SIMULATED_TEST'})
        except (AgentRun.DoesNotExist,ValidationError,KeyError,ValueError,IndexError,TypeError) as exc:
            return Response({'message':str(exc)},status=400)


class DemoCommandDetail(APIView):
    permission_classes=[AuthenticatedRead]
    @transaction.atomic
    def post(self,request,pk):
        demo.guard()
        if not write(request.user): return Response(status=403)
        if request.data not in ({'action':'confirm'},{'action':'cancel'}): return Response(status=400)
        a=SimulatedAction.objects.select_for_update().filter(pk=pk,owner=request.user).first()
        if not a: return Response(status=404)
        if a.state!='proposed': return Response({'state':a.state,'events':a.events,'replayed':True})
        if request.data['action']=='confirm':
            from .agent_guardrails import VERSION
            report=a.run.result.get('guardrails')
            if not isinstance(report,dict) or report.get('version')!=VERSION or report.get('violations'):
                return Response({'message':'规则版本已变化或任务被护栏阻断，需重新核查；仍可取消。'},status=409)
        session=DemoSession.objects.select_for_update().get(pk=1)
        if a.expires_at<=timezone.now() or a.generation!=session.generation:
            a.state='expired'; a.save(); return Response({'state':'expired'},status=409)
        if request.data['action']=='cancel':
            a.state='cancelled'; a.save(); return Response({'state':'cancelled'})
        action='relay_on' if a.intent=='power' and a.value else 'relay_off' if a.intent=='power' else 'fan_pwm' if a.asset_code=='FAN-01' else 'fan2_pwm'
        try:
            command=build_command(INVENTORY['fanControllers'][a.asset_code],action,a.value,str(a.pk))
        except ValueError as exc:
            return Response({'message':str(exc)},status=409)
        ack={'cmdId':str(a.pk),'controllerId':command['controllerId'],'generation':str(a.generation),'result':'simulated_accepted'}
        # Fault injection is server-only and remains confined to the demo adapter.
        behavior=getattr(settings,'AGENT_DEMO_ACK_BEHAVIOR','accept')
        a.events=[{'stage':'confirmed','at':timezone.now().isoformat(),'actor':request.user.pk},
            {'stage':'simulated_sent','at':timezone.now().isoformat(),'command':command}]
        if behavior=='timeout':
            a.state='simulated_timeout';a.save()
            return Response({'state':a.state,'events':a.events,'source':'SIMULATED_TEST'})
        if behavior=='reject': ack['result']='simulated_rejected'
        if behavior=='wrong_id': ack['cmdId']='unrelated-command'
        if behavior not in {'accept','reject','wrong_id'}:
            return Response({'message':'仿真适配器配置无效。'},status=409)
        a.events.append({'stage':'simulated_ack','at':timezone.now().isoformat(),'ack':ack})
        if not match_ack(a,ack):
            a.state='simulated_rejected' if behavior=='reject' else 'simulated_ack_mismatch';a.save()
            return Response({'state':a.state,'events':a.events,'source':'SIMULATED_TEST'})
        outputs=session.outputs.get(a.asset_code,{'power':True,'pwm':50})
        outputs[a.intent]=bool(a.value) if a.intent=='power' else a.value
        session.outputs={**session.outputs,a.asset_code:outputs}; session.save()
        a.state='simulated_accepted'
        a.events.append({'stage':'simulated_output_applied','at':timezone.now().isoformat(),'assetCode':a.asset_code})
        a.save()
        return Response({'state':a.state,'events':a.events,'source':'SIMULATED_TEST',
            'boundary':'回执仅为仿真输出应用；新模拟RPM由下次采样产生；未发布MQTT，未解除告警。'})
