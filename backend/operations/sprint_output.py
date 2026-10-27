"""Deterministic response checks. These do not grade arbitrary natural language."""
import json
import re


def _unique(pairs):
    value={}
    for key,item in pairs:
        if key in value: raise ValueError('JSON含重复字段：'+key)
        value[key]=item
    return value


def parse_output(text):
    if not isinstance(text,str) or len(text)>24000: raise ValueError('角色回复为空或过长。')
    fenced=re.findall(r'```(?:json)?\s*(.*?)```',text,re.S)
    if len(fenced)>1: raise ValueError('角色回复包含多个JSON代码块。')
    enclosed=bool(fenced)
    # Never interpret XML/DSML or textual pseudo-tool calls as executable tools.
    candidate=fenced[0] if enclosed else text.strip()
    value=json.loads(candidate,object_pairs_hook=_unique,parse_constant=lambda _: (_ for _ in ()).throw(ValueError('禁止非有限JSON数字。')))
    if not isinstance(value,dict) or not isinstance(value.get('summary'),str) or not value['summary'].strip():
        raise ValueError('角色输出必须为含summary的JSON。')
    return value,enclosed


def check_output(output,role,evidence,knowledge_ids,stage_traces,known_guard_ids=None):
    good={e['id'] for e in evidence if e['status']=='ok'}
    rejected={e['id'] for e in evidence if e['status']=='rejected'}
    ids=output.get('evidence_ids',[]);errors=output.get('rejection_ids',[])
    for value,allowed,label in ((ids,good,'证据'),(errors,rejected,'拒绝记录')):
        if not isinstance(value,list) or len(value)>24 or not all(isinstance(i,str) and i in allowed for i in value):
            raise ValueError('无效'+label+'引用。')
    refs=set(re.findall(r'(?<![A-Za-z0-9_])[EK]\d+(?![A-Za-z0-9_])',json.dumps(output,ensure_ascii=False)))
    if refs-(good|rejected|knowledge_ids): raise ValueError('输出含不存在的引用。')
    if (refs&rejected)-set(errors): raise ValueError('被拒调用须列入rejection_ids，不能作测量证据。')
    guard_ids=output.get('guard_ids',[]);known_guard_ids=set(known_guard_ids or ())
    if not isinstance(guard_ids,list) or len(guard_ids)>40 or not all(isinstance(i,str) and i in known_guard_ids for i in guard_ids):
        raise ValueError('无效规则推导引用；不能冒充原始E证据。')
    guard_refs=set(re.findall(r'(?<![A-Za-z0-9_])G\d+(?![A-Za-z0-9_])',json.dumps(output,ensure_ascii=False)))
    if guard_refs-set(guard_ids): raise ValueError('规则编号须列入guard_ids且属于本快照。')
    for key in ('missing','candidates','next_checks','findings','facts','claims'):
        if key in output and (not isinstance(output[key],list) or len(output[key])>40):
            raise ValueError(key+'必须是有界数组。')
    if 'request_evidence' in output and not isinstance(output['request_evidence'],str):
        raise ValueError('request_evidence必须是字符串。')
    if role=='evidence' and not any(t['status']=='ok' for t in stage_traces):
        raise ValueError('本阶段取证未成功调用工具。')
    if role=='review' and output.get('decision') not in {'pass','revise','insufficient'}:
        raise ValueError('复核决策无效。')


def task_contract(payload,evidence,proposals,orders,handbook_checked):
    """Check required tool products, not whether the model's diagnosis is true."""
    good=[e for e in evidence if e['status']=='ok'];kind=payload['kind'];gaps=[]
    if kind=='inspection' and not any(e['tool']=='station_snapshot' and e['data'].get('station_id')=='all' for e in good):
        gaps.append('缺少五站巡检的实际工具结果')
    if kind=='diagnosis':
        if not any(e['tool']=='collect_station_evidence' for e in good): gaps.append('缺少本站、邻站及双风机的取证结果')
        if not handbook_checked: gaps.append('未取得有效手册或当前适用知识依据')
    if kind=='draft':
        code=payload.get('asset_code')
        if not any(e['tool']=='asset_snapshot' and e['data'].get('asset_code')==code and e['data'].get('exists',True) for e in good):
            gaps.append('未查询草案目标设备')
        if not any(e['tool']=='active_work_orders' and e.get('arguments',{}).get('asset_code')==code for e in good):
            gaps.append('未查询目标已有工单')
        if not handbook_checked and not any(w['assetCode']==code for w in orders): gaps.append('缺少有效手册或当前适用知识依据')
        if not any(w['assetCode']==code for w in orders) and not any(p['assetCode']==code for p in proposals):
            gaps.append('未实际生成目标工单草案')
    if kind=='review' and not any(e['tool']=='review_work_order' and e.get('arguments',{}).get('work_order_code')==payload.get('work_order_code') for e in good):
        gaps.append('未读取指定工单的恢复复核结果')
    return {'passed':not gaps,'missing':gaps,'scope':'required_tool_products_only_not_factual_accuracy'}
