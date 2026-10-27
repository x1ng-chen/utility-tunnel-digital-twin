"""Versioned deterministic checks over a frozen packet, never an actuator."""
from datetime import datetime
import math

VERSION='2026-10-27.1'
RULES={
    'FAN-OBS-1':'转动判断需同设备、新鲜、有效的独立RPM；耗电不证明转动，不确定唯一根因。',
    'GAS-UNIT-1':'原始ADC、电压和开关量不是标定浓度；不同单位不得混算。',
    'RECOVERY-1':'回执不能证明恢复；需工单后新观测、适用阈值规则和活动告警核查，仍需人工复核。',
    'EVIDENCE-1':'结构化事实必须与实际所引原始工具结果一致。',
    'ACCESS-1':'角色、明确目标、手册、人工确认和幂等限制不由资料或经验扩大。',
}
GAS_METRICS={'methane.raw','co.raw','oxygen.raw','oxygen.voltage','smoke.alarm'}
CONCENTRATION_UNITS={'ppm','ppb','%','％','%o2','% o2','%o₂','%vol','% vol','vol%','vol %','mg/m3','mg/m³','g/m3','g/m³','percent','%lel'}


def number(v): return isinstance(v,(int,float)) and not isinstance(v,bool) and math.isfinite(v)


def time(value):
    try:
        parsed=datetime.fromisoformat(value.replace('Z','+00:00'))
        return parsed if parsed.tzinfo else None
    except (ValueError,TypeError,AttributeError): return None


def scope(snapshot):
    source=snapshot.get('source',{})
    return source.get('mode','unknown') if isinstance(source,dict) else 'unknown'


def valid_reading(snapshot,asset,row):
    """Recheck flags against frozen timestamps; no wall-clock rejuvenation."""
    if not isinstance(row,dict) or not number(row.get('value')) or row.get('quality')!='good': return False
    connection=asset.get('connection',{});limit=connection.get('freshness_limit_seconds')
    captured,sampled,ingested=map(time,(snapshot.get('capturedAt'),row.get('sampled_at'),row.get('ingested_at')))
    if not captured or not sampled or not ingested or not number(limit) or limit<0: return False
    if not 0<=(captured-sampled).total_seconds()<=limit or ingested>captured or connection.get('state')!='online': return False
    if scope(snapshot)=='simulated_test':
        return row.get('scenario_usable') is True and row.get('provenance')=='simulated_test'
    return row.get('usable') is True and row.get('provenance')=='database_observation'


def metric(asset,key):
    return next((r for r in asset.get('readings',[]) if r.get('metric_key')==key),None)


def unit(row):
    value=row.get('unit')
    return value.strip().lower() if isinstance(value,str) else ''


def current_amps(row):
    if not row or not number(row.get('value')): return None
    return row['value'] if row.get('unit')=='A' else row['value']/1000 if row.get('unit')=='mA' else None


def contains_measurement(value,code,row,parent=None):
    if isinstance(value,dict):
        current=next((value[k] for k in ('asset_code','assetCode','asset__code') if isinstance(value.get(k),str)),parent)
        if current==code and all(value.get(k)==row.get(k) for k in ('metric_key','value','unit')): return True
        return any(contains_measurement(v,code,row,current) for v in value.values())
    if isinstance(value,list): return any(contains_measurement(v,code,row,parent) for v in value)
    return False


def evidence_ids(evidence,code,row):
    return [e['id'] for e in evidence if e.get('status')=='ok' and contains_measurement(e.get('data'),code,row)]


def derive(snapshot,evidence=()):
    findings=[];domain=scope(snapshot)
    def add(rule,code,state,message,ids=(),missing=()):
        findings.append({'id':f'G{len(findings)+1}','ruleId':rule,'ruleVersion':VERSION,'assetCode':code,
            'state':state,'message':message,'evidenceIds':list(ids),'missing':list(missing),
            'sourceScope':domain,'snapshotHash':snapshot.get('sha256'),'capturedAt':snapshot.get('capturedAt'),
            'kind':'deterministic_inference_not_measurement'})
    for code in ('FAN-01','FAN-02'):
        asset=snapshot.get('assets',{}).get(code,{})
        rpm=metric(asset,'rotational.speed');current=metric(asset,'motor.current')
        if rpm and valid_reading(snapshot,asset,rpm) and unit(rpm)=='rpm' and rpm['value']>=0:
            state='supported' if rpm['value']>0 else 'unsupported'
            message='本来源下存在有效正转速反馈。' if state=='supported' else '本来源下观测到零转速，原因未确定。'
            amps=current_amps(current) if current and valid_reading(snapshot,asset,current) else None
            if state=='unsupported' and amps is not None and amps>0:
                message+='有耗电而未观测到转动，需核查启动、驱动、机械和测速链路；不确定卡阻或皮带故障。'
            if state=='supported' and amps is not None and amps==0:
                message+='零电流与正转速可能涉及惯性或测量问题，不仅凭此判错。'
            add('FAN-OBS-1',code,state,message,evidence_ids(evidence,code,rpm))
            findings[-1]['derivedCurrentAmps']=amps
        else:
            add('FAN-OBS-1',code,'unknown','缺少可用独立转速反馈；不能判断是否转动。',missing=['fresh_valid_same_asset_rpm'])
    for code,asset in snapshot.get('assets',{}).items():
        rows=[r for r in asset.get('readings',[]) if r.get('metric_key') in GAS_METRICS]
        if rows:
            add('GAS-UNIT-1',code,'unsupported','只提供原始量或开关量；本版本没有经核实的浓度标定契约，不支持可信ppm、氧浓度或跨探头浓度梯度。',
                sorted({i for r in rows for i in evidence_ids(evidence,code,r)}),['verified_calibration'])
    review=snapshot.get('workOrderReview')
    if isinstance(review,dict):
        code=review.get('asset_code');asset=snapshot.get('assets',{}).get(code,{})
        rows=asset.get('readings',[]);updated=time(review.get('work_order_updated_at'))
        applicable=snapshot.get('thresholds',{})
        configured=bool(rows) and all(r.get('metric_key') in applicable for r in rows)
        fresh=bool(rows) and updated and all(valid_reading(snapshot,asset,r) and time(r.get('sampled_at'))>updated for r in rows)
        normal=configured and all(number(applicable[r['metric_key']].get('warning')) and
            unit(r)==unit(applicable[r['metric_key']]) and
            r['value']<applicable[r['metric_key']]['warning'] for r in rows if number(r.get('value')))
        count=review.get('active_alert_count')
        state='unsupported' if type(count) is int and count>0 else 'supported' if type(count) is int and count==0 and fresh and normal else 'unknown'
        ids=[e['id'] for e in evidence if e.get('status')=='ok' and e.get('tool')=='review_work_order'
            and e.get('data',{}).get('work_order_code')==review.get('work_order_code')]
        add('RECOVERY-1',code,state,
            '仅本来源、已配置上限规则下的新观测恢复支持；不证明现场安全或持续稳定，不自动结单。' if state=='supported' else
            '仍有活动告警，不能声明恢复。' if state=='unsupported' else '缺少完整的新观测、适用阈值或告警核查；回执不能补齐这些证据。',
            ids,[] if state!='unknown' else ['post_work_order_valid_observations_and_applicable_rules'])
    return {'version':VERSION,'findings':findings,'violations':[],
        'boundary':'规则推导与原始观测分开；仅核验结构化断言和动作前提，不验证全部自然语言，不确定唯一根因。'}


class GuardViolation(ValueError):
    def __init__(self,rule,message): self.rule=rule;super().__init__(message)


def validate_claims(output,snapshot,evidence):
    claims=output.get('claims',[])
    if not isinstance(claims,list) or len(claims)>12: raise GuardViolation('EVIDENCE-1','claims必须是至多12项的数组。')
    findings=derive(snapshot,evidence)['findings'];good={e['id'] for e in evidence if e.get('status')=='ok'}
    seen=set()
    for c in claims:
        if not isinstance(c,dict) or set(c)!={'kind','asset_code','state','evidence_ids'}:
            raise GuardViolation('EVIDENCE-1','断言需明确kind、asset_code、state和evidence_ids。')
        if not isinstance(c['kind'],str) or not isinstance(c['state'],str) or c['kind'] not in {'fan_motion','alarm_recovery'} or c['state'] not in {'supported','unsupported','unknown'} or not isinstance(c['asset_code'],str):
            raise GuardViolation('EVIDENCE-1','断言类型、状态或目标无效。')
        ident=(c['kind'],c['asset_code'])
        if ident in seen: raise GuardViolation('EVIDENCE-1','重复的同目标断言。')
        seen.add(ident)
        ids=c['evidence_ids']
        if not isinstance(ids,list) or len(ids)>24 or not all(isinstance(i,str) and i in good for i in ids):
            raise GuardViolation('EVIDENCE-1','断言只能引用实际成功的原始E证据。')
        rule='FAN-OBS-1' if c['kind']=='fan_motion' else 'RECOVERY-1'
        finding=next((f for f in findings if f['ruleId']==rule and f['assetCode']==c['asset_code']),None)
        if not finding: raise GuardViolation(rule,'目标不属于本快照中可判定的断言范围。')
        if c['state']!='unknown' and (c['state']!=finding['state'] or not set(ids)&set(finding['evidenceIds'])):
            raise GuardViolation(rule,'断言缺少匹配的有效原始证据，或与规则判断冲突。')


def validate_output(output,snapshot,evidence):
    from .sprint_validation import validate_facts
    if not isinstance(output.get('facts',[]),list): raise GuardViolation('EVIDENCE-1','facts必须是数组。')
    for fact in output.get('facts',[]):
        if isinstance(fact,dict) and isinstance(fact.get('unit'),str) and fact['unit'].strip().lower() in CONCENTRATION_UNITS:
            code=fact.get('asset_code');asset=snapshot.get('assets',{}).get(code,{}) if isinstance(code,str) else {}
            if any(r.get('metric_key') in GAS_METRICS for r in asset.get('readings',[])):
                raise GuardViolation('GAS-UNIT-1','当前原始气体通道没有可信浓度标定契约。')
    try: validate_facts(output,evidence,snapshot.get('assets',{}))
    except ValueError as exc: raise GuardViolation('EVIDENCE-1',str(exc)) from exc
    validate_claims(output,snapshot,evidence)
