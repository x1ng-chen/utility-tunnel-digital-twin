"""Authenticated investigation interfaces; none publish hardware commands."""
import copy
import uuid
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework.response import Response
from rest_framework.views import APIView
from .permissions import AuthenticatedRead
from .sprint_models import AgentRun, InvestigationCase, ProcedureTemplate, BranchComparison
from . import agent_investigations as cases
from . import agent_procedures as procedures


def admin(user):
    return user.is_superuser or getattr(getattr(user, 'profile', None), 'role', '') == 'administrator'


def writer(user):
    return admin(user) or getattr(getattr(user, 'profile', None), 'role', '') == 'operator'


def error(exc, status=400):
    return Response({'message': str(exc)}, status=status)


def identifier(value, label):
    try:
        return uuid.UUID(str(value))
    except (ValueError, TypeError, AttributeError):
        raise ValueError(label + '编号无效。')


class CaseList(APIView):
    permission_classes = [AuthenticatedRead]

    def get(self, request):
        return Response([cases.serialize_case(c) for c in InvestigationCase.objects.filter(owner=request.user).order_by('-updated_at')[:50]])

    def post(self, request):
        p = request.data
        if not isinstance(p, dict) or set(p) - {'station_id', 'asset_code', 'title'}:
            return error('无效档案字段。')
        station, asset = p.get('station_id', 'P5'), p.get('asset_code', '')
        title = p.get('title', f'{station}异常排查')
        if not isinstance(station, str) or station not in {'P1', 'P2', 'P3', 'P4', 'P5'} or not isinstance(asset, str):
            return error('工位或设备无效。')
        if not isinstance(title, str) or not 1 <= len(title.strip()) <= 160:
            return error('档案名称需为1～160字。')
        from .twin_presentation import runtime_inventory
        inventory = runtime_inventory()
        known = {b['assetCode']: b['stationId'] for b in inventory['bindings']}
        if asset and asset not in set(known) | {'FAN-01', 'FAN-02', 'CTRL-01', 'CTRL-02', 'CTRL-03', 'CTRL-04'}:
            return error('设备不在当前清单内。')
        if asset in known and known[asset] != station:
            return error('设备与当前展示工位不一致。')
        source, layout, presentation = cases.current_identity()
        case = InvestigationCase.objects.create(owner=request.user, title=title.strip(), station_id=station,
            asset_code=asset, source=source, layout_version=layout, presentation_version=presentation,
            state={'hypotheses': [], 'checks': [], 'history': []})
        return Response(cases.serialize_case(case), status=201)


class CaseDetail(APIView):
    permission_classes = [AuthenticatedRead]

    def get(self, request, pk):
        case = InvestigationCase.objects.filter(pk=pk, owner=request.user).first()
        return Response(cases.serialize_case(case)) if case else Response(status=404)


class CaseFeedback(APIView):
    permission_classes = [AuthenticatedRead]

    def post(self, request, pk):
        with transaction.atomic():
            case = InvestigationCase.objects.select_for_update().filter(pk=pk, owner=request.user).first()
            if not case:
                return Response(status=404)
            try:
                cases.feedback(case, request.data, request.user)
            except ValueError as exc:
                return error(exc)
            except RuntimeError as exc:
                return error(exc, 409)
            return Response(cases.serialize_case(case))


class TopologyView(APIView):
    permission_classes = [AuthenticatedRead]

    def get(self, request):
        from .agent_topology import build_topology, query_topology
        from .twin_presentation import runtime_inventory
        from .agent_operations import station_snapshot
        from .agent_context import data_context
        try:
            snapshot = {'topologyContext': build_topology(runtime_inventory(), bindings=station_snapshot('all')['items']),
                'source': data_context()}
            target = request.query_params.get('target')
            result = query_topology(snapshot, target, request.query_params.get('relation', 'dependencies')) if target else snapshot['topologyContext']
            return Response(result)
        except ValueError as exc:
            return error(exc)


class BranchCompareView(APIView):
    permission_classes = [AuthenticatedRead]

    def post(self, request):
        p = request.data
        if not isinstance(p, dict) or set(p) - {'run_id', 'candidates'} or 'run_id' not in p:
            return error('需指定已完成任务run_id，可选candidates。')
        try:
            ident = identifier(p['run_id'], '任务')
        except ValueError as exc:
            return error(exc)
        run = AgentRun.objects.filter(pk=ident, owner=request.user, status='completed').first()
        if not run:
            return Response(status=404)
        from .agent_branching import compare_scenarios
        try:
            result = compare_scenarios(copy.deepcopy(run.snapshot), p.get('candidates'))
        except (ValueError, TypeError) as exc:
            return error(exc)
        row = BranchComparison.objects.create(owner=request.user, run=run, result=result)
        return Response({'id': str(row.pk), 'runId': str(run.pk), **result}, status=201)


class ProcedureList(APIView):
    permission_classes = [AuthenticatedRead]

    def get(self, request):
        rows = ProcedureTemplate.objects.all() if admin(request.user) else ProcedureTemplate.objects.filter(Q(owner=request.user) | Q(status='approved'))
        return Response([procedures.serialize(p) for p in rows.order_by('-created_at')[:60]])

    def post(self, request):
        if not writer(request.user):
            return Response(status=403)
        p = request.data
        if not isinstance(p, dict) or set(p) - {'title', 'station_id', 'asset_kind', 'steps', 'source_refs', 'source_run_id'}:
            return error('无效流程字段。')
        station, title, kind = p.get('station_id', ''), p.get('title', ''), p.get('asset_kind', '')
        if not isinstance(station,str) or station not in {'P1', 'P2', 'P3', 'P4', 'P5'} or not isinstance(title, str) or not 1 <= len(title.strip()) <= 160 or not isinstance(kind,str) or kind not in {'', 'sensor', 'fan', 'controller'}:
            return error('请填写流程名称、适用工位和设备类别。')
        refs = p.get('source_refs', [])
        if not isinstance(refs, list) or not 1 <= len(refs) <= 12 or not all(isinstance(r, str) and len(r) <= 100 for r in refs):
            return error('需填写1～12项可核查来源引用。')
        from .agent_runbooks import RUNBOOKS
        from .sprint_knowledge import corpus, version
        from .agent_guardrails import VERSION
        from .models import Asset
        known = {d['id'] for d in corpus()} | {'RUNBOOK:' + name for name in RUNBOOKS}
        source_run = None
        try:
            if p.get('source_run_id'):
                source_run = AgentRun.objects.filter(pk=identifier(p['source_run_id'], '来源任务'), owner=request.user, status='completed').first()
                if not source_run:
                    return error('来源任务不可用。')
                known |= {e['id'] for e in source_run.result.get('evidence', []) if e.get('status') == 'ok'}
            if set(refs) - known:
                raise ValueError('来源不在已核查知识或本人的来源任务中。')
            steps = procedures.validate_steps(p.get('steps'), station, set(Asset.objects.filter(is_active=True).values_list('code', flat=True)))
        except (ValueError, TypeError, ValidationError) as exc:
            return error(exc)
        source, layout, presentation = cases.current_identity()
        if source_run and (source_run.snapshot.get('layoutVersion') != layout or source_run.snapshot.get('source', {}).get('mode') != source['mode']):
            return error('来源任务与当前布局或数据来源不匹配。')
        template = ProcedureTemplate(owner=request.user, source_run=source_run, title=title.strip(), station_id=station,
            asset_kind=kind, steps=steps, source_refs=refs, source_scope=source['mode'], layout_version=layout,
            presentation_version=presentation, rule_version=VERSION, knowledge_version=version())
        template.content_hash = procedures.digest(template)
        template.audit = [{'action': 'candidate_created', 'actor': request.user.pk, 'at': timezone.now().isoformat(),
            'validation': 'READ_ONLY_SCHEMA_CHECK_NOT_HUMAN_APPROVAL'}]
        template.save()
        return Response(procedures.serialize(template), status=201)


class ProcedureReview(APIView):
    permission_classes = [AuthenticatedRead]

    def post(self, request, pk):
        if not admin(request.user):
            return Response(status=403)
        p = request.data
        if not isinstance(p, dict) or set(p) != {'action', 'revision'} or not isinstance(p['action'],str) or p['action'] not in {'approve', 'reject', 'retire'} or type(p['revision']) is not int:
            return error('需提供审核动作和当前revision。')
        with transaction.atomic():
            template = ProcedureTemplate.objects.select_for_update().filter(pk=pk).first()
            if not template:
                return Response(status=404)
            allowed = {'candidate': {'approve', 'reject'}, 'approved': {'retire'}}
            if template.revision != p['revision'] or p['action'] not in allowed.get(template.status, set()):
                return error('审核状态或版本已变化，请刷新。', 409)
            if procedures.digest(template) != template.content_hash:
                return error('流程内容散列不一致，不能审核。', 409)
            if p['action'] == 'approve':
                from .agent_guardrails import VERSION
                from .sprint_knowledge import version
                source, layout, presentation = cases.current_identity()
                if (template.source_scope, template.layout_version, template.presentation_version, template.rule_version, template.knowledge_version) != (source['mode'], layout, presentation, VERSION, version()):
                    return error('来源或适用版本已变化，请创建新候选。', 409)
                from .models import Asset
                try:
                    procedures.validate_steps(template.steps, template.station_id, set(Asset.objects.filter(is_active=True).values_list('code', flat=True)))
                except ValueError as exc:
                    return error(exc)
                # Exercise actual frozen read-only tools before publication. This does
                # not certify free-text stop conditions, knowledge truth, or hardware.
                from .sprint_agents import Workflow, freeze
                payload={'kind':'diagnosis','station_id':template.station_id}
                target=next((s['args'].get('asset_code') for s in template.steps if s['args'].get('asset_code')),None)
                if target: payload['asset_code']=target
                candidate_run=AgentRun(owner=request.user,input=payload,snapshot=freeze(payload,request.user))
                workflow=Workflow(candidate_run)
                regression=[]
                try:
                    for step in template.steps:
                        workflow.execute(step['tool'],step['args'])
                        regression.append({'tool':step['tool'],'status':'read_only_tool_returned'})
                except (ValueError,TypeError,KeyError) as exc:
                    return error('流程只读回归未通过：'+str(exc))
                template.audit.append({'action':'read_only_regression','at':timezone.now().isoformat(),
                    'snapshotHash':candidate_run.snapshot['sha256'],'steps':regression,
                    'modelCalls':0,'commandsSent':0,'boundary':'工具可执行性检查，不验证自由文本条件或现场正确性。'})
            template.status = {'approve': 'approved', 'reject': 'rejected', 'retire': 'retired'}[p['action']]
            template.revision += 1
            template.audit.append({'action': p['action'], 'actor': request.user.pk, 'at': timezone.now().isoformat(),
                'contentHash': template.content_hash, 'approvalType': 'AUTHENTICATED_ADMINISTRATOR_REVIEW'})
            template.save(update_fields=['status', 'revision', 'audit'])
            return Response(procedures.serialize(template))


class ProcedureFromRun(APIView):
    permission_classes=[AuthenticatedRead]

    def post(self,request):
        if not writer(request.user): return Response(status=403)
        p=request.data
        if not isinstance(p,dict) or set(p)!={'run_id'}: return error('需指定来源任务run_id。')
        try: ident=identifier(p['run_id'],'来源任务')
        except ValueError as exc: return error(exc)
        run=AgentRun.objects.filter(pk=ident,owner=request.user,status='completed').first()
        if not run: return Response(status=404)
        source,layout,presentation=cases.current_identity()
        from .agent_guardrails import VERSION
        from .sprint_knowledge import version
        if (run.snapshot.get('layoutVersion'),run.snapshot.get('presentationVersion',''),
                run.snapshot.get('guardRuleVersion'),run.snapshot.get('knowledgeVersion'),
                run.snapshot.get('source',{}).get('mode'))!=(layout,presentation,VERSION,version(),source['mode']):
            return error('来源任务版本或数据来源已不适用，不能提取当前流程。')
        steps,refs,seen=[],[],set()
        import json
        for e in run.result.get('evidence',[]):
            if e.get('status')!='ok' or e.get('tool') not in procedures.READ_TOOLS-{'review_work_order','procedure_templates'}: continue
            key=json.dumps([e['tool'],e.get('arguments',{})],sort_keys=True)
            if key in seen: continue
            seen.add(key);refs.append(e['id'])
            steps.append({'tool':e['tool'],'args':e.get('arguments',{}),
                'expectedEvidence':'保留实际返回的来源、时间或配置版本、质量与缺项。',
                'stopCondition':'工具错误或所需证据缺失时停止确认并补证；文字条件仍需复核。'})
            if len(steps)==6: break
        if not steps: return error('本任务没有可复用的成功只读检查步骤。')
        from .models import Asset
        try: procedures.validate_steps(steps,run.input.get('station_id','P5'),set(Asset.objects.filter(is_active=True).values_list('code',flat=True)))
        except (ValueError,TypeError) as exc: return error(exc)
        station=run.input.get('station_id','P5')
        if station=='all': return error('请从明确检测站的排障任务提取流程。')
        template=ProcedureTemplate(owner=request.user,source_run=run,title=station+'排障只读流程候选',
            station_id=station,steps=steps,source_refs=refs,source_scope=source['mode'],layout_version=layout,
            presentation_version=presentation,rule_version=VERSION,knowledge_version=version())
        template.content_hash=procedures.digest(template)
        template.audit=[{'action':'extracted_successful_read_only_steps','actor':request.user.pk,
            'sourceRunId':str(run.pk),'at':timezone.now().isoformat(),'status':'CANDIDATE_NOT_APPROVED',
            'boundary':'真实工具轨迹整理，不是模型训练、知识正确性或人工审批证明。'}]
        template.save()
        return Response(procedures.serialize(template),status=201)


class RunAnalysis(APIView):
    permission_classes = [AuthenticatedRead]

    def get(self, request, pk):
        run = AgentRun.objects.filter(pk=pk, owner=request.user).first()
        if not run:
            return Response(status=404)
        from .agent_failure_analysis import analyze
        return Response(analyze(run))
