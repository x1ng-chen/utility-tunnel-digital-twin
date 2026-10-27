import math
import re


def validate_arguments(schema, value):
    if not isinstance(value,dict): raise ValueError('工具参数必须是对象。')
    props=schema.get('properties',{})
    if set(value)-set(props) or set(schema.get('required',[]))-set(value): raise ValueError('未知或缺失参数。')
    for name,v in value.items():
        rule=props[name]
        t=rule.get('type')
        if t=='string' and (not isinstance(v,str) or len(v)>rule.get('maxLength',2000)): raise ValueError('字符串参数无效。')
        if t=='integer' and (isinstance(v,bool) or not isinstance(v,int)): raise ValueError('整数参数无效。')
        if t=='boolean' and not isinstance(v,bool): raise ValueError('布尔参数无效。')
        if isinstance(v,(int,float)) and (not math.isfinite(v) or v<rule.get('minimum',-math.inf) or v>rule.get('maximum',math.inf)):
            raise ValueError('数字超出范围。')
        if 'enum' in rule and v not in rule['enum']: raise ValueError('不允许的枚举值。')
        if 'pattern' in rule and (not isinstance(v,str) or not re.fullmatch(rule['pattern'],v)): raise ValueError('参数格式无效。')


def validate_facts(output,evidence,assets):
    """Only explicit structured facts are checked, not arbitrary prose."""
    facts=output.get('facts',[])
    if not isinstance(facts,list): raise ValueError('facts必须是数组。')
    valid={e['id'] for e in evidence if e['status']=='ok'}
    for f in facts:
        if not isinstance(f,dict): raise ValueError('事实必须是对象。')
        code=f.get('asset_code')
        if code is not None and code not in assets:
            absence=any(e['status']=='ok' and e['tool']=='asset_snapshot' and e['data'].get('asset_code')==code
                and e['data'].get('exists') is False and e['id']==f.get('evidence_id') for e in evidence)
            if not absence or f.get('exists') is not False or set(f)-{'asset_code','exists','evidence_id'}:
                raise ValueError('事实引用不存在设备。')
            continue
        if f.get('evidence_id') is not None and f['evidence_id'] not in valid: raise ValueError('事实引用无效证据。')
        if code and 'metric_key' in f and 'value' in f:
            rows=assets[code].get('readings',[])
            if not any(r['metric_key']==f['metric_key'] and r['value']==f['value'] and
                ('unit' not in f or r['unit']==f['unit']) for r in rows): raise ValueError('结构化事实与冻结观测冲突。')
