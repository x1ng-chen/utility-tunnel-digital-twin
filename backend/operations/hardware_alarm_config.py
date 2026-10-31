"""Commissioning thresholds, not certified gas limits or entry criteria."""
from copy import deepcopy
from .hardware_live import INVENTORY, SPECS

RULES = [
    {'key':'flame.alarm', 'label':'火焰数字输入', 'warning':.5, 'alarm':1, 'unit':'bool'},
    {'key':'smoke.alarm', 'label':'烟雾数字输入', 'warning':.5, 'alarm':1, 'unit':'bool'},
    {'key':'level.detected', 'label':'液位触水验收', 'warning':.5, 'alarm':1, 'unit':'bool'},
    {'key':'temperature', 'label':'温度上限（验收暂定）', 'warning':28, 'alarm':32, 'unit':'°C'},
    {'key':'humidity', 'label':'湿度上限（验收暂定）', 'warning':75, 'alarm':85, 'unit':'%RH'},
    {'key':'methane.raw', 'label':'MQ-4原始ADC验收（非浓度）', 'warning':3000, 'alarm':3500, 'unit':'adc'},
    {'key':'co.raw', 'label':'MQ-7原始ADC验收（非浓度）', 'warning':3000, 'alarm':3500, 'unit':'adc'},
]
RULE_KEYS = {r['key'] for r in RULES}


def policy():
    channels = []
    for binding in INVENTORY['bindings']:
        code = binding['assetCode']
        metrics = list(SPECS[code])
        oxygen = binding['physicalTag'].startswith('O2-')
        channels.append({'assetCode':code, 'physicalTag':binding['physicalTag'],
            'metrics':metrics, 'status':'blocked_calibration' if oxygen else 'threshold_configured',
            'ruleKeys':[] if oxygen else [m for m in metrics if m in RULE_KEYS],
            'reason':'未标定原始氧气信号；不推算氧浓度，不作缺氧或安全进入判断。' if oxygen else ''})
    return {'revision':'hardware-acceptance-alarms-20261029.1', 'scope':'isolated_hardware_commissioning',
        'rules':deepcopy(RULES), 'sensors':channels, 'registeredSensors':31,
        'thresholdCoveredSensors':28, 'calibrationBlockedSensors':3,
        'boundary':'验收暂定值，不是国标气体浓度阈值；坏质量、过期、单位错误的观测不能触发或解除阈值告警。'}
