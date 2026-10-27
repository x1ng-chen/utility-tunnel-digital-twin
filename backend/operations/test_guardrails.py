import copy
from datetime import datetime,timezone
from django.test import SimpleTestCase,TestCase,override_settings
from django.core.cache import cache
from django.contrib.auth.models import User
from rest_framework.test import APIClient
from unittest.mock import patch
from uuid import uuid4
from .agent_guardrails import derive,validate_output,GuardViolation,VERSION
from .joint_benchmark import entries,fixture,asserted_output,stub
from .sprint_agents import freeze,process_one
from .sprint_models import AgentRun
from .models import WorkOrder
from . import test_software_sprint as base_tests


class GuardRuleTests(SimpleTestCase):
    def packet(self,case):
        return fixture({'capturedAt':'2026-10-27T00:00:00+00:00','assets':{},'source':{},'thresholds':{}},case)
    def evidence(self,s):
        out=[{'id':'E1','status':'ok','tool':'collect_station_evidence','arguments':{},'data':{}}]
        for i,code in enumerate(('FAN-01','MQ4-05','O2-02'),2):
            out.append({'id':f'E{i}','status':'ok','tool':'asset_snapshot','arguments':{'asset_code':code},'data':s['assets'][code]})
        if 'workOrderReview' in s: out.append({'id':'E5','status':'ok','tool':'review_work_order','data':s['workOrderReview']})
        return out
    def test_joint_assertion_matrix_and_explicit_observability_boundary(self):
        for case in entries():
            if case['id'] in ('J21','J22'): continue # exercised through real role/write policies below
            s=self.packet(case);e=self.evidence(s);output=asserted_output(case,e)
            with self.subTest(case=case['id']):
                if case['expected']=='reject':
                    with self.assertRaises(GuardViolation): validate_output(output,s,e)
                else: validate_output(output,s,e)
    def test_derived_checks_are_not_raw_evidence_or_unique_cause(self):
        s=self.packet(entries()[8]);result=derive(s,self.evidence(s));fan=result['findings'][0]
        self.assertEqual(fan['state'],'unsupported');self.assertIn('不确定',fan['message'])
        self.assertEqual(fan['kind'],'deterministic_inference_not_measurement')
        bad={'claims':[{'kind':'fan_motion','asset_code':'FAN-01','state':'supported','evidence_ids':['G1']}]}
        with self.assertRaises(GuardViolation): validate_output(bad,s,self.evidence(s))
    def test_missing_data_is_unknown_and_does_not_reject_readonly_analysis(self):
        for case in (entries()[2],entries()[3],entries()[19]):
            s=self.packet(case);validate_output({'summary':'资料不足，继续只读核查。','claims':[]},s,self.evidence(s))
            self.assertTrue(any(f['state']=='unknown' for f in derive(s)['findings']))
    def test_bad_typed_claims_rejected_and_flags_cannot_rejuvenate_time(self):
        s=self.packet(entries()[0]);s['assets']['FAN-01']['readings'][0].update(scenario_usable=True,freshness='fresh')
        self.assertEqual(derive(s)['findings'][0]['state'],'unknown')
        for c in (None,{}, {'kind':[],'asset_code':'FAN-01','state':'supported','evidence_ids':[]}):
            with self.subTest(claim=c),self.assertRaises(GuardViolation): validate_output({'claims':[c]},s,self.evidence(s))
    def test_guard_references_are_validated_in_their_own_namespace(self):
        from .sprint_output import check_output
        check_output({'summary':'G1为推导，不是测量。','guard_ids':['G1']},'diagnosis',[],set(),[],{'G1'})
        for out in ({'summary':'G99','guard_ids':['G99']},{'summary':'test','evidence_ids':['G1']}):
            with self.assertRaises(ValueError): check_output(out,'diagnosis',[],set(),[],{'G1'})
    def test_current_unit_conversion_remains_a_derivation_not_a_raw_fact(self):
        s=self.packet(entries()[7]);e=self.evidence(s)
        f=next(f for f in derive(s,e)['findings'] if f['assetCode']=='FAN-01')
        self.assertAlmostEqual(f['derivedCurrentAmps'],.2)
        row=next(r for r in s['assets']['FAN-01']['readings'] if r['metric_key']=='motor.current')
        self.assertEqual((row['value'],row['unit']),(200,'mA'))
        self.assertEqual(f['state'],'supported')


@override_settings(DEEPSEEK_API_KEY='EXPLICIT_OFFLINE_STUB',AGENT_EVALUATION_MODE=True,AGENT_EXPERIENCE_ENABLED=False,
    ALLOWED_HOSTS=['testserver','127.0.0.1'],CONTROLLER_COMMAND_PROTOCOL='four-controller-v2')
class GuardWorkflowTests(TestCase):
    @classmethod
    def setUpTestData(cls): base_tests.RunTests.setUpTestData.__func__(cls)
    def test_both_orchestrators_execute_same_frozen_matrix_without_paid_calls(self):
        for case in entries():
            actor=self.viewer if case['role']=='viewer' else self.user
            s=fixture(freeze({**case['task'],'kind':'diagnosis'},actor),case)
            for mode in ('single','multi'):
                cache.clear();client=APIClient();client.force_authenticate(actor);before=WorkOrder.objects.count()
                response=client.post('/api/assistant/runs/',{**case['task'],'mode':mode},format='json',HTTP_IDEMPOTENCY_KEY=uuid4().hex)
                self.assertEqual(response.status_code,202,response.data)
                run=AgentRun.objects.get(pk=response.data['id']);run.snapshot=s;run.save(update_fields=['snapshot'])
                with patch('operations.ai_assistant._completion',side_effect=stub(case)),patch('operations.ai_assistant.urlopen',side_effect=AssertionError('paid call forbidden')): process_one()
                run.refresh_from_db()
                rejected=any(e['status']=='rejected' for e in run.result.get('evidence',[]))
                intercepted=bool(run.result['guardrails']['violations']) or rejected
                with self.subTest(case=case['id'],mode=mode):
                    self.assertEqual(intercepted,case['expected']=='reject',run.error)
                    if case['expected']!='reject': self.assertEqual(run.status,'completed',run.error)
                    self.assertEqual(WorkOrder.objects.count(),before)
                    self.assertLessEqual(run.runtime['modelCalls'],12);self.assertLessEqual(run.runtime['toolCalls'],12)
                    if case['expected']=='reject' and run.status=='failed':
                        self.assertEqual(run.result['controlProposals'],[]);self.assertEqual(run.result['proposals'],[])
