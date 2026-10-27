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
        if set(f)-{'asset_code','metric_key','value','unit','evidence_id','exists'}:
            raise ValueError('事实含未支持的字段；其他判断应在summary中说明并引用证据。')
        if any(k in f for k in ('metric_key','value','unit')) and (
            not isinstance(code,str) or not all(k in f for k in ('metric_key','value','unit','evidence_id'))
            or not isinstance(f['metric_key'],str) or not isinstance(f['unit'],str) or not f['unit']):
            raise ValueError('结构化测量事实缺少设备、指标、数值、单位或证据编号。')
        if code is not None and not isinstance(code,str): raise ValueError('事实设备编码必须是字符串。')
        if code is not None and code not in assets:
            absence=any(e['status']=='ok' and e['tool']=='asset_snapshot' and e['data'].get('asset_code')==code
                and e['data'].get('exists') is False and e['id']==f.get('evidence_id') for e in evidence)
            if not absence or f.get('exists') is not False or set(f)-{'asset_code','exists','evidence_id'}:
                raise ValueError('事实引用不存在设备。')
            continue
        if code and 'exists' in f and f['exists'] is not True: raise ValueError('存在性事实与冻结资产清单冲突。')
        if f.get('evidence_id') is not None and f['evidence_id'] not in valid: raise ValueError('事实引用无效证据。')
        if code and 'metric_key' in f and 'value' in f:
            if isinstance(f['value'],bool) or not isinstance(f['value'],(int,float)) or not math.isfinite(f['value']):
                raise ValueError('结构化测量值必须是有限数字。')
            rows=assets[code].get('readings',[])
            if not any(r['metric_key']==f['metric_key'] and r['value']==f['value'] and
                ('unit' not in f or r['unit']==f['unit']) for r in rows): raise ValueError('结构化事实与冻结观测冲突。')
            def contains(value,parent_code=None):
                if isinstance(value,dict):
                    current=next((value[k] for k in ('asset_code','assetCode','asset__code') if isinstance(value.get(k),str)),parent_code)
                    if current==code and value.get('metric_key')==f['metric_key'] and value.get('value')==f['value'] and ('unit' not in f or value.get('unit')==f['unit']):
                        return True
                    return any(contains(v,current) for v in value.values())
                if isinstance(value,list): return any(contains(v,parent_code) for v in value)
                return False
            source=next((e for e in evidence if e['id']==f.get('evidence_id') and e['status']=='ok'),None)
            if not source or not contains(source.get('data')): raise ValueError('所引工具结果未包含该设备的数值与单位。')
