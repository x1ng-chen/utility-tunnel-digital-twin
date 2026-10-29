from copy import deepcopy
from unittest.mock import patch

from django.test import SimpleTestCase

from .agent_branching import compare_scenarios, SOURCE


def snapshot():
    return {'sha256': 'same-evidence-hash', 'capturedAt': '2026-10-29T00:00:00Z',
            'source': {'mode': 'simulated_test', 'scenarioId': 'DIA-01'},
            'assets': {'FAN-01': {'readings': [{'metric_key': 'rotational.speed', 'value': 0}]}},
            'branchScenario': {'version': 'fan-response-demo-v1', 'windowSeconds': 60,
                'requiredFanCount': 1, 'runbookApproved': True,
                'fanModels': {fan: {'initialPower': False, 'initialPwm': 50,
                    'rpmAt50': 1200, 'powerWAt50': 3.6, 'fault': 'none'}
                    for fan in ('FAN-01', 'FAN-02')},
                'tariffs': [{'start': '2026-10-29T00:00:00Z', 'end': '2026-10-29T01:00:00Z', 'price': 1}]}}


class BranchComparisonTests(SimpleTestCase):
    def test_branches_are_deterministic_detached_and_do_not_mutate_snapshot(self):
        initial = snapshot()
        before = deepcopy(initial)
        first = compare_scenarios(initial)
        self.assertEqual(first, compare_scenarios(initial))
        self.assertEqual(initial, before)
        self.assertEqual(len(first['branches']), 3)
        self.assertEqual(len({branch['initialStateHash'] for branch in first['branches']}), 1)
        self.assertEqual({branch['snapshotHash'] for branch in first['branches']}, {'same-evidence-hash'})
        first['branches'][1]['outputs']['FAN-01']['rpm'] = 999
        self.assertEqual(first['branches'][2]['outputs']['FAN-01']['rpm'], 0)
        self.assertEqual(compare_scenarios(initial)['branches'][1]['outputs']['FAN-01']['rpm'], 1200)

    def test_real_history_and_unknown_sources_are_not_physical_predictors(self):
        for source in ({'mode': 'database_observation'}, {'mode': 'historical_replay'}, None):
            initial = snapshot()
            initial['source'] = source
            result = compare_scenarios(initial)
            self.assertEqual(result['status'], 'unsupported_source')
            self.assertEqual(result['branches'], [])
            self.assertFalse(result['comparison']['comparable'])

    def test_no_explicit_parameters_means_no_virtual_rpm_or_output(self):
        initial = snapshot()
        del initial['branchScenario']
        result = compare_scenarios(initial)
        self.assertEqual(result['status'], 'needs_parameters')
        for branch in result['branches']:
            self.assertIsNone(branch['energy'])
            for fan in branch['outputs'].values():
                self.assertIsNone(fan['rpm'])
                self.assertIsNone(fan['watts'])
                self.assertIsNone(fan['power'])

    def test_conflicting_valid_start_observations_prevent_ranking(self):
        initial = snapshot()
        row = initial['assets']['FAN-01']['readings'][0]
        row.update(value=1200, unit='rpm', quality='good', freshness='fresh', scenario_usable=True)
        result = compare_scenarios(initial)
        self.assertIn('FAN-01:model_start_conflicts_with_rotational.speed', result['missing'])
        self.assertFalse(any(branch['constraints']['eligibleForRanking'] for branch in result['branches']))
        self.assertEqual(initial['assets']['FAN-01']['readings'][0]['value'], 1200)
        self.assertFalse(result['comparison']['comparable'])

    def test_model_version_missing_does_not_emit_plausible_numbers(self):
        for version in (None, '', 123):
            initial = snapshot()
            initial['branchScenario']['version'] = version
            result = compare_scenarios(initial)
            self.assertEqual(result['status'], 'needs_parameters')
            self.assertTrue(all(fan['rpm'] is None for branch in result['branches'] for fan in branch['outputs'].values()))

    def test_matching_ack_is_separate_from_output_and_never_clears_alarm(self):
        initial = snapshot()
        initial['branchScenario']['fanModels']['FAN-01']['fault'] = 'output_mismatch'
        result = compare_scenarios(initial)
        fan01 = result['branches'][1]
        self.assertEqual(fan01['actions'][0]['state'], 'simulated_ack')
        self.assertEqual(fan01['outputs']['FAN-01']['rpm'], 0)
        self.assertFalse(fan01['constraints']['eligibleForRanking'])
        self.assertFalse(result['alertsResolved'])
        self.assertTrue(all(branch['environmentRecovery'] == 'unknown' and not branch['alertsResolved']
                            for branch in result['branches']))

    def test_rejected_timeout_and_unrelated_receipt_are_not_success(self):
        expected = {'command_rejected': 'simulated_rejected', 'command_timeout': 'simulated_timeout',
                    'wrong_ack': 'simulated_unmatched_receipt'}
        for fault, state in expected.items():
            initial = snapshot()
            initial['branchScenario']['fanModels']['FAN-01']['fault'] = fault
            result = compare_scenarios(initial)
            branch = result['branches'][1]
            self.assertEqual(branch['actions'][0]['state'], state)
            self.assertFalse(branch['constraints']['eligibleForRanking'])
            if fault == 'wrong_ack':
                action = branch['actions'][0]
                self.assertNotEqual(action['commandId'], action['receipt']['commandId'])
            self.assertFalse(branch['realCommandsSent'])

    def test_tach_missing_cannot_be_ranked_as_verified_fan_motion(self):
        initial = snapshot()
        initial['branchScenario']['fanModels']['FAN-01']['fault'] = 'tach_missing'
        branch = compare_scenarios(initial)['branches'][1]
        self.assertIsNone(branch['outputs']['FAN-01']['rpm'])
        self.assertIsNone(branch['constraints']['scenarioRequirementSatisfied'])
        self.assertFalse(branch['constraints']['eligibleForRanking'])

    def test_power_absence_remains_a_declared_fault_not_a_mechanical_root_cause(self):
        initial = snapshot()
        initial['branchScenario']['fanModels']['FAN-01']['fault'] = 'power_absent'
        branch = compare_scenarios(initial)['branches'][1]
        self.assertEqual(branch['outputs']['FAN-01']['rpm'], 0)
        self.assertFalse(branch['outputs']['FAN-01']['power'])
        self.assertFalse(branch['constraints']['eligibleForRanking'])

    def test_missing_power_and_price_are_unknown_not_zero_or_savings(self):
        initial = snapshot()
        del initial['branchScenario']['fanModels']['FAN-01']['powerWAt50']
        initial['branchScenario']['tariffs'] = []
        result = compare_scenarios(initial)
        branch = result['branches'][1]
        self.assertIsNone(branch['outputs']['FAN-01']['watts'])
        self.assertGreater(branch['energy']['unknownFanSeconds'], 0)
        self.assertIsNone(branch['energy']['electricityCost'])
        self.assertFalse(result['comparison']['actualSavingsProven'])

    def test_only_compliant_same_window_branches_can_be_compared(self):
        choices = [{'id': 'one', 'label': '风机1', 'actions': [{'assetCode': 'FAN-01', 'intent': 'power', 'value': 1}]},
                   {'id': 'two', 'label': '风机2', 'actions': [{'assetCode': 'FAN-02', 'intent': 'power', 'value': 1}]}]
        result = compare_scenarios(snapshot(), choices)
        self.assertTrue(result['comparison']['comparable'])
        self.assertTrue(all(branch['energy']['complete'] for branch in result['branches']))
        self.assertAlmostEqual(result['branches'][0]['energy']['knownKwh'], .00006)
        initial = snapshot()
        initial['branchScenario']['requiredFanCount'] = 2
        self.assertFalse(compare_scenarios(initial, choices)['comparison']['comparable'])
        initial = snapshot()
        initial['branchScenario']['runbookApproved'] = False
        self.assertFalse(compare_scenarios(initial, choices)['comparison']['comparable'])

    def test_candidates_are_explicit_bounded_and_whitelisted(self):
        invalid = [
            [{'id': 'x', 'label': '水泵', 'actions': [{'assetCode': 'PUMP-01', 'intent': 'power', 'value': 1}]}],
            [{'id': 'x', 'label': '关闭告警', 'actions': [{'assetCode': 'FAN-01', 'intent': 'clear_alert', 'value': 1}]}],
            [{'id': 'x', 'label': '布尔', 'actions': [{'assetCode': 'FAN-01', 'intent': 'power', 'value': True}]}],
            [{'id': 'x', 'label': 'PWM', 'actions': [{'assetCode': 'FAN-01', 'intent': 'pwm', 'value': 101}]}],
            [{'id': 'x', 'label': '执行', 'actions': [], 'execute': True}],
            [{'id': 'x', 'label': '重复', 'actions': []}] * 2,
        ]
        for choices in invalid:
            with self.subTest(choices=choices), self.assertRaises(ValueError):
                compare_scenarios(snapshot(), choices)

    def test_bad_parameters_and_incomplete_clocks_fail_explicitly(self):
        for key, value in [('windowSeconds', float('nan')), ('windowSeconds', 3601),
                           ('requiredFanCount', True), ('fanModels', {'PUMP-01': {}})]:
            initial = snapshot()
            initial['branchScenario'][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                compare_scenarios(initial)
        initial = snapshot()
        initial['capturedAt'] = '2026-10-29T00:00:00'
        with self.assertRaises(ValueError):
            compare_scenarios(initial)

    def test_never_writes_database_or_calls_external_services(self):
        with patch('operations.agent_branching.calculate', wraps=__import__('operations.sprint_costs', fromlist=['calculate']).calculate):
            result = compare_scenarios(snapshot())
        self.assertEqual(result['source'], SOURCE)
        self.assertFalse(result['realCommandsSent'])
        self.assertTrue(all(action['executedOnHardware'] is False for branch in result['branches'] for action in branch['actions']))
