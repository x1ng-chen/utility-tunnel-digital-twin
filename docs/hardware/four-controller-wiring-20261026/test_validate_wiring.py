"""Mutation checks for the source/pin boundary; these do not simulate hardware."""
from copy import deepcopy
import json
from pathlib import Path
import unittest

from validate_wiring import validate


class WiringValidationTests(unittest.TestCase):
    def setUp(self):
        self.plan = json.loads((Path(__file__).parent / 'wiring-plan.json').read_text(encoding='utf-8'))

    def sensor(self, tag):
        return next(s for s in self.plan['sensors'] if s['physicalTag'] == tag)

    def device(self, tag):
        return next(d for d in self.plan['devices'] if d['id'] == tag)

    def rejects(self):
        self.assertTrue(validate(self.plan)['errors'])

    def test_current_plan_passes_with_unverified_pa0_exception(self):
        result = validate(self.plan)
        self.assertFalse(result['errors'])
        self.assertEqual(result['static_resource_check'], 'PASS_WITH_DECLARED_PIN_EXCEPTION')
        self.assertFalse(result['hardware_verified'])

    def test_sensor_cannot_move_to_another_controller(self):
        self.sensor('MQ2-03')['node'] = 'CTRL-04'
        self.rejects()

    def test_duplicate_tag_is_rejected(self):
        self.plan['sensors'][1]['physicalTag'] = self.plan['sensors'][0]['physicalTag']
        self.rejects()

    def test_old_pin_cannot_silently_replace_current_source(self):
        self.sensor('MQ2-03')['pins'] = ['PC11']
        self.rejects()

    def test_adc_channel_must_match_selected_pin(self):
        self.sensor('CO-03')['adcChannel'] = 9
        self.rejects()

    def test_pa0_exception_is_not_global(self):
        self.sensor('O2-03')['pins'] = ['PA0']
        self.sensor('O2-03')['adcChannel'] = 0
        self.rejects()

    def test_removing_exception_does_not_hide_reserved_pin(self):
        self.plan['reservedPinExceptions'] = []
        self.rejects()

    def test_declared_hardware_verified_exception_is_rejected(self):
        self.plan['reservedPinExceptions'][0]['hardwareVerified'] = True
        self.rejects()

    def test_fan2_must_use_tim3_ch4(self):
        self.device('FAN-02')['signals'][0].update(pin='PB8', mode='TIM4_CH3')
        self.rejects()

    def test_screen_pin_collision_is_rejected(self):
        self.device('SCREEN-MAIN')['signals'][-1]['pin'] = 'PB8'
        self.rejects()

    def test_historical_evidence_cannot_be_rewritten(self):
        self.sensor('MQ2-03')['previousPlan']['pins'] = ['PC4']
        self.rejects()

    def test_source_hash_drift_is_rejected(self):
        self.plan['pinSource']['sha256'] = '0' * 64
        self.rejects()

    def test_i2c_address_collision_is_rejected(self):
        self.plan['buses'][0]['devices'].append(deepcopy(self.plan['buses'][0]['devices'][0]))
        self.rejects()

    def test_oxygen_quality_cannot_become_calibrated(self):
        self.sensor('O2-02')['quality'] = 'CALIBRATED'
        self.rejects()


if __name__ == '__main__':
    unittest.main()
