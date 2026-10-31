"""Pure, bounded fan scenario branches over an immutable evidence snapshot.

This module deliberately imports neither Django nor a publisher. Its model
parameters are explicit server-frozen assumptions, not fitted physics. Even a
simulated matching receipt cannot clear an alert or establish real recovery.
"""
from copy import deepcopy
from datetime import datetime, timedelta
import hashlib
import json
import math

from .sprint_costs import calculate


VERSION = 'fan-branch-comparison-20261029.1'
SOURCE = 'SIMULATED_BRANCH'
FANS = ('FAN-01', 'FAN-02')
FAULTS = {'none', 'power_absent', 'tach_missing', 'command_rejected',
          'command_timeout', 'wrong_ack', 'output_mismatch'}
BOUNDARY = ('分支为显式假设下的场景模拟，不是MQTT/RS-485或实物执行。'
            '没有经验证的通风响应模型，不预测浓度、现场安全或告警恢复；回执不能解除告警。')


def _hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def _number(value, name, low=0, high=None):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(name + '必须为有限数值。')
    if value < low or high is not None and value > high:
        raise ValueError(name + '超出允许范围。')
    return value


def _timestamp(value):
    if not isinstance(value, str):
        raise ValueError('分支起点需要冻结快照的带时区采集时间。')
    try:
        result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError as exc:
        raise ValueError('分支采集时间无效。') from exc
    if result.tzinfo is None:
        raise ValueError('分支采集时间需要时区。')
    return result


def _candidates(candidates):
    if candidates is None:
        candidates = [
            {'id': 'observe', 'label': '先补充独立证据', 'actions': []},
            {'id': 'fan01', 'label': '模拟风机1供电与50% PWM',
             'actions': [{'assetCode': 'FAN-01', 'intent': 'power', 'value': 1}, {'assetCode': 'FAN-01', 'intent': 'pwm', 'value': 50}]},
            {'id': 'fan02', 'label': '模拟风机2供电与50% PWM',
             'actions': [{'assetCode': 'FAN-02', 'intent': 'power', 'value': 1}, {'assetCode': 'FAN-02', 'intent': 'pwm', 'value': 50}]},
        ]
    if not isinstance(candidates, list) or not 1 <= len(candidates) <= 3:
        raise ValueError('一次只能比较1至3个独立分支。')
    ids, result = set(), []
    for candidate in candidates:
        if not isinstance(candidate, dict) or set(candidate) - {'id', 'label', 'actions'}:
            raise ValueError('分支只接受id、label和actions。')
        identity, label = candidate.get('id'), candidate.get('label')
        if (not isinstance(identity, str) or not 1 <= len(identity) <= 40 or identity in ids
                or not isinstance(label, str) or not 1 <= len(label) <= 100):
            raise ValueError('分支需要不重复的编号和简短名称。')
        ids.add(identity)
        actions = candidate.get('actions', [])
        if not isinstance(actions, list) or len(actions) > 4:
            raise ValueError('分支最多包含4个模拟设置。')
        settings = set()
        for action in actions:
            if not isinstance(action, dict) or set(action) != {'assetCode', 'intent', 'value'}:
                raise ValueError('仅接受明确目标、类型和值的模拟设置。')
            asset, intent, value = action['assetCode'], action['intent'], action['value']
            if asset not in FANS or intent not in {'power', 'pwm'} or type(value) is not int:
                raise ValueError('只允许双风机power或pwm设置。')
            if not 0 <= value <= (1 if intent == 'power' else 100) or (asset, intent) in settings:
                raise ValueError('模拟设置超界或同一分支含冲突设置。')
            settings.add((asset, intent))
        result.append({'id': identity, 'label': label, 'actions': deepcopy(actions)})
    return result


def _model(parameters, fan, missing):
    value = parameters.get('fanModels', {}).get(fan)
    if not isinstance(value, dict):
        missing.append(fan + ':explicit_fan_model_missing')
        return None
    allowed = {'initialPower', 'initialPwm', 'rpmAt50', 'powerWAt50', 'fault'}
    if set(value) - allowed:
        raise ValueError('未知模拟风机参数。')
    if type(value.get('initialPower')) is not bool:
        missing.append(fan + ':initial_power_missing')
        return None
    if value.get('initialPwm') is None:
        missing.append(fan + ':initial_pwm_missing')
        return None
    _number(value['initialPwm'], 'initialPwm', 0, 100)
    fault = value.get('fault', 'none')
    if fault not in FAULTS:
        raise ValueError('未知模拟故障。')
    for field in ('rpmAt50', 'powerWAt50'):
        if value.get(field) is not None:
            _number(value[field], field)
        else:
            missing.append(fan + ':' + field + '_missing')
    return {**value, 'fault': fault}


def _outputs(state):
    """Evaluate explicitly supplied response parameters only."""
    if state is None:
        return {'power': None, 'pwm': None, 'rpm': None, 'watts': None,
                'verification': 'explicit_model_missing'}
    power, pwm, fault = state['initialPower'], state['initialPwm'], state['fault']
    if fault == 'power_absent':
        # Zero supply is a scenario assumption, never a reading inferred from RPM.
        return {'power': False, 'pwm': pwm, 'rpm': 0 if state.get('rpmAt50') is not None else None,
                'watts': 0 if state.get('powerWAt50') is not None else None,
                'verification': 'simulated_power_absent'}
    ratio = pwm / 50 if power else 0
    rpm = state.get('rpmAt50')
    watts = state.get('powerWAt50')
    return {'power': power, 'pwm': pwm,
            'rpm': None if fault == 'tach_missing' or rpm is None else rpm * ratio,
            'watts': None if watts is None else watts * ratio,
            'verification': 'simulated_output_only'}


def _start_conflicts(snapshot, initial):
    """Do not rank a branch model whose starting values contradict valid data."""
    conflicts, observations = [], {}
    for fan in FANS:
        observations[fan] = []
        for row in snapshot.get('assets', {}).get(fan, {}).get('readings', []):
            if (not isinstance(row, dict) or row.get('scenario_usable') is not True
                    or row.get('quality') != 'good' or row.get('freshness') != 'fresh'):
                continue
            metric, unit, value = row.get('metric_key'), row.get('unit'), row.get('value')
            output_key = {'rotational.speed': 'rpm', 'power': 'watts'}.get(metric)
            if output_key is None or unit not in {'rpm', 'W', 'mW'}:
                continue
            if metric == 'rotational.speed' and unit != 'rpm' or metric == 'power' and unit not in {'W', 'mW'}:
                continue
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
                continue
            normalized = value / 1000 if unit == 'mW' else value
            observations[fan].append({'id': row.get('id'), 'metricKey': metric, 'value': value,
                                      'unit': unit, 'sampledAt': row.get('sampled_at')})
            modeled = _outputs(initial[fan])[output_key]
            if modeled is not None and not math.isclose(modeled, normalized, rel_tol=1e-6, abs_tol=1e-9):
                conflicts.append(fan + ':model_start_conflicts_with_' + metric)
    return conflicts, observations


def compare_scenarios(snapshot, candidates=None):
    """Return detached branches; callers must freeze any branchScenario config.

    branchScenario is server-owned, optional explicit input:
      {version, windowSeconds, fanModels: {FAN-01: {initialPower, initialPwm,
       rpmAt50, powerWAt50, fault}, ...}, requiredFanCount, runbookApproved,
       tariffs: [{start,end,price}]}
    Missing parameters stay unknown; they are not filled with generic motor or
    ventilation values. User/API input must never be copied into that config.
    """
    if not isinstance(snapshot, dict):
        raise ValueError('需要冻结证据快照。')
    candidates = _candidates(candidates)
    source = snapshot.get('source')
    simulated = (isinstance(source, dict) and source.get('mode') == 'simulated_test') or source == 'SIMULATED_TEST'
    origin_hash = snapshot.get('sha256') or _hash(snapshot)
    result = {'source': SOURCE, 'sourceContext': deepcopy(source), 'status': 'needs_parameters',
              'snapshotHash': origin_hash, 'modelVersion': VERSION, 'window': None,
              'assumptions': [], 'missing': [], 'branches': [],
              'comparison': {'comparable': False, 'reason': '缺少明确的模拟参数或适用规程条件。'},
              'realCommandsSent': False, 'alertsResolved': False, 'boundary': BOUNDARY}
    if not simulated:
        result.update(status='unsupported_source', missing=['isolated_simulated_source_required'])
        result['comparison']['reason'] = '现场或历史观测未经过通风模型验证，不能据此推演现场处置效果。'
        return result
    parameters = deepcopy(snapshot.get('branchScenario') or {})
    if not isinstance(parameters, dict):
        raise ValueError('branchScenario需要服务器冻结的参数对象。')
    if set(parameters) - {'version', 'windowSeconds', 'fanModels', 'requiredFanCount', 'runbookApproved', 'tariffs', 'assumptions'}:
        raise ValueError('未知分支模型参数。')
    if parameters.get('fanModels') is not None and (not isinstance(parameters['fanModels'], dict)
            or set(parameters['fanModels']) - set(FANS)):
        raise ValueError('模拟模型只允许双风机。')
    window_seconds = parameters.get('windowSeconds')
    if window_seconds is None:
        result['missing'].append('explicit_window_seconds_missing')
    else:
        _number(window_seconds, 'windowSeconds', 1, 3600)
        start = _timestamp(snapshot.get('capturedAt'))
        end = start + timedelta(seconds=window_seconds)
        result['window'] = {'start': start.isoformat(), 'end': end.isoformat(), 'seconds': window_seconds}
    version_valid = isinstance(parameters.get('version'), str) and bool(parameters['version'])
    if not version_valid:
        result['missing'].append('explicit_model_version_missing')
    else:
        result['responseModelVersion'] = parameters['version']
    model_missing = []
    initial = {fan: _model(parameters, fan, model_missing) for fan in FANS}
    result['missing'].extend(model_missing)
    start_conflicts, initial_observations = _start_conflicts(snapshot, initial)
    result['missing'].extend(start_conflicts)
    required = parameters.get('requiredFanCount')
    if required is not None and (type(required) is not int or not 0 <= required <= 2):
        raise ValueError('requiredFanCount只能为0至2。')
    approved = parameters.get('runbookApproved') is True
    if required is None:
        result['missing'].append('scenario_ventilation_requirement_missing')
    if not approved:
        result['missing'].append('scenario_runbook_conditions_not_approved')
    result['assumptions'] = [
        {'kind': 'EXPLICIT_SCENARIO_PARAMETERS', 'parameters': deepcopy(parameters)},
        {'kind': 'CONSTANT_WINDOW', 'description': '本窗口内模型参数恒定，不包含启动瞬态或真实风道响应。'},
        {'kind': 'RESPONSE_FORMULA', 'description': '仅当提供参数时，RPM和支路功率按pwm/50线性缩放；这是教学场景假设，不是实测风机规律。'},
    ]
    for candidate in candidates:
        state = deepcopy(initial)
        branch = {**candidate, 'source': SOURCE, 'actions': [], 'outputs': {},
                  'constraints': {}, 'energy': None, 'limitations': [],
                  'initialStateHash': _hash(initial), 'snapshotHash': origin_hash,
                  'initialObservations': deepcopy(initial_observations),
                  'modelVersion': parameters.get('version'), 'environmentRecovery': 'unknown',
                  'alertsResolved': False, 'realCommandsSent': False}
        reliable = True
        for action in candidate['actions']:
            fan = action['assetCode']
            fan_state = state[fan]
            command_id = 'branch-' + _hash([origin_hash, candidate['id'], action])[:24]
            event = {**action, 'commandId': command_id, 'state': 'simulated_proposal',
                     'receipt': None, 'executedOnHardware': False}
            fault = (fan_state or {}).get('fault')
            if fan_state is None or not version_valid:
                event['state'] = 'not_modeled'
                branch['limitations'].append(fan + ':没有明确响应模型，动作效果未知。')
                reliable = False
            elif fault == 'command_rejected':
                event.update(state='simulated_rejected', receipt={'commandId': command_id, 'accepted': False})
                reliable = False
            elif fault == 'command_timeout':
                event['state'] = 'simulated_timeout'
                branch['limitations'].append(fan + ':模拟超时后输出是否改变未知。')
                state[fan] = None
                reliable = False
            elif fault == 'wrong_ack':
                event.update(state='simulated_unmatched_receipt',
                             receipt={'commandId': command_id + '-unrelated', 'accepted': True})
                state[fan] = None
                reliable = False
            else:
                event.update(state='simulated_ack', receipt={'commandId': command_id, 'accepted': True})
                if fault != 'output_mismatch':
                    field = 'initialPower' if action['intent'] == 'power' else 'initialPwm'
                    fan_state[field] = bool(action['value']) if action['intent'] == 'power' else action['value']
                else:
                    branch['limitations'].append(fan + ':模拟回执与输出不一致，回执不证明输出动作。')
                    reliable = False
            branch['actions'].append(event)
        branch['outputs'] = {fan: _outputs(state[fan]) for fan in FANS}
        # A missing declared model version cannot authorize numeric prediction.
        if not version_valid:
            branch['outputs'] = {fan: _outputs(None) for fan in FANS}
        rpms = [output['rpm'] for output in branch['outputs'].values()]
        running = sum(rpm > 0 for rpm in rpms if rpm is not None)
        feedback_known = all(rpm is not None for rpm in rpms)
        satisfied = running >= required if required is not None and feedback_known and reliable else None
        compliant = approved and satisfied is True and not start_conflicts
        branch['constraints'] = {'requiredFanCount': required, 'modeledRunningFanCount': running if feedback_known else None,
                                 'scenarioRequirementSatisfied': satisfied, 'runbookApproved': approved,
                                 'eligibleForRanking': compliant, 'hardwareExecutionAuthorized': False}
        if result['window'] and version_valid:
            readings = []
            for fan, output in branch['outputs'].items():
                if output['watts'] is not None:
                    readings.append({'assetCode': fan, 'at': result['window']['start'],
                                     'power': output['watts'], 'unit': 'W', 'quality': 'good',
                                     'rpm': output['rpm']})
            branch['energy'] = calculate({'start': result['window']['start'], 'end': result['window']['end'],
                                         'maxGapSeconds': window_seconds, 'source': SOURCE,
                                         'readings': readings, 'tariffs': parameters.get('tariffs', []),
                                         'sameWindowAndRequirements': True, 'strategyCompliant': compliant})
        branch['limitations'].extend(['无经过验证的浓度或环境恢复模型。', '只表示模拟输出，不计为真机执行或人员安全结论。'])
        result['branches'].append(branch)
    comparable = bool(result['branches']) and not result['missing'] and all(
        branch['constraints']['eligibleForRanking'] and branch['energy'] and branch['energy']['complete']
        for branch in result['branches'])
    result['comparison'] = {'comparable': comparable,
                            'reason': '相同窗口、明确场景条件和完整模拟电价下可比较。' if comparable
                            else '缺少完整参数、电价、独立反馈，或有分支不满足场景条件；不进行节能排名。',
                            'eligibleBranchIds': [branch['id'] for branch in result['branches']
                                                  if branch['constraints']['eligibleForRanking']],
                            'actualSavingsProven': False}
    result['status'] = 'modeled' if not result['missing'] else 'needs_parameters'
    result['comparisonHash'] = _hash(result)
    return result
