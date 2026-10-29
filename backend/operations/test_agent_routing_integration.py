"""Model stubs validate execution boundaries; they are not real-model scores."""
from unittest.mock import patch
import uuid
from django.test import TestCase, override_settings
from django.core.cache import cache
from rest_framework.test import APIClient
from . import test_software_sprint as fixtures
from .sprint_agents import process_one, freeze
from .sprint_models import AgentRun
from .sprint_validation import validate_facts


def decision(state, options, timeout=5):
    return {'status':'selected','selectedOption':options[0]['id'],'attempted':True,
        'model':'EXPLICIT_ROUTER_STUB','modelRevision':'test-only','usage':None,
        'runtime':{'elapsedMs':1},'probabilities':{},'fallbackReason':None}


@override_settings(DEEPSEEK_API_KEY='EXPLICIT_TEST_STUB',ANYJEV_ENABLED=True,
    ALLOWED_HOSTS=['testserver','127.0.0.1'],CONTROLLER_COMMAND_PROTOCOL='four-controller-v2')
class RoutingIntegrationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        fixtures.RunTests.setUpTestData.__func__(cls)

    def setUp(self):
        cache.clear()
        self.client=APIClient();self.client.force_authenticate(self.user)

    def run_task(self):
        response=self.client.post('/api/assistant/runs/',{'kind':'diagnosis','station_id':'P5'},format='json',
            HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()))
        self.assertEqual(response.status_code,202,response.data)
        process_one()
        return AgentRun.objects.get(pk=response.data['id'])

    @patch('operations.ai_assistant._completion',side_effect=fixtures.completion)
    @patch('operations.decision_router.route_decision',side_effect=decision)
    def test_selected_checks_are_executed_journaled_and_share_budget(self,router,model):
        run=self.run_task()
        self.assertEqual(run.status,'completed',run.error)
        traces=run.result['decisionTrace']
        self.assertEqual(len(traces),3)
        self.assertEqual(run.runtime['modelCalls'],router.call_count+model.call_count)
        self.assertLessEqual(run.runtime['toolCalls'],12)
        self.assertFalse(run.runtime['tokenUsageComplete'])
        self.assertIsNone(run.runtime['cost'])
        ids={e['id'] for e in run.result['evidence'] if e['status']=='ok'}
        self.assertTrue(all(t['executedEvidenceId'] in ids for t in traces))
        self.assertEqual(run.steps[0]['decisions'],traces)
        self.assertEqual(len({t['selectedOption'] for t in traces}),3)
        self.assertFalse(run.result['controlProposals'])

    @patch('operations.ai_assistant._completion',side_effect=fixtures.completion)
    @patch('operations.decision_router.route_decision',return_value={'status':'fallback','attempted':True,
        'model':'TEST_STUB','usage':None,'fallbackReason':'timeout','runtime':{}})
    def test_timeout_falls_back_once_and_is_not_free_or_hidden(self,router,model):
        run=self.run_task()
        self.assertEqual(run.status,'completed',run.error)
        self.assertEqual(router.call_count,1)
        self.assertEqual(run.runtime['modelCalls'],model.call_count+1)
        self.assertEqual(run.result['decisionTrace'][0]['fallbackReason'],'timeout')
        self.assertTrue(any(e['tool']=='collect_station_evidence' for e in run.result['evidence']))

    @patch('operations.ai_assistant._completion',side_effect=fixtures.completion)
    @patch('operations.decision_router.route_decision',return_value={'status':'selected','selectedOption':'propose_control',
        'attempted':True,'model':'TEST_STUB','usage':None,'runtime':{}})
    def test_router_cannot_invent_tools_or_authorize_an_action(self,router,model):
        run=self.run_task()
        self.assertEqual(run.status,'completed',run.error)
        self.assertEqual(run.result['decisionTrace'][0]['status'],'fallback')
        self.assertFalse(run.result['controlProposals'])
        self.assertFalse(any(e.get('origin')=='ANYJEV_READ_ONLY_ROUTING' for e in run.result['evidence']))

    @override_settings(ANYJEV_ENABLED=False)
    @patch('operations.ai_assistant._completion',side_effect=fixtures.completion)
    @patch('operations.decision_router.route_decision')
    def test_disabled_router_never_loads_or_calls_local_model(self,router,model):
        run=self.run_task()
        router.assert_not_called()
        self.assertEqual(run.runtime['modelCalls'],model.call_count)
        self.assertEqual(run.result['decisionTrace'],[])

    @override_settings(ANYJEV_ENABLED=False)
    def test_retried_case_request_after_completion_does_not_start_a_second_run(self):
        case=self.client.post('/api/assistant/cases/',{'station_id':'P5'},format='json').data
        payload={'kind':'diagnosis','station_id':'P5','case_id':case['id']}
        key=str(uuid.uuid4())
        first=self.client.post('/api/assistant/runs/',payload,format='json',HTTP_IDEMPOTENCY_KEY=key)
        with patch('operations.ai_assistant._completion',side_effect=fixtures.completion): process_one()
        again=self.client.post('/api/assistant/runs/',payload,format='json',HTTP_IDEMPOTENCY_KEY=key)
        self.assertEqual(again.status_code,200,again.data)
        self.assertEqual(again.data['id'],first.data['id'])
        self.assertEqual(AgentRun.objects.count(),1)

    def test_derived_simulation_cannot_impersonate_a_matching_raw_reading(self):
        row={'asset_code':'FAN-01','metric_key':'rotational.speed','value':1200,'unit':'rpm'}
        packet={'facts':[{**row,'evidence_id':'E1'}]}
        with self.assertRaises(ValueError):
            validate_facts(packet,[{'id':'E1','status':'ok','tool':'compare_scenarios','data':row}],
                {'FAN-01':{'readings':[row]}})

    def test_default_simulation_profile_is_explicit_and_does_not_approve_a_policy(self):
        from .agent_branch_profiles import demo_profile
        from .agent_branching import compare_scenarios
        snap=freeze({'kind':'diagnosis','station_id':'P5'},self.user)
        snap['source']={'mode':'simulated_test'}
        snap['branchScenario']=demo_profile(snap)
        result=compare_scenarios(snap)
        self.assertFalse(result['comparison']['comparable'])
        self.assertFalse(result['alertsResolved'])
        self.assertIn('scenario_runbook_conditions_not_approved',result['missing'])
        self.assertEqual(len(result['branches']),3)
