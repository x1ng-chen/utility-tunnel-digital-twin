from copy import deepcopy
import json
from pathlib import Path

from django.test import SimpleTestCase

from .agent_topology import build_topology, query_topology, BUS_ID, GATEWAY_ID, SOURCE


class TopologyTests(SimpleTestCase):
    def setUp(self):
        catalog = Path(__file__).parent / 'agent_catalog'
        self.inventory = json.loads((catalog / 'station-inventory.json').read_text(encoding='utf-8'))
        self.presentation = json.loads((catalog / 'model-v20-presentation.json').read_text(encoding='utf-8'))

    def freeze(self, inventory=None):
        return {'sha256': 'observation-hash', 'topologyContext': build_topology(inventory or self.inventory)}

    def test_complete_physical_identity_and_owner_counts(self):
        graph = build_topology(self.inventory)
        sensors = [item for item in graph['nodes'] if item['kind'] == 'sensor']
        self.assertEqual(len(sensors), 31)
        self.assertEqual(len({item['physicalTag'] for item in sensors}), 31)
        self.assertEqual(graph['counts']['allocation'], {'CTRL-01': 11, 'CTRL-02': 7, 'CTRL-03': 6, 'CTRL-04': 7})
        self.assertEqual(graph['source'], SOURCE)
        self.assertFalse(any(item['stationId'] == 'P5' and item['physicalTag'].startswith('SHT') for item in sensors))

    def test_central_telemetry_path_is_configured_not_live_measurement(self):
        result = query_topology(self.freeze(), 'MQ4-05')
        ids = {item['id'] for item in result['nodes']}
        self.assertEqual(ids, {'MQ4-05', 'CTRL-01', BUS_ID, GATEWAY_ID})
        self.assertTrue(all(edge['source'] == SOURCE and not edge['verified'] for edge in result['edges']))
        self.assertEqual(result['snapshotHash'], 'observation-hash')

    def test_controller_impact_keeps_all_children_and_correct_fan(self):
        result = query_topology(self.freeze(), 'CTRL-04', 'impact')
        ids = {item['id'] for item in result['nodes']}
        self.assertIn('FAN-01', ids)
        self.assertNotIn('FAN-02', ids)
        self.assertEqual(sum(item['kind'] == 'sensor' for item in result['nodes']), 7)

    def test_gateway_impact_reaches_all_controllers_and_sensors(self):
        result = query_topology(self.freeze(), GATEWAY_ID, 'impact')
        self.assertEqual(sum(item['kind'] == 'controller' for item in result['nodes']), 4)
        self.assertEqual(sum(item['kind'] == 'sensor' for item in result['nodes']), 31)

    def test_feedback_contract_does_not_claim_acquired_rpm_or_ina(self):
        result = query_topology(self.freeze(), 'FAN-01')
        feedback = [item for item in result['nodes'] if item['kind'] == 'feedback_channel']
        self.assertEqual({item['metricKey'] for item in feedback}, {'rotational.speed', 'motor.current', 'supply.voltage'})
        self.assertTrue(all(item['observationVerified'] is False for item in feedback))
        self.assertTrue(all('value' not in item for item in feedback))

    def test_verified_mesh_requires_actual_inspection_and_identity_match(self):
        first = self.inventory['bindings'][0]
        good = {**first, 'current_mesh': first['targetNode'], 'registry_present': True,
                'mapping_status': 'active_model_node_verified'}
        graph = build_topology(self.inventory, bindings=[good])
        mapped = [edge for edge in graph['edges'] if edge['from'] == first['assetCode'] and edge['kind'] == 'mapped_to']
        self.assertEqual(len(mapped), 1)
        self.assertTrue(mapped[0]['verified'])
        bad = {**good, 'controllerId': 'CTRL-01'}
        graph = build_topology(self.inventory, bindings=[bad])
        self.assertFalse(any(edge['from'] == first['assetCode'] and edge['kind'] == 'mapped_to' for edge in graph['edges']))
        self.assertTrue(any(item['reason'] == 'binding_identity_conflict' for item in graph['missing']))

    def test_missing_mesh_does_not_become_located_success(self):
        item = {**self.inventory['bindings'][0], 'current_mesh': '', 'registry_present': True,
                'mapping_status': 'mesh_missing'}
        graph = build_topology(self.inventory, bindings=[item])
        self.assertFalse(any(edge['kind'] == 'mapped_to' for edge in graph['edges']))
        self.assertIn({'target': item['assetCode'], 'reason': 'mesh_missing'}, graph['missing'])

    def test_presentation_changes_station_not_wire_owner(self):
        original = deepcopy(self.inventory)
        graph = build_topology(self.inventory, self.presentation)
        sensor = next(item for item in graph['nodes'] if item['id'] == 'SMOKE-01')
        self.assertEqual(sensor['stationId'], 'P3')
        self.assertEqual(sensor['controllerId'], 'CTRL-04')
        self.assertEqual(graph['layoutVersion'], self.inventory['revision'])
        self.assertEqual(graph['presentationVersion'], self.presentation['revision'])
        self.assertEqual(self.inventory, original)

    def test_frozen_graph_is_not_replaced_by_changed_configuration(self):
        frozen = self.freeze()
        self.inventory['bindings'][0]['controllerId'] = 'CTRL-01'
        query = query_topology(frozen, 'SMOKE-01')
        self.assertIn('CTRL-04', {item['id'] for item in query['nodes']})
        self.assertNotIn('CTRL-01', {item['id'] for item in query['nodes']})
        query['nodes'][0]['id'] = 'mutated'
        self.assertNotIn('mutated', {item['id'] for item in frozen['topologyContext']['nodes']})

    def test_unrecorded_and_unknown_targets_remain_unknown(self):
        self.assertEqual(query_topology({}, 'FAN-01')['status'], 'unknown')
        self.assertEqual(query_topology(self.freeze(), 'P99')['status'], 'unknown')
        self.assertEqual(query_topology(self.freeze(), 'MQ2-01')['target'], 'SMOKE-01')

    def test_neighbors_are_explicitly_topological_not_spatial_or_pipe(self):
        result = query_topology(self.freeze(), 'MQ4-05', 'neighbors')
        self.assertIn('不表示物理距离', result['neighborMeaning'])
        self.assertIn('MQ4-03', {item['id'] for item in result['nodes']})
        self.assertNotIn('FLAME-04', {item['id'] for item in result['nodes']})

    def test_validation_and_stable_versioned_hash(self):
        first = build_topology(self.inventory)
        self.assertEqual(first, build_topology(self.inventory))
        invalid = deepcopy(self.inventory)
        invalid['bindings'].append(invalid['bindings'][0])
        with self.assertRaises(ValueError):
            build_topology(invalid)
        with self.assertRaises(ValueError):
            build_topology(self.inventory, {**self.presentation, 'wireLayoutVersion': 'old'})
        with self.assertRaises(ValueError):
            query_topology(self.freeze(), 'P1', 'execute')
