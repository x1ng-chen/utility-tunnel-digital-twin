"""Explicit demonstration assumptions; never inferred from a live measurement."""
def demo_profile(snapshot):
    if snapshot.get('source',{}).get('mode')!='simulated_test': return None
    # Absent starting measurements remain gaps. Never force them to fit a model.
    models={}
    for code in ('FAN-01','FAN-02'):
        readings=snapshot.get('assets',{}).get(code,{}).get('readings',[])
        observed={r.get('metric_key'):r for r in readings if r.get('quality')=='good' and r.get('scenario_usable')}
        models[code]={'initialPower':False,'initialPwm':0,'rpmAt50':1200,'powerWAt50':3.6,'fault':'none'}
        rpm=observed.get('rotational.speed')
        if rpm and rpm.get('value',0)>0:
            models[code]['initialPower']=True
            models[code]['initialPwm']=50
    return {'version':'fan-response-demo-v1','windowSeconds':60,'fanModels':models,
        'requiredFanCount':1,'runbookApproved':False,'tariffs':[],
        'assumptions':['SIMULATED_SCENARIO_ASSUMPTION：1200rpm/3.6W为教学参数，未由INA或风量实验标定。',
            '本分支仅比较模拟运行反馈与教学约束，不是火灾或燃气通风策略；不推断气体恢复。',
            '未取得本场景已审核的处置策略，runbookApproved=false；不参加合规或节能排名。']}
