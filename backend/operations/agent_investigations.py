"""Owner-scoped, resumable investigations. Reports are not instrument readings."""
import copy
import hashlib
import json
import uuid
from django.db import transaction
from django.utils import timezone
from .sprint_models import InvestigationCase


def source_identity(source):
    return {k: source.get(k) for k in ('mode', 'hardwareLive', 'scenarioId', 'generation', 'seededAt')}


def current_identity():
    from .agent_context import data_context
    from .twin_presentation import runtime_inventory
    inventory = runtime_inventory()
    return data_context(), inventory['revision'], presentation_identity(inventory)


def presentation_identity(inventory):
    from .models import TwinModelRelease
    release=TwinModelRelease.objects.filter(status='active').first()
    # Even an unrecognised model must invalidate a previous model's investigation.
    adapter=inventory.get('presentationRevision','')
    return (adapter+':'+release.sha256) if release else adapter


def compatible(case, payload, source, layout, presentation):
    if source_identity(case.source) != source_identity(source):
        raise ValueError('排障档案与当前数据来源或场景代次不同，请新建档案。')
    if case.layout_version != layout or case.presentation_version != presentation:
        raise ValueError('布局或模型展示版本已变化，请新建档案保留历史。')
    if payload.get('station_id', case.station_id) != case.station_id:
        raise ValueError('调查工位与档案目标不一致。')
    if payload.get('asset_code', case.asset_code) != case.asset_code:
        raise ValueError('调查设备与档案目标不一致。')


def serialize_case(case):
    state = copy.deepcopy(case.state)
    return {'id': str(case.pk), 'title': case.title, 'stationId': case.station_id,
        'assetCode': case.asset_code, 'status': case.status, 'revision': case.revision,
        'source': case.source, 'layoutVersion': case.layout_version,
        'presentationVersion': case.presentation_version, 'hypotheses': state.get('hypotheses', []),
        'checks': state.get('checks', []), 'history': state.get('history', []),
        'runs': [{'id': str(r.pk), 'status': r.status, 'createdAt': r.created_at.isoformat(),
            'snapshotHash': r.snapshot.get('sha256')} for r in case.runs.order_by('created_at')],
        'createdAt': case.created_at.isoformat(), 'updatedAt': case.updated_at.isoformat(),
        'boundary': '假设为待核查解释；人工报告不是测量事实；复核通过不自动结案。'}


def freeze_case(case):
    return {'id': str(case.pk), 'revision': case.revision, 'stationId': case.station_id,
        'assetCode': case.asset_code, 'source': case.source, 'state': copy.deepcopy(case.state),
        'trust': 'LOW_TRUST_PRIOR_HYPOTHESES_AND_HUMAN_REPORTS_NOT_MEASUREMENTS'}


def _text(value, limit=300):
    return value[:limit] if isinstance(value, str) else ''


def record_run(run):
    if not run.case_id:
        return
    with transaction.atomic():
        case = InvestigationCase.objects.select_for_update().get(pk=run.case_id, owner=run.owner)
        state = copy.deepcopy(case.state)
        history = state.setdefault('history', [])
        if any(h.get('runId') == str(run.pk) and h.get('event') == 'run_recorded' for h in history):
            return
        before = copy.deepcopy(state.get('hypotheses', []))
        answer = run.result.get('answer', {})
        good = {e['id'] for e in run.result.get('evidence', []) if e.get('status') == 'ok'}
        def refs(value):
            return [i for i in value if isinstance(i, str) and i in good][:24] if isinstance(value, list) else []
        hypotheses = []
        for index, item in enumerate(answer.get('candidates', [])[:3]):
            item = item if isinstance(item, dict) else {'label': item}
            label = _text(item.get('label') or item.get('cause') or item.get('reason') or item.get('name'))
            if not label:
                continue
            hypotheses.append({'id': str(uuid.uuid5(case.pk, label)), 'label': label,
                'status': 'candidate', 'supportRefs': refs(item.get('support_refs', item.get('evidence_ids', []))),
                'counterRefs': refs(item.get('counter_refs', [])),
                'missing': [_text(x) for x in item.get('missing', [])[:5]] if isinstance(item.get('missing'), list) else [],
                'runId': str(run.pk), 'snapshotHash': run.snapshot.get('sha256'),
                'authority': 'MODEL_HYPOTHESIS_NOT_CONFIRMED_ROOT_CAUSE'})
        if hypotheses:
            state['hypotheses'] = hypotheses
        checks = state.setdefault('checks', [])
        for index, item in enumerate(answer.get('next_checks', [])[:3]):
            label = _text(item if isinstance(item, str) else item.get('label', item.get('description', '')) if isinstance(item, dict) else '')
            if label:
                checks.append({'id': str(uuid.uuid5(run.pk, f'check:{index}:{label}')), 'label': label,
                    'kind': 'human', 'tool': None, 'args': {}, 'status': 'pending', 'report': '',
                    'source': 'MODEL_SUGGESTION', 'evidenceRefs': [], 'runId': str(run.pk)})
        for entry in run.result.get('decisionTrace', []):
            if entry.get('executedTool'):
                checks.append({'id': str(uuid.uuid5(run.pk, 'tool:' + str(entry.get('executedEvidenceId')))),
                    'label': entry.get('selectedOption', entry['executedTool']), 'kind': 'software',
                    'tool': entry['executedTool'], 'args': entry.get('executedArguments', {}),
                    'status': 'completed' if entry.get('executedEvidenceId') in good else 'unavailable',
                    'report': '', 'source': 'ANYJEV_READ_ONLY_ROUTING',
                    'evidenceRefs': [entry['executedEvidenceId']] if entry.get('executedEvidenceId') else [], 'runId': str(run.pk)})
        history.append({'event': 'run_recorded', 'runId': str(run.pk), 'status': run.status,
            'at': timezone.now().isoformat(), 'snapshotHash': run.snapshot.get('sha256'),
            'previousHypotheses': before, 'hypotheses': copy.deepcopy(state.get('hypotheses', [])),
            'previousSnapshot': run.snapshot.get('previousSnapshot'), 'claim': 'MODEL_REVIEW_IS_NOT_PHYSICAL_ACCEPTANCE'})
        case.state = state
        case.status = 'awaiting_feedback' if any(c['status'] == 'pending' for c in checks) else 'open'
        case.revision += 1
        case.save(update_fields=['state', 'status', 'revision', 'updated_at'])


def feedback(case, payload, user):
    if not isinstance(payload, dict) or set(payload) != {'check_id', 'status', 'report', 'revision'}:
        raise ValueError('反馈需包含check_id、status、report和revision。')
    if not isinstance(payload['status'], str) or payload['status'] not in {'completed', 'unavailable'} or not isinstance(payload['report'], str) or not 1 <= len(payload['report'].strip()) <= 1000:
        raise ValueError('请填写1～1000字人工检查报告，并选择完成或无法执行。')
    if type(payload['revision']) is not int:
        raise ValueError('版本号无效。')
    state = copy.deepcopy(case.state)
    check = next((c for c in state.get('checks', []) if c['id'] == payload['check_id']), None)
    if not check or check.get('kind') != 'human':
        raise ValueError('仅允许反馈本档案中的人工检查项。')
    if check['status'] != 'pending':
        if check['status'] == payload['status'] and check.get('report') == payload['report'].strip():
            return
        raise RuntimeError('该检查已反馈，请开始新一轮检查。')
    if case.revision != payload['revision']:
        raise RuntimeError('档案版本已更新，请刷新后提交。')
    check.update(status=payload['status'], report=payload['report'].strip(), reportedBy=user.pk,
        reportedAt=timezone.now().isoformat(), reportSource='HUMAN_REPORT_NOT_INSTRUMENT_MEASUREMENT')
    state.setdefault('history', []).append({'event': 'human_feedback', 'checkId': check['id'],
        'status': check['status'], 'report': check['report'], 'at': check['reportedAt'], 'actor': user.pk,
        'source': 'HUMAN_REPORT_NOT_INSTRUMENT_MEASUREMENT'})
    case.state = state
    case.status = 'awaiting_feedback' if any(c['status']=='pending' for c in state.get('checks',[])) else 'open'
    case.revision += 1
    case.save(update_fields=['state', 'status', 'revision', 'updated_at'])
