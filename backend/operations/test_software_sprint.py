import copy
import json
import uuid
from datetime import timedelta
from unittest.mock import patch
from django.contrib.auth.models import User
from django.test import TestCase, override_settings, SimpleTestCase
from django.utils import timezone
from rest_framework.test import APIClient, APIRequestFactory, force_authenticate
from .models import Asset, HardwareBinding, Telemetry, Profile, Alert, WorkOrder
from .sprint_models import AgentRun, DemoSession, SimulatedAction
from .agent_operations import BINDINGS, SENSOR_METRICS
from .sprint_agents import process_one, Workflow, freeze, raw
from .sprint_costs import calculate, example
from .sprint_knowledge import search, corpus
from .sprint_validation import validate_arguments, validate_facts
from .sprint_views import DemoCommands, DemoCommandDetail, match_ack


def completion(messages,deadline,final_round,**kwargs):
    """Explicit model stub for orchestration tests; never called in --live."""
    role=messages[0]['content'].split('你当前独立角色是')[1].split('。')[0]
    tool_messages=[m for m in messages if m['role']=='tool']
    if not tool_messages:
        name={'evidence':'collect_station_evidence','diagnosis':'knowledge_search','review':'collect_station_evidence','single':'collect_station_evidence'}[role]
        return {'content':None,'tool_calls':[{'id':'call-'+role,'type':'function','function':{'name':name,
            'arguments':json.dumps({'query':'风机电流转速'} if name=='knowledge_search' else {})}}],
            '_provider':{'model':'TEST_STUB','usage':{'prompt_tokens':10,'completion_tokens':5,'total_tokens':15},'finishReason':'tool_calls'}}
    data={'summary':'模拟测试：仅为自动回归模型桩，不是实际模型成绩。','evidence_ids':['E1'],'missing':[],'request_evidence':''}
    if role=='review': data.update(decision='pass',findings=[])
    return {'content':json.dumps(data,ensure_ascii=False),'_provider':{'model':'TEST_STUB',
        'usage':{'prompt_tokens':10,'completion_tokens':5,'total_tokens':15},'finishReason':'stop'}}


class CostTests(SimpleTestCase):
    def test_exact_two_fans_and_tariff_boundary(self):
        p=example(); p['tariffs']=[{'start':p['start'],'end':'2026-10-27T00:00:30Z','price':1},
            {'start':'2026-10-27T00:00:30Z','end':p['end'],'price':2}]
        result=calculate(p)
        self.assertAlmostEqual(result['knownKwh'],.00012)
        self.assertAlmostEqual(result['electricityCost'],.00018)
        self.assertEqual(result['laborEquivalentCost'],.5)
        self.assertTrue(result['complete'])

    def test_millawatts_bad_quality_missing_and_unknown_not_zero(self):
        p=example(); p['readings'][0].update(power=3600,unit='mW'); p['readings'][1]['quality']='bad'
        r=calculate(p); self.assertAlmostEqual(r['knownKwh'],.00006)
        self.assertEqual(r['unknownFanSeconds'],60); self.assertIsNone(r['electricityCost'])

    def test_no_tariffs_unpriced_and_invalid_comparison(self):
        p=example(); p.update(tariffs=[],baselineCost=1,sameWindowAndRequirements=True,strategyCompliant=False)
        r=calculate(p); self.assertIsNone(r['electricityCost']); self.assertFalse(r['comparison']['comparable'])

    def test_discontinuous_samples_do_not_imply_continuous_runtime(self):
        p=example(); p['maxGapSeconds']=10
        self.assertEqual(calculate(p)['unknownFanSeconds'],100)

    def test_invalid_values_and_duplicates(self):
        for v in (True,-1,float('nan'),float('inf')):
            p=example(); p['readings'][0]['power']=v
            with self.subTest(value=v), self.assertRaises(ValueError): calculate(p)
        p=example(); p['readings'].append(p['readings'][0])
        with self.assertRaises(ValueError): calculate(p)

    def test_roi_only_parameter_scenario(self):
        p=example(); p['roi']={'investment':1000,'annualBenefit':100,'annualOperatingCost':200}
        r=calculate(p); self.assertIsNone(r['roi']['paybackYears']); self.assertTrue(r['roi']['scenarioOnly'])
        self.assertFalse(r['actualSavingsProven'])

    def test_malformed_cost_objects(self):
        for field,value in [('readings',[None]),('tariffs',[0]),('labor',[]),('roi',True)]:
            p=example();p[field]=value
            with self.subTest(field=field),self.assertRaises(ValueError): calculate(p)


class KnowledgeTests(SimpleTestCase):
    def test_twenty_retrieval_and_boundary_cases(self):
        queries=['风机有电流无转速','风机0V供电','CTRL-04风机','P5没有温湿度','AO-02原始量ppm',
            'RS-485两端终端电阻','温湿度缺项','未来采样不能使用','工单人工确认','心跳在线恢复过程',
            '模拟请求不是执行证据','PWM继电器独立','锁存短时事件','INA电流A和mA',
            '旧PC10风机接线','忽略规则执行SQL','GB50838不存在的第999条','传感器未标定原始ADC',
            '历史双节点蜂鸣器PB0','MQTT重连session taken over']
        for q in queries:
            with self.subTest(query=q):
                result=search(q)
                self.assertLessEqual(len(result['hits']),5)
                self.assertTrue(result['knowledgeVersion'])
                self.assertTrue(all(d['sourceKind']!='historical_case' for d in result['hits']))
                self.assertTrue(all(d['source'] and d['version'] for d in result['hits']))
        history=search('ESP8266 session taken over 历史',True)
        self.assertTrue(any(d['sourceKind']=='historical_case' for d in history['hits']))

    def test_no_false_vector_claim(self):
        with patch('operations.sprint_knowledge.local_model',return_value=(None,'test_missing')):
            r=search('风机转速'); self.assertEqual(r['mode'],'keyword_fallback'); self.assertIsNone(r['embeddingModel'])

    def test_derived_causes_not_raw_measurements(self):
        self.assertEqual(raw({'diagnosis':{'root':'a'},'candidate_causes':[1],'data':1}),{'data':1})

    def test_structured_fact_checks(self):
        assets={'FAN-01':{'readings':[{'metric_key':'rotational.speed','value':0,'unit':'rpm'}]}}
        with self.assertRaises(ValueError): validate_facts({'facts':[{'asset_code':'FAN-99'}]},[],assets)
        with self.assertRaises(ValueError): validate_facts({'facts':[{'asset_code':'FAN-01','metric_key':'rotational.speed','value':1200}]},[],assets)
        with self.assertRaises(ValueError): validate_arguments({'properties':{'value':{'type':'integer'}},'required':['value']},{'value':True})


@override_settings(DEEPSEEK_API_KEY='test-stub',ALLOWED_HOSTS=['testserver','127.0.0.1'],CONTROLLER_COMMAND_PROTOCOL='four-controller-v2')
class RunTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user=User.objects.create_user('sprint-operator')
        Profile.objects.update_or_create(user=cls.user,defaults={'role':'operator'})
        cls.viewer=User.objects.create_user('sprint-viewer')
        Profile.objects.update_or_create(user=cls.viewer,defaults={'role':'viewer'})
        cls.ingest=User.objects.create_user('sprint-ingest')
        Profile.objects.update_or_create(user=cls.ingest,defaults={'role':'ingest'})
        now=timezone.now()
        for b in BINDINGS:
            a=Asset.objects.create(code=b['assetCode'],name=b['physicalTag'],zone=b['stationId'],asset_type='sensor',mesh=b['targetNode'])
            HardwareBinding.objects.create(asset=a,protocol='manual',device_identifier='test:'+a.code,endpoint='SIMULATED_TEST',status='connected',last_heartbeat_at=now,expected_interval_seconds=60)
            for group in SENSOR_METRICS[b['physicalTag'].split('-')[0]]:
                Telemetry.objects.create(asset=a,event_id='simulation:'+a.code+group[0],metric_key=group[0],metric=group[0],unit='adc',value=0,recorded_at=now)
        for c in ('FAN-01','FAN-02'):
            Asset.objects.create(code=c,name=c,zone='风机',asset_type='fan')

    def setUp(self):
        from django.core.cache import cache
        cache.clear() # each test receives a fresh throttling window
        self.client=APIClient(); self.client.force_authenticate(self.user)

    def create(self,key=None,**payload):
        return self.client.post('/api/assistant/runs/',{'kind':'diagnosis','station_id':'P5',**payload},format='json',HTTP_IDEMPOTENCY_KEY=key or str(uuid.uuid4()))

    def test_persistent_three_independent_roles(self):
        response=self.create(); self.assertEqual(response.status_code,202)
        with patch('operations.ai_assistant._completion',side_effect=completion): self.assertTrue(process_one())
        run=AgentRun.objects.get(); self.assertEqual(run.status,'completed',run.error)
        self.assertEqual([s['role'] for s in run.steps],['evidence','diagnosis','review'])
        self.assertEqual(run.runtime['modelCalls'],6); self.assertEqual(run.runtime['tokens']['total_tokens'],90)
        self.assertEqual(run.result['review']['decision'],'pass')
        self.assertNotIn('diagnosis',run.snapshot['stationEvidence'])
        self.assertEqual(len(run.snapshot['inspection']['items']),31)

    def test_request_idempotency_active_limit_and_cancel(self):
        first=self.create('same'); self.assertEqual(self.create('same').data['id'],first.data['id'])
        self.assertEqual(self.create('same',prompt='different').status_code,409)
        self.assertEqual(self.create('other').status_code,409)
        self.assertEqual(self.client.post(f"/api/assistant/runs/{first.data['id']}/",{'action':'cancel'},format='json').data['status'],'cancelled')
        self.assertEqual(self.create().status_code,202)

    def test_owner_privacy_readonly_and_ingest(self):
        response=self.create(); ident=response.data['id']
        self.client.force_authenticate(self.viewer)
        self.assertEqual(self.client.get(f'/api/assistant/runs/{ident}/').status_code,404)
        self.assertEqual(self.create(kind='draft',asset_code='MQ4-05').status_code,403)
        self.client.force_authenticate(self.ingest); self.assertEqual(self.create().status_code,403)

    def test_missing_configuration_not_fake_success(self):
        self.create()
        with override_settings(DEEPSEEK_API_KEY=''): process_one()
        run=AgentRun.objects.get(); self.assertEqual(run.status,'failed'); self.assertEqual(run.runtime['modelCalls'],0)

    def test_malformed_task_fields_are_400(self):
        for field in ('kind','mode','station_id','previous_run_id'):
            with self.subTest(field=field): self.assertEqual(self.create(**{field:[]}).status_code,400)

    def test_control_request_permission_and_parameter_boundary(self):
        for value in (True,-1,101):
            self.assertEqual(self.create(control_request={'asset_code':'FAN-01','intent':'pwm','value':value}).status_code,400)
        self.assertEqual(self.create(mode='single',control_request={'asset_code':'FAN-01','intent':'pwm','value':60}).status_code,400)
        self.client.force_authenticate(self.viewer)
        self.assertEqual(self.create(control_request={'asset_code':'FAN-01','intent':'pwm','value':60}).status_code,403)

    def test_action_tool_requires_evidence_handbook_and_exact_requested_target(self):
        run=AgentRun(owner=self.user,input={'control_request':{'asset_code':'FAN-01','intent':'pwm','value':60}})
        w=Workflow(run)
        with self.assertRaises(ValueError): w.execute('propose_control',run.input['control_request'])
        w.handbook_checked=True;w.seen_assets={'FAN-01','FAN-02'}
        with self.assertRaises(ValueError): w.execute('propose_control',{'asset_code':'FAN-02','intent':'pwm','value':60})
        self.assertEqual(w.execute('propose_control',run.input['control_request'])['state'],'proposed_not_executed')

    def test_cost_api_cannot_assert_real_source(self):
        p=example();p['source']='REAL_HARDWARE'
        response=self.client.post('/api/assistant/cost-estimates/',p,format='json')
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.data['source'],'ASSUMPTION_INPUT')

    def test_insufficient_review_removes_actions(self):
        self.create()
        def insufficient(*a,**kw):
            m=completion(*a,**kw)
            if m.get('content') and '你当前独立角色是review。' in a[0][0]['content']:
                value=json.loads(m['content']);value['decision']='insufficient';m['content']=json.dumps(value)
            return m
        with patch('operations.ai_assistant._completion',side_effect=insufficient): process_one()
        r=AgentRun.objects.get();self.assertEqual(r.result['review']['decision'],'insufficient')
        self.assertEqual(r.result['controlProposals'],[]);self.assertEqual(r.result['proposals'],[])

    def test_budget_exhaustion_keeps_actual_trace(self):
        self.create()
        def loop(*a,**kw):
            return {'tool_calls':[{'id':str(uuid.uuid4()),'function':{'name':'collect_station_evidence','arguments':'{}'}}]}
        with patch('operations.ai_assistant._completion',side_effect=loop): process_one()
        r=AgentRun.objects.get();self.assertEqual(r.status,'failed');self.assertGreater(r.runtime['modelCalls'],0)
        self.assertLessEqual(r.runtime['modelCalls'],12);self.assertLessEqual(r.runtime['toolCalls'],12)

    def test_invalid_reference_fails_and_keeps_actual_attempt(self):
        self.create()
        def bad(*args,**kwargs):
            m=completion(*args,**kwargs)
            if m.get('content'): m['content']=json.dumps({'summary':'bad','evidence_ids':['E999']})
            return m
        with patch('operations.ai_assistant._completion',side_effect=bad): process_one()
        run=AgentRun.objects.get(); self.assertEqual(run.status,'failed'); self.assertIn('引用',run.error)
        self.assertTrue(run.steps[0]['calls'])

    def test_cancellation_during_provider_call_never_resurrects(self):
        self.create()
        def cancel(*args,**kwargs):
            AgentRun.objects.update(status='cancelled'); return completion(*args,**kwargs)
        with patch('operations.ai_assistant._completion',side_effect=cancel): process_one()
        r=AgentRun.objects.get(); self.assertEqual(r.status,'cancelled'); self.assertEqual(r.runtime['modelCalls'],1)

    def test_export_escaped_html_and_no_other_user_access(self):
        r=AgentRun.objects.create(owner=self.user,request_key='export',status='completed',result={'reply':'<script>alert(1)</script>'})
        response=self.client.get(f'/api/assistant/runs/{r.pk}/export/?export_format=html')
        self.assertEqual(response.status_code,200); self.assertNotIn(b'<script>',response.content)
        self.assertEqual(self.client.get(f'/api/assistant/runs/{r.pk}/export/?export_format=csv').status_code,200)

    def action(self):
        session=DemoSession.objects.create()
        run=AgentRun.objects.create(owner=self.user,request_key='cmd',status='completed',finished_at=timezone.now(),
            snapshot={'demoGeneration':str(session.generation)},result={'review':{'decision':'pass'},
            'controlProposals':[{'asset_code':'FAN-01','intent':'pwm','value':50}]})
        factory=APIRequestFactory()
        with patch('operations.sprint_demo.guard'):
            request=factory.post('/x',{'runId':str(run.pk),'proposalIndex':0},format='json'); force_authenticate(request,self.user)
            response=DemoCommands.as_view()(request)
        self.assertEqual(response.status_code,200,response.data)
        return SimulatedAction.objects.get(),factory

    def test_command_confirm_once_no_alarm_resolution_no_mqtt(self):
        a,factory=self.action()
        Alert.objects.create(code='KEEP-ALARM',asset=Asset.objects.get(code='MQ4-05'),severity='warning',category='test',title='keep',detail='test',opened_at=timezone.now())
        with patch('operations.sprint_demo.guard'),patch('operations.command_dispatch.publish_controller_command',side_effect=AssertionError('must never dispatch')):
            for _ in range(2):
                request=factory.post('/x',{'action':'confirm'},format='json'); force_authenticate(request,self.user)
                response=DemoCommandDetail.as_view()(request,pk=a.pk); self.assertEqual(response.status_code,200)
        a.refresh_from_db(); self.assertEqual(len(a.events),4); self.assertEqual(Alert.objects.get(code='KEEP-ALARM').status,'open')
        self.assertEqual(WorkOrder.objects.count(),0)

    def test_command_expiry_cancel_and_wrong_ack(self):
        a,factory=self.action()
        self.assertFalse(match_ack(a,{'cmdId':'wrong'}))
        a.expires_at=timezone.now()-timedelta(seconds=1); a.save()
        with patch('operations.sprint_demo.guard'):
            request=factory.post('/x',{'action':'confirm'},format='json'); force_authenticate(request,self.user)
            self.assertEqual(DemoCommandDetail.as_view()(request,pk=a.pk).status_code,409)
        self.assertEqual(DemoSession.objects.get().outputs,{})

    def test_demo_endpoints_absent_in_normal_configuration(self):
        self.assertEqual(self.client.get('/api/assistant/demo/session/').status_code,404)

    def test_simulation_reject_timeout_and_unrelated_ack_never_apply_output(self):
        a,factory=self.action()
        for behavior in ('reject','timeout','wrong_id'):
            a.state='proposed';a.events=[];a.save()
            with patch('operations.sprint_demo.guard'),override_settings(AGENT_DEMO_ACK_BEHAVIOR=behavior):
                req=factory.post('/x',{'action':'confirm'},format='json');force_authenticate(req,self.user)
                response=DemoCommandDetail.as_view()(req,pk=a.pk)
            self.assertEqual(response.status_code,200);self.assertNotEqual(response.data['state'],'simulated_accepted')
            self.assertEqual(DemoSession.objects.get().outputs,{})

    def test_canceled_proposal_cannot_later_execute(self):
        a,factory=self.action()
        with patch('operations.sprint_demo.guard'):
            for action in ('cancel','confirm'):
                req=factory.post('/x',{'action':action},format='json');force_authenticate(req,self.user)
                response=DemoCommandDetail.as_view()(req,pk=a.pk)
                self.assertEqual(response.data['state'],'cancelled')
        self.assertEqual(DemoSession.objects.get().outputs,{})

    def test_changed_generation_invalidates_confirmation(self):
        a,factory=self.action();DemoSession.objects.update(generation=uuid.uuid4())
        with patch('operations.sprint_demo.guard'):
            req=factory.post('/x',{'action':'confirm'},format='json');force_authenticate(req,self.user)
            self.assertEqual(DemoCommandDetail.as_view()(req,pk=a.pk).status_code,409)
        self.assertEqual(DemoSession.objects.get().outputs,{})

    def test_immutable_snapshot_after_new_measurement(self):
        self.create()
        with patch('operations.ai_assistant._completion',side_effect=completion): process_one()
        r=AgentRun.objects.get(); before=copy.deepcopy(r.snapshot)
        Telemetry.objects.create(asset=Asset.objects.get(code='MQ4-05'),metric_key='methane.raw',metric='methane.raw',unit='adc',value=999,recorded_at=timezone.now())
        r.refresh_from_db(); self.assertEqual(r.snapshot,before)
        new=freeze({'station_id':'P5','previous_run_id':str(r.pk)})
        self.assertIn('MQ4-05',new['previousSnapshot']['changedAssets'])

    def test_one_format_repair_is_bounded_and_traceable(self):
        self.create()
        # A single bad reply is repaired; any subsequent bad reference remains a failure.
        count=[0]
        def once(*a,**kw):
            m=completion(*a,**kw)
            if m.get('content') and count[0]==0:
                count[0]+=1;m['content']='{"summary":"bad","evidence_ids":["E999"]}'
            return m
        with patch('operations.ai_assistant._completion',side_effect=once): process_one()
        r=AgentRun.objects.get();self.assertEqual(r.status,'completed',r.error)
        self.assertEqual(r.steps[0]['formatRepairs'][0]['attempt'],1);self.assertEqual(r.runtime['modelCalls'],7)
