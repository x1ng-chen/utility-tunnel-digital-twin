"""Deterministic, non-exclusive hypotheses with support, counterevidence and gaps."""
from .agent_context import evaluation_enabled, observation_valid
from django.utils import timezone

FAN_CONTROLLERS = {'FAN-01': 'CTRL-04', 'FAN-02': 'CTRL-02'}


def analyze(inspection, neighbors, fans, commands):
    facts, candidates, missing = [], [], []

    def candidate(code, title, support, against, gaps, next_check):
        candidates.append({'code': code, 'title': title, 'support': support,
            'counterevidence': against, 'missing': gaps, 'nextCheck': next_check,
            'conclusion': '候选解释，尚未确认根因'})

    for code, controller in FAN_CONTROLLERS.items():
        readings = (fans.get(code) or {}).get('readings', [])

        def reading(key, units):
            return next((r for r in readings if r['metric_key'] == key and observation_valid(r)
                         and r['unit'] in units and r['value'] >= 0), None)

        rpm = reading('rotational.speed', {'rpm'})
        current = reading('motor.current', {'A', 'mA'})
        voltage = reading('supply.voltage', {'V'})
        current_a = current['value'] / (1000 if current['unit'] == 'mA' else 1) if current else None
        requested = next((c for c in commands if c['controller'] == controller
            and c.get('asset_code') == code and c.get('protocol_version') in
            ({'four-controller-v1', 'four-controller-v2', 'four-controller-eval-v1'} if evaluation_enabled() else {'four-controller-v1', 'four-controller-v2'})), None)
        v2 = requested and requested['protocol_version'] == 'four-controller-v2'
        intent = (requested.get('command_intent') if v2 else requested['command_action']) if requested else None
        issued = requested.get('issued_at_ms') if v2 else None
        lease = requested.get('manual_lease_ms') if v2 else None
        lease_active = bool(v2 and isinstance(issued, int) and isinstance(lease, int) and
                            issued <= int(timezone.now().timestamp()*1000) < issued+lease)
        intent_support = []
        if requested and (not v2 or lease_active):
            if intent == 'fan.power_on':
                intent_support = ['有独立供电开启请求记录；不证明PWM已设定或风机转动']
            elif intent == 'fan.pwm':
                intent_support = ['有PWM设定请求记录；不证明继电器供电或风机转动']
            elif intent == 'fan.start':
                intent_support = ['有旧版显式启动请求记录，实际执行仍待核对']
        facts.append({'assetCode': code, 'controllerId': controller,
            'rpm': rpm['value'] if rpm else None, 'currentA': current_a,
            'supplyV': voltage['value'] if voltage else None,
            'commandIntent': intent,
            'commandValue': requested.get('command_value') if v2 else None,
            'commandOutcome': requested.get('outcome') if requested else None,
            'commandLeaseActive': lease_active if v2 else None,
            'outputsApplied': bool(v2 and requested.get('outcome') == 'accepted'),
            'movementState': 'observed_rotating' if rpm and rpm['value'] > 0 else 'observed_zero_rpm' if rpm else 'unknown',
            'controlBoundary': 'PWM和继电器供电独立；回执仅是输出证据，实际运动由新鲜良好RPM观测证明。',
            'measurementIds': [r['id'] for r in (rpm, current, voltage) if r]})
        gaps = [name for name, value in [('转速', rpm), ('电流', current), ('供电电压', voltage),
                                        ('新布局下的控制意图记录', requested)] if value is None]
        missing.extend(f'{code}：{name}证据缺失或不可用' for name in gaps)
        if voltage and voltage['value'] == 0:
            candidate('power_evidence_abnormal', f'{code}供电证据异常',
                ['新鲜良好电压观测为0V'] + intent_support,
                ['有电流或转速观测，与完全断电不一致'] if (current_a or (rpm and rpm['value'])) else [],
                ['电压测点、测量链路和实际供电仍需核对'], '人工核对测点与供电/继电器，不能仅据0V判定电机损坏')
        if not rpm and current_a is not None and current_a > 0:
            candidate('tach_feedback_missing', f'{code}测速证据不足', ['观测到独立电流，缺少可用rpm'],
                ['有电流不等于叶轮转动'], ['TACH接线、脉冲与实际转动未核对'], '人工核对TACH与实际转动，保留机械异常等其他解释')
        elif rpm and rpm['value'] == 0:
            candidate('zero_rpm_unresolved', f'{code}零转速原因待查', ['观测到0rpm'],
                ['可能为正常停机；独立供电或PWM请求不等于完整运行条件'] if intent != 'fan.start' else [],
                gaps, '比较控制意图、供电、驱动和测速链路后再判断')

    alerts = [a for item in inspection['items'] for a in item['active_alerts']]
    peers = {code: snap for code, snap in neighbors.items()
             if code not in {i['assetCode'] for i in inspection['items']}}
    usable_peers = [code for code, snap in peers.items() if snap['readings']
                    and all(observation_valid(r) for r in snap['readings'])]
    peer_alarm_codes = [code for code, snap in peers.items() if any(
        r['metric_key'] in {'smoke.alarm', 'flame.alarm'} and observation_valid(r) and r['value'] != 0
        for r in snap['readings'])]
    if len(alerts) == 1:
        candidate('single_sensor_anomaly', '单测点异常，原因尚待排除',
            [f"本站仅发现一条活动告警：{alerts[0]['code']}", f'其他站有{len(usable_peers)}个可用测点'],
            [f'其他站存在离散报警：{", ".join(peer_alarm_codes)}'] if peer_alarm_codes else [],
            ['原始ADC不能跨探头直接比较为浓度', '局部环境异常和传感器/接线异常均未排除'],
            '核对该探头自身变化、同站其他证据与人工检查，不直接断言探头损坏')
    if len(usable_peers) != len(peers) or not peers:
        candidate('neighbor_evidence_incomplete', '邻站证据不足，无法进行完整比较',
            [f'邻站观测可用{len(usable_peers)}/{len(peers)}'], [],
            ['缺项、离线、过期或坏质量的邻站数据'], '先恢复可核查的邻站数据；不推断扩散方向')
    return {'state': 'hypotheses_only' if candidates else 'insufficient_evidence', 'facts': facts,
        'candidates': candidates, 'missingEvidence': missing,
        'boundary': '确定性证据整理，不输出根因置信度、扩散预测或安全进入结论。'}
