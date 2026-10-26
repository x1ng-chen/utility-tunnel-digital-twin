"""Versioned ownership of physical outputs; the Agent has no dispatch tool."""
from django.conf import settings
from django.utils import timezone

LEGACY_ACTIONS = {'led_red', 'led_green', 'led_blue', 'led_off', 'relay_on', 'relay_off', 'fan_pwm', 'fan2_pwm'}
FOUR_PROTOCOL = 'four-controller-v2'
FOUR_ACTIONS = {
    'CTRL-01': set(),
    'CTRL-02': {'fan2_pwm', 'relay_on', 'relay_off', 'auto'},
    'CTRL-03': {'led_red', 'led_green', 'led_blue', 'led_off', 'buzzer_on', 'buzzer_off', 'auto'},
    'CTRL-04': {'fan_pwm', 'relay_on', 'relay_off', 'auto'},
}


def four_controller_enabled():
    return settings.CONTROLLER_COMMAND_PROTOCOL == FOUR_PROTOCOL


def allowed_target(controller_id, action):
    if not isinstance(action, str) or not isinstance(controller_id, str):
        return False
    return action in FOUR_ACTIONS.get(controller_id, set()) if four_controller_enabled() else controller_id == 'CTRL-01' and action in LEGACY_ACTIONS


def build_command(controller_id, action, duty_percent, command_id):
    if not allowed_target(controller_id, action):
        raise ValueError('Action does not belong to this controller.')
    if action in {'fan_pwm', 'fan2_pwm'} and (isinstance(duty_percent, bool) or not isinstance(duty_percent, int) or not 0 <= duty_percent <= 100):
        raise ValueError('PWM duty must be an integer from 0 to 100.')
    if not four_controller_enabled():
        result = {'schema': 'ut.command.v1', 'cmdId': command_id, 'action': action, 'ttlMs': 10000}
        if action in {'fan_pwm', 'fan2_pwm'}:
            result['dutyPercent'] = duty_percent
        return result
    if action in {'fan_pwm', 'fan2_pwm'}:
        command, value = 'fan', duty_percent
    elif action.startswith('relay_'):
        command, value = 'relay', int(action == 'relay_on')
    elif action.startswith('buzzer_'):
        command, value = 'buzzer', int(action == 'buzzer_on')
    elif action == 'auto':
        command, value = 'auto', 0
    else:
        command, value = 'led', {'led_off': 0, 'led_red': 1, 'led_green': 3, 'led_blue': 4}[action]
    return {'schema': 'ut.command.v2', 'cmdId': command_id, 'controllerId': controller_id,
            'command': command, 'value': value, 'issuedAtMs': int(timezone.now().timestamp() * 1000),
            'ttlMs': 10000}
