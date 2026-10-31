"""Reviewed executable read-only checklists; no shell, code or output authority."""
import copy
import hashlib
import json
from .sprint_models import ProcedureTemplate

READ_TOOLS = {'station_snapshot', 'asset_snapshot', 'telemetry_trend', 'active_work_orders',
    'collect_station_evidence', 'review_work_order', 'runtime_overview', 'open_alerts', 'query_topology'}


def validate_steps(steps, station, assets=None):
    from .sprint_agents import TOOLS
    from .sprint_validation import validate_arguments
    if not isinstance(steps, list) or not 1 <= len(steps) <= 6:
        raise ValueError('流程需包含1～6个只读检查步骤。')
    for step in steps:
        if not isinstance(step, dict) or set(step) != {'tool', 'args', 'expectedEvidence', 'stopCondition'}:
            raise ValueError('步骤需包含tool、args、expectedEvidence和stopCondition。')
        if step['tool'] not in READ_TOOLS or step['tool'] not in TOOLS:
            raise ValueError('流程不允许控制、草案、任意代码或未知工具。')
        validate_arguments(TOOLS[step['tool']]['function']['parameters'], step['args'])
        for field in ('expectedEvidence', 'stopCondition'):
            if not isinstance(step[field], str) or not 1 <= len(step[field]) <= 300:
                raise ValueError('步骤的证据要求和停止条件需为1～300字文本。')
        target = step['args'].get('station_id')
        if target and target not in {'all', station}:
            raise ValueError('步骤工位与流程适用工位不一致。')
        asset = step['args'].get('asset_code')
        if assets is not None and asset and asset not in assets:
            raise ValueError('步骤设备不在当前冻结清单内。')
    return copy.deepcopy(steps)


def digest(template):
    body = {'title': template.title, 'station': template.station_id, 'assetKind': template.asset_kind,
        'steps': template.steps, 'sourceRefs': template.source_refs, 'scope': template.source_scope,
        'layout': template.layout_version, 'presentation': template.presentation_version,
        'knowledge': template.knowledge_version, 'rules': template.rule_version}
    return hashlib.sha256(json.dumps(body, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def serialize(template):
    return {'id': str(template.pk), 'title': template.title, 'stationId': template.station_id,
        'assetKind': template.asset_kind, 'steps': template.steps, 'sourceRefs': template.source_refs,
        'status': template.status, 'revision': template.revision, 'layoutVersion': template.layout_version,
        'presentationVersion': template.presentation_version, 'ruleVersion': template.rule_version,
        'knowledgeVersion': template.knowledge_version, 'sourceScope': template.source_scope,
        'contentHash': template.content_hash, 'audit': template.audit,
        'boundary': '受审只读流程；文本条件仍需模型与人工核查，不批准动作，不代表现场正确。'}


def matching(snapshot, payload):
    station = payload.get('station_id', 'P5')
    queryset = ProcedureTemplate.objects.filter(status='approved', station_id=station,
        source_scope=snapshot['source']['mode'], layout_version=snapshot['layoutVersion'],
        presentation_version=snapshot.get('presentationVersion',snapshot.get('inventory', {}).get('presentationRevision', '')),
        knowledge_version=snapshot['knowledgeVersion'], rule_version=snapshot['guardRuleVersion']).order_by('-created_at')
    selected = payload.get('procedure_id')
    if selected: queryset=queryset.filter(pk=selected)
    items = []
    kind = snapshot.get('assetKinds', {}).get(payload.get('asset_code'), '')
    for template in queryset[:30]:
        if template.content_hash != digest(template) or template.asset_kind and template.asset_kind != kind:
            continue
        validate_steps(template.steps, station, snapshot.get('assets', {}))
        items.append(serialize(template))
    if selected and not any(i['id'] == selected for i in items):
        raise ValueError('指定流程未批准、版本或来源不匹配，不能执行。')
    return {'items': items[:3] if not selected else [i for i in items if i['id'] == selected],
        'selectedId': selected, 'authority': 'APPROVED_READ_ONLY_PROCEDURE_NOT_OBSERVATION'}
