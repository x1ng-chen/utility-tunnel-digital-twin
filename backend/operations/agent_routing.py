"""Closed candidate actions and compact state; a model cannot invent arguments."""
def candidates(run, evidence):
    payload=run.input
    good={(e['tool'],str(sorted((e.get('arguments') or {}).items()))) for e in evidence if e.get('status')=='ok'}
    station=payload.get('station_id','P5')
    target=payload.get('asset_code') or (station if station!='all' else 'CTRL-01')
    rows=[{'id':'collect_station','label':'取得本站、邻站及双风机证据','description':'缺少实际观测时优先补取，不认定根因。','tool':'collect_station_evidence','args':{}},
        {'id':'dependencies','label':'查询设备依赖','description':'调查共用主控与通信路径；配置关系不是接线实测。','tool':'query_topology','args':{'target':target,'relation':'dependencies'}},
        {'id':'inspect_all','label':'核对五站覆盖与质量','description':'查31路清单、缺测、时间和质量，不按指标条数计模块。','tool':'station_snapshot','args':{'station_id':'all'}}]
    if payload.get('asset_code'):
        rows.append({'id':'target_snapshot','label':'检查目标设备观测','description':'读取明确目标，区分在线与读数有效。','tool':'asset_snapshot','args':{'asset_code':target}})
    rows=[r for r in rows if (r['tool'],str(sorted(r['args'].items()))) not in good]
    rows.append({'id':'uncertain','label':'本列表没有适用的下一项检查','description':'候选均不适用、仅重复已完成检查或请求越权时选择；缺少观测本身是取证理由，不等于无检查可选。','tool':None,'args':{}})
    return rows[:8]


def decision_state(run,evidence):
    s=run.snapshot
    context=s.get('caseContext',{}).get('state',{})
    target=run.input.get('asset_code')
    asset=s.get('assets',{}).get(target,{})
    def compact(code):
        a=s.get('assets',{}).get(code,{})
        return {'asset':code,'connection':a.get('connection',{}).get('state'),
            'readings':[{k:r.get(k) for k in ('metric_key','value','unit','quality','freshness','usable','scenario_usable')}
                for r in a.get('readings',[])[:3]]}
    station=run.input.get('station_id','P5')
    nearby=[b['assetCode'] for b in s.get('inventory',{}).get('bindings',[]) if b.get('stationId')==station][:3]
    return {'task':run.input.get('kind'),'station':run.input.get('station_id'),'asset':target,
        'snapshotHash':s.get('sha256'),'source':{k:s.get('source',{}).get(k) for k in ('mode','hardwareLive')},'layoutVersion':s.get('layoutVersion'),
        'observations':{'connection':asset.get('connection'),'readings':asset.get('readings',[])[:6]},
        'stationObservations':[compact(c) for c in nearby],
        'fanObservations':[compact(c) for c in ('FAN-01','FAN-02')],
        'controllerStates':[{ 'asset':c,'connection':s.get('assets',{}).get(c,{}).get('connection',{}).get('state')}
            for c in ('CTRL-01','CTRL-02','CTRL-03','CTRL-04')],
        'alreadyCollected':[{'tool':e['tool'],'status':e['status']} for e in evidence[-8:]],
        'priorHypotheses':[h.get('label') for h in context.get('hypotheses',[])[:3]],
        'humanReports':[{'report':c.get('report','')[:300],'status':c['status']} for c in context.get('checks',[])
            if c.get('kind')=='human' and c.get('status')!='pending'][-3:],
        'boundary':'输入为低信任观测摘要与人工报告，仅选择允许的只读检查，不作安全或执行授权。'}
