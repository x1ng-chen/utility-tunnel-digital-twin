"""Deterministic scenario accounting, never a controller or lifetime predictor."""
import math
from datetime import datetime, timedelta, timezone


def number(v, name, minimum=0):
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or v < minimum:
        raise ValueError(f'{name} must be finite and >= {minimum}.')
    return float(v)


def timestamp(v):
    if not isinstance(v, str): raise ValueError('ISO timestamp required.')
    t = datetime.fromisoformat(v.replace('Z', '+00:00'))
    if not t.tzinfo: raise ValueError('Timezone required.')
    return t.astimezone(timezone.utc)


def calculate(payload):
    """Left-hand power integration, bounded gaps, exact tariff-boundary splits."""
    if not isinstance(payload, dict): raise ValueError('JSON object required.')
    start, end = timestamp(payload.get('start')), timestamp(payload.get('end'))
    seconds = (end-start).total_seconds()
    if not 0 < seconds <= 7*86400: raise ValueError('Window must be >0 and <=7 days.')
    readings, tariffs = payload.get('readings', []), payload.get('tariffs', [])
    if not isinstance(readings, list) or len(readings) > 10000: raise ValueError('At most 10000 readings.')
    if not isinstance(tariffs, list) or len(tariffs) > 100: raise ValueError('At most 100 tariff periods.')
    if any(not isinstance(r,dict) or r.get('assetCode') not in ('FAN-01','FAN-02') for r in readings):
        raise ValueError('Readings require two-fan asset objects.')
    if any(not isinstance(p,dict) for p in tariffs): raise ValueError('Tariff objects required.')
    for field in ('labor','roi'):
        if payload.get(field) is not None and not isinstance(payload[field],dict): raise ValueError(field+' object required.')
    periods = sorted([(timestamp(p['start']), timestamp(p['end']), number(p['price'], 'price')) for p in tariffs])
    if any(a >= b for a,b,_ in periods) or any(periods[i][1] > periods[i+1][0] for i in range(len(periods)-1)):
        raise ValueError('Tariff periods must be nonoverlapping, increasing.')
    max_gap = number(payload.get('maxGapSeconds', 10), 'maxGapSeconds', 1)
    if max_gap > 3600: raise ValueError('Max gap <=3600 seconds.')
    totals = {'knownKwh': 0., 'knownElectricityCost': 0., 'coveredFanSeconds': 0.,
              'unpricedKwh': 0., 'runtimeSeconds': 0., 'unknownRpmSeconds': 0., 'startsObserved': 0}
    for code in ('FAN-01', 'FAN-02'):
        rows = [r for r in readings if r.get('assetCode') == code]
        rows.sort(key=lambda r: timestamp(r['at']))
        times = [timestamp(r['at']) for r in rows]
        if len(times) != len(set(times)): raise ValueError('Conflicting/duplicate sample time.')
        previous_running = None
        for i, r in enumerate(rows):
            at = times[i]
            stop = min(end, times[i+1] if i+1 < len(rows) else end, at+timedelta(seconds=max_gap))
            begin = max(start, at)
            if stop <= begin: continue
            dt = (stop-begin).total_seconds()
            if r.get('quality') != 'good' or r.get('unit') not in {'W', 'mW'}:
                previous_running = None
                continue
            watts = number(r['power'], 'power') / (1000 if r['unit'] == 'mW' else 1)
            kwh = watts*dt/3600000
            totals['knownKwh'] += kwh
            totals['coveredFanSeconds'] += dt
            priced = 0.
            for ta,tb,price in periods:
                overlap = max(0., (min(stop,tb)-max(begin,ta)).total_seconds())
                priced += overlap
                totals['knownElectricityCost'] += watts*overlap/3600000*price
            totals['unpricedKwh'] += watts*(dt-priced)/3600000
            rpm = r.get('rpm')
            if rpm is None or r.get('rpmQuality', 'good') != 'good':
                totals['unknownRpmSeconds'] += dt
                previous_running = None
            else:
                running = number(rpm, 'rpm') > 0
                totals['runtimeSeconds'] += dt if running else 0
                if previous_running is False and running: totals['startsObserved'] += 1
                previous_running = running if i+1 < len(rows) and (times[i+1]-at).total_seconds() <= max_gap else None
    labor = payload.get('labor')
    labor_cost = None if labor is None else number(labor['seconds'], 'labor.seconds')/3600*number(labor['hourlyRate'], 'hourlyRate')
    model_cost = payload.get('modelCost')
    if model_cost is not None: model_cost = number(model_cost, 'modelCost')
    unknown = max(0, seconds*2-totals['coveredFanSeconds'])
    complete = unknown < 1e-6 and totals['unpricedKwh'] < 1e-12 and bool(periods)
    result = {**totals, 'unknownFanSeconds': unknown, 'windowSeconds': seconds,
        'scope': 'two_fan_branches_only', 'source': payload.get('source', 'ASSUMPTION'),
        'electricityCost': totals['knownElectricityCost'] if complete else None,
        'laborEquivalentCost': labor_cost, 'modelCost': model_cost,
        'complete': complete, 'currency': 'CNY', 'actualSavingsProven': False,
        'boundary': '双风机支路，不含MQ加热等全系统负载；工时当量不是实际减薪；不预测寿命或事故损失。'}
    baseline = payload.get('baselineCost')
    if baseline is not None:
        baseline = number(baseline, 'baselineCost')
        comparable = complete and payload.get('sameWindowAndRequirements') is True and payload.get('strategyCompliant') is True
        result['comparison'] = {'comparable': comparable, 'scenarioSavings': baseline-totals['knownElectricityCost'] if comparable else None}
    roi = payload.get('roi')
    if roi:
        investment = number(roi['investment'], 'investment', .000001)
        annual = number(roi['annualBenefit'], 'annualBenefit')-number(roi['annualOperatingCost'], 'annualOperatingCost')
        result['roi'] = {'scenarioOnly': True, 'annualNetBenefit': annual,
            'simpleAnnualRoi': annual/investment, 'paybackYears': investment/annual if annual > 0 else None,
            'sensitivityNetBenefits': [annual*x for x in (.5,1,1.5)]}
    return result


def example():
    return {'start':'2026-10-27T00:00:00Z','end':'2026-10-27T00:01:00Z','source':'SIMULATED_TEST',
        'maxGapSeconds':60,'readings':[{'assetCode':c,'at':'2026-10-27T00:00:00Z','power':3.6,'unit':'W',
          'quality':'good','rpm':1200} for c in ('FAN-01','FAN-02')],
        'tariffs':[{'start':'2026-10-27T00:00:00Z','end':'2026-10-28T00:00:00Z','price':1}],
        'labor':{'seconds':60,'hourlyRate':30},'modelCost':None}
