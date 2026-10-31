"""Offline API acceptance: simulated actors and model stubs, never live scores."""
from copy import deepcopy
import json
import uuid
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from . import test_software_sprint as fixtures
from . import test_agent_branching as branch_fixtures
from .agent_guardrails import VERSION as RULE_VERSION
from .agent_investigations import compatible, freeze_case, record_run
from .agent_procedures import digest, matching, validate_steps
from .models import Alert, Asset, Profile, Telemetry, WorkOrder
from .sprint_agents import freeze, process_one
from .sprint_knowledge import version as knowledge_version
from .sprint_models import (AgentRun, BranchComparison, DemoSession, InvestigationCase,
                            ProcedureTemplate, ReviewExperience)


def diagnosis_stub(*args, **kwargs):
    message = fixtures.completion(*args, **kwargs)
    if message.get('content') and '你当前独立角色是diagnosis。' in args[0][0]['content']:
        value = json.loads(message['content'])
        value.update(candidates=[{'label': '采集链路需核查', 'evidence_ids': ['E1'],
                                  'missing': ['独立现场检查']}],
                     next_checks=['断电后核对模块插接，并提交检查结果。'])
        message['content'] = json.dumps(value, ensure_ascii=False)
    return message


@override_settings(DEEPSEEK_API_KEY='OFFLINE_TEST_STUB',
                   ALLOWED_HOSTS=['testserver', '127.0.0.1'],
                   CONTROLLER_COMMAND_PROTOCOL='four-controller-v2')
class InvestigationWorkflowTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        # Invoke the fixture only; do not inherit or import the old TestCase class.
        fixtures.RunTests.setUpTestData.__func__(cls)
        cls.administrator = User.objects.create_user('investigation-admin')
        Profile.objects.update_or_create(user=cls.administrator, defaults={'role': 'administrator'})
        cls.other = User.objects.create_user('other-investigation-operator')
        Profile.objects.update_or_create(user=cls.other, defaults={'role': 'operator'})

    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def create_case(self, **extra):
        response = self.client.post('/api/assistant/cases/',
            {'station_id': 'P5', 'asset_code': 'MQ4-05', 'title': '模拟测试排障', **extra}, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        return InvestigationCase.objects.get(pk=response.data['id'])

    def create_run(self, **extra):
        return self.client.post('/api/assistant/runs/',
            {'kind': 'diagnosis', 'station_id': 'P5', **extra}, format='json',
            HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()))

    def completed_run(self, snapshot=None, **extra):
        return AgentRun.objects.create(owner=self.user, request_key=str(uuid.uuid4()),
            input={'kind': 'diagnosis', 'station_id': 'P5'}, status='completed',
            snapshot=snapshot or freeze({'kind': 'diagnosis', 'station_id': 'P5'}, self.user), **extra)

    def pending_check(self, case, kind='human'):
        check = {'id': str(uuid.uuid4()), 'label': '断电核对连接', 'kind': kind,
                 'status': 'pending', 'report': '', 'source': 'MODEL_SUGGESTION', 'evidenceRefs': []}
        case.state = {'checks': [check], 'hypotheses': [], 'history': []}
        case.status = 'awaiting_feedback'
        case.save(update_fields=['state', 'status'])
        return check

    def submit_feedback(self, case, check, **extra):
        return self.client.post(f'/api/assistant/cases/{case.pk}/feedback/',
            {'check_id': check['id'], 'status': 'completed',
             'report': '模拟人工报告：连接已重新核对，仍待仪器观测。', 'revision': case.revision, **extra}, format='json')

    def procedure(self, **extra):
        response = self.client.post('/api/assistant/procedures/', {
            'title': '模拟风机只读检查流程', 'station_id': 'P5', 'asset_kind': 'fan',
            'source_refs': ['RUNBOOK:fan'],
            'steps': [{'tool': 'asset_snapshot', 'args': {'asset_code': 'FAN-01'},
                       'expectedEvidence': '独立RPM和供电反馈及其质量。',
                       'stopCondition': '缺失或过期时报告证据不足，不确认转动。'}], **extra}, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        return ProcedureTemplate.objects.get(pk=response.data['id'])

    def review(self, procedure, action, actor=None, revision=None):
        self.client.force_authenticate(actor or self.administrator)
        response = self.client.post(f'/api/assistant/procedures/{procedure.pk}/review/',
            {'action': action, 'revision': procedure.revision if revision is None else revision}, format='json')
        self.client.force_authenticate(self.user)
        return response

    def test_case_creation_rejects_unknown_sensor_and_wrong_station(self):
        for extra in ({'asset_code': 'PUMP-01'}, {'asset_code': 'SMOKE-01'},
                      {'station_id': 'P6'}, {'source': {'mode': 'simulated_test'}}):
            response = self.client.post('/api/assistant/cases/',
                {'station_id': 'P5', 'asset_code': 'MQ4-05', **extra}, format='json')
            self.assertEqual(response.status_code, 400, response.data)
        self.assertEqual(InvestigationCase.objects.count(), 0)

    def test_case_list_detail_and_feedback_are_owner_private_even_for_admin(self):
        case = self.create_case()
        check = self.pending_check(case)
        for actor in (self.other, self.administrator):
            self.client.force_authenticate(actor)
            self.assertEqual(self.client.get('/api/assistant/cases/').data, [])
            self.assertEqual(self.client.get(f'/api/assistant/cases/{case.pk}/').status_code, 404)
            self.assertEqual(self.submit_feedback(case, check).status_code, 404)
        case.refresh_from_db()
        self.assertEqual(case.state['checks'][0]['status'], 'pending')

    def test_case_compatibility_checks_target_source_layout_and_presentation(self):
        case = self.create_case()
        compatible(case, {'station_id': 'P5', 'asset_code': 'MQ4-05'}, case.source,
                   case.layout_version, case.presentation_version)
        changes = [({'station_id': 'P1'}, case.source, case.layout_version, case.presentation_version),
                   ({'asset_code': 'FLAME-05'}, case.source, case.layout_version, case.presentation_version),
                   ({}, {**case.source, 'mode': 'different_source'}, case.layout_version, case.presentation_version),
                   ({}, {**case.source, 'generation': 'different_generation'}, case.layout_version, case.presentation_version),
                   ({}, case.source, 'old-layout', case.presentation_version),
                   ({}, case.source, case.layout_version, 'old-presentation')]
        for payload, source, layout, presentation in changes:
            with self.subTest(payload=payload, source=source), self.assertRaises(ValueError):
                compatible(case, payload, source, layout, presentation)

    def test_feedback_revision_conflict_does_not_change_case(self):
        case = self.create_case()
        check = self.pending_check(case)
        before = deepcopy(case.state)
        response = self.submit_feedback(case, check, revision=case.revision + 1)
        self.assertEqual(response.status_code, 409)
        case.refresh_from_db()
        self.assertEqual(case.state, before)

    def test_feedback_repeat_is_idempotent_and_different_repeat_is_conflict(self):
        case = self.create_case()
        check = self.pending_check(case)
        first = self.submit_feedback(case, check)
        self.assertEqual(first.status_code, 200, first.data)
        second = self.submit_feedback(case, check)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(first.data['revision'], second.data['revision'])
        self.assertEqual(len(second.data['history']), 1)
        self.assertEqual(self.submit_feedback(case, check, report='不同报告').status_code, 409)

    def test_feedback_report_is_labeled_and_does_not_create_readings_or_close_case(self):
        case = self.create_case()
        check = self.pending_check(case)
        telemetry_count, order_count = Telemetry.objects.count(), WorkOrder.objects.count()
        response = self.submit_feedback(case, check)
        self.assertEqual(response.status_code, 200)
        case.refresh_from_db()
        self.assertEqual(case.status, 'open')
        report = freeze_case(case)
        self.assertEqual(report['state']['checks'][0]['reportSource'], 'HUMAN_REPORT_NOT_INSTRUMENT_MEASUREMENT')
        self.assertIn('NOT_MEASUREMENTS', report['trust'])
        self.assertEqual(Telemetry.objects.count(), telemetry_count)
        self.assertEqual(WorkOrder.objects.count(), order_count)

    def test_feedback_unavailable_is_a_report_not_a_pass(self):
        case = self.create_case()
        check = self.pending_check(case)
        response = self.submit_feedback(case, check, status='unavailable', report='模拟：无法断电检查。')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['checks'][0]['status'], 'unavailable')
        self.assertNotIn(response.data['status'], {'resolved', 'closed'})

    def test_feedback_cannot_complete_software_check_or_inject_authority(self):
        case = self.create_case()
        check = self.pending_check(case, kind='software')
        self.assertEqual(self.submit_feedback(case, check).status_code, 400)
        check = self.pending_check(case)
        self.assertEqual(self.submit_feedback(case, check, approved=True).status_code, 400)
        self.assertEqual(self.submit_feedback(case, check, revision=True).status_code, 400)

    def test_continuation_rejects_another_owner_target_or_changed_layout(self):
        case = self.create_case()
        self.client.force_authenticate(self.other)
        self.assertIn(self.create_run(case_id=str(case.pk), asset_code='MQ4-05').status_code, {400, 404})
        self.client.force_authenticate(self.user)
        self.assertEqual(self.create_run(case_id=str(case.pk), asset_code='FLAME-05').status_code, 400)
        case.layout_version = 'retired-layout'
        case.save(update_fields=['layout_version'])
        self.assertEqual(self.create_run(case_id=str(case.pk), asset_code='MQ4-05').status_code, 400)
        self.assertEqual(AgentRun.objects.count(), 0)

    def test_continuation_rejects_changed_source_or_presentation(self):
        for field, value in [('source', {'mode': 'historical_replay'}), ('presentation_version', 'another-model')]:
            case = self.create_case()
            setattr(case, field, value)
            case.save(update_fields=[field])
            response = self.create_run(case_id=str(case.pk), asset_code='MQ4-05')
            self.assertEqual(response.status_code, 400, response.data)
        self.assertEqual(AgentRun.objects.count(), 0)

    def test_two_rounds_freeze_new_evidence_preserve_old_and_keep_reports_separate(self):
        case = self.create_case()
        first = self.create_run(case_id=str(case.pk), asset_code='MQ4-05')
        self.assertEqual(first.status_code, 202, first.data)
        with patch('operations.ai_assistant._completion', side_effect=diagnosis_stub):
            self.assertTrue(process_one())
        original = AgentRun.objects.get(pk=first.data['id'])
        self.assertEqual(original.status, 'completed', original.error)
        original_snapshot = deepcopy(original.snapshot)
        case.refresh_from_db()
        check = next(item for item in case.state['checks'] if item['kind'] == 'human')
        self.assertEqual(self.submit_feedback(case, check).status_code, 200)
        Telemetry.objects.create(asset=Asset.objects.get(code='MQ4-05'), event_id='simulation:continuation-new',
            metric_key='methane.raw', metric='methane.raw', value=250, unit='adc', recorded_at=timezone.now())
        second = self.create_run(case_id=str(case.pk), asset_code='MQ4-05')
        self.assertEqual(second.status_code, 202, second.data)
        with patch('operations.ai_assistant._completion', side_effect=diagnosis_stub):
            self.assertTrue(process_one())
        continued = AgentRun.objects.get(pk=second.data['id'])
        self.assertEqual(continued.status, 'completed', continued.error)
        original.refresh_from_db()
        self.assertEqual(original.snapshot, original_snapshot)
        self.assertNotEqual(continued.snapshot['sha256'], original.snapshot['sha256'])
        self.assertEqual(continued.snapshot['previousSnapshot']['hash'], original.snapshot['sha256'])
        self.assertEqual(continued.snapshot['caseContext']['state']['checks'][0]['reportSource'],
                         'HUMAN_REPORT_NOT_INSTRUMENT_MEASUREMENT')
        self.assertNotIn('reportSource', json.dumps(continued.snapshot['assets']))
        self.assertLessEqual(continued.runtime['modelCalls'], 12)
        self.assertLessEqual(continued.runtime['toolCalls'], 12)
        case.refresh_from_db()
        recorded = [entry for entry in case.state['history'] if entry['event'] == 'run_recorded']
        self.assertEqual(len(recorded), 2)
        self.assertNotEqual(recorded[0]['snapshotHash'], recorded[1]['snapshotHash'])

    def test_recording_run_is_idempotent_and_discards_invalid_hypothesis_references(self):
        case = self.create_case()
        run = self.completed_run(case=case, result={'answer': {'candidates': [
            {'label': '供电候选', 'support_refs': ['E1', 'E999'], 'counter_refs': ['E2']}],
            'next_checks': ['补充供电测量']}, 'evidence': [{'id': 'E1', 'status': 'ok'}, {'id': 'E2', 'status': 'rejected'}]})
        record_run(run)
        case.refresh_from_db()
        revision = case.revision
        self.assertEqual(case.state['hypotheses'][0]['supportRefs'], ['E1'])
        self.assertEqual(case.state['hypotheses'][0]['counterRefs'], [])
        self.assertEqual(case.state['hypotheses'][0]['status'], 'candidate')
        record_run(run)
        case.refresh_from_db()
        self.assertEqual(case.revision, revision)
        self.assertEqual(len(case.state['checks']), 1)

    def test_candidate_procedure_not_loaded_or_explicitly_executable(self):
        template = self.procedure()
        snap = freeze({'station_id': 'P5', 'asset_code': 'FAN-01'}, self.user)
        self.assertEqual(matching(snap, {'station_id': 'P5', 'asset_code': 'FAN-01'})['items'], [])
        with self.assertRaises(ValueError):
            matching(snap, {'station_id': 'P5', 'asset_code': 'FAN-01', 'procedure_id': str(template.pk)})

    def test_procedure_requires_admin_review_and_duplicate_review_is_conflict(self):
        template = self.procedure()
        for actor in (self.user, self.viewer):
            self.assertEqual(self.review(template, 'approve', actor=actor).status_code, 403)
        approved = self.review(template, 'approve')
        self.assertEqual(approved.status_code, 200, approved.data)
        self.assertEqual(approved.data['status'], 'approved')
        self.assertEqual(self.review(template, 'approve').status_code, 409)
        template.refresh_from_db()
        self.assertEqual(self.review(template, 'approve').status_code, 409)

    def test_approved_matching_template_loads_with_correct_asset_kind_and_retirement_removes_it(self):
        template = self.procedure()
        self.assertEqual(self.review(template, 'approve').status_code, 200)
        snap = freeze({'station_id': 'P5', 'asset_code': 'FAN-01'}, self.user)
        found = matching(snap, {'station_id': 'P5', 'asset_code': 'FAN-01'})
        self.assertEqual([item['id'] for item in found['items']], [str(template.pk)])
        self.assertEqual(found['items'][0]['status'], 'approved')
        template.refresh_from_db()
        self.assertEqual(self.review(template, 'retire').status_code, 200)
        self.assertEqual(matching(snap, {'station_id': 'P5', 'asset_code': 'FAN-01'})['items'], [])
        # The already frozen task context is historical and must remain intact.
        self.assertEqual(found['items'][0]['status'], 'approved')

    def test_procedure_source_version_kind_station_and_hash_mismatches_do_not_load(self):
        template = self.procedure()
        self.assertEqual(self.review(template, 'approve').status_code, 200)
        snap = freeze({'station_id': 'P5', 'asset_code': 'FAN-01'}, self.user)
        for field, value in [('source_scope', 'historical_replay'), ('layout_version', 'old-layout'),
                             ('presentation_version', 'different-model'), ('rule_version', 'old-rule'),
                             ('knowledge_version', 'old-corpus'), ('station_id', 'P1'), ('asset_kind', 'sensor')]:
            original = getattr(template, field)
            setattr(template, field, value)
            template.content_hash = digest(template)
            template.save()
            self.assertEqual(matching(snap, {'station_id': 'P5', 'asset_code': 'FAN-01'})['items'], [], field)
            setattr(template, field, original)
        template.content_hash = 'tampered-content'
        template.save()
        self.assertEqual(matching(snap, {'station_id': 'P5', 'asset_code': 'FAN-01'})['items'], [])

    def test_procedure_rejects_control_shell_unknown_tools_and_invalid_arguments(self):
        for tool, arguments in [('propose_control', {'asset_code': 'FAN-01', 'intent': 'power', 'value': 1}),
                                ('draft_work_order', {}), ('shell', {'command': 'echo bad'}),
                                ('asset_snapshot', {'asset_code': 'FAN-01', 'execute': True})]:
            step = {'tool': tool, 'args': arguments, 'expectedEvidence': '观察', 'stopCondition': '停止'}
            with self.subTest(tool=tool), self.assertRaises(ValueError):
                validate_steps([step], 'P5', {'FAN-01'})
        self.client.force_authenticate(self.viewer)
        response = self.client.post('/api/assistant/procedures/', {}, format='json')
        self.assertEqual(response.status_code, 403)

    def test_unknown_source_refs_and_private_source_run_are_rejected(self):
        payload = {'title': '模拟流程', 'station_id': 'P5', 'asset_kind': '',
            'source_refs': ['E999'], 'steps': [{'tool': 'station_snapshot', 'args': {'station_id': 'P5'},
                'expectedEvidence': '采样时间', 'stopCondition': '证据缺失停止'}]}
        self.assertEqual(self.client.post('/api/assistant/procedures/', payload, format='json').status_code, 400)
        foreign = AgentRun.objects.create(owner=self.other, request_key='private-source', status='completed',
            result={'evidence': [{'id': 'E1', 'status': 'ok'}]}, snapshot={})
        payload.update(source_refs=['E1'], source_run_id=str(foreign.pk))
        self.assertEqual(self.client.post('/api/assistant/procedures/', payload, format='json').status_code, 400)

    def test_private_candidates_are_not_shared_until_approved(self):
        template = self.procedure()
        self.client.force_authenticate(self.other)
        self.assertEqual(self.client.get('/api/assistant/procedures/').data, [])
        self.client.force_authenticate(self.user)
        self.assertEqual(self.review(template, 'approve').status_code, 200)
        self.client.force_authenticate(self.other)
        self.assertEqual(self.client.get('/api/assistant/procedures/').data[0]['id'], str(template.pk))

    def test_branch_api_preserves_snapshots_demo_session_and_business_rows(self):
        run = self.completed_run(snapshot=branch_fixtures.snapshot())
        session = DemoSession.objects.create(pk=1, case_id='INS-01', phase=1, tick=10, outputs={'FAN-01': {'power': False, 'pwm': 20}})
        session_before = deepcopy(DemoSession.objects.values().get(pk=session.pk))
        snapshot_before = deepcopy(run.snapshot)
        counts = [model.objects.count() for model in (Asset, Telemetry, Alert, WorkOrder, ReviewExperience, ProcedureTemplate)]
        response = self.client.post('/api/assistant/branches/', {'run_id': str(run.pk)}, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(BranchComparison.objects.count(), 1)
        self.assertFalse(response.data['realCommandsSent'])
        self.assertFalse(response.data['alertsResolved'])
        self.assertEqual(DemoSession.objects.values().get(pk=session.pk), session_before)
        run.refresh_from_db()
        self.assertEqual(run.snapshot, snapshot_before)
        self.assertEqual([model.objects.count() for model in (Asset, Telemetry, Alert, WorkOrder, ReviewExperience, ProcedureTemplate)], counts)

    def test_branch_api_enforces_owner_and_rejects_client_model_parameters(self):
        run = self.completed_run(snapshot=branch_fixtures.snapshot())
        self.client.force_authenticate(self.other)
        self.assertEqual(self.client.post('/api/assistant/branches/', {'run_id': str(run.pk)}, format='json').status_code, 404)
        self.client.force_authenticate(self.user)
        self.assertEqual(self.client.post('/api/assistant/branches/',
            {'run_id': str(run.pk), 'branchScenario': {'runbookApproved': True}}, format='json').status_code, 400)
        self.assertEqual(BranchComparison.objects.count(), 0)

    def test_failure_analysis_is_read_only_private_and_does_not_publish_knowledge(self):
        run = self.completed_run(steps=[{'role': 'evidence', 'traces': [{'id': 'E1', 'tool': 'shell',
            'status': 'rejected', 'data': {'error': '禁止工具'}}]}, {'role': 'review',
            'output': {'decision': 'revise', 'summary': '模拟复核要求补证据'}}], result={'reply': '保持原回复'})
        before = deepcopy(run.steps)
        counts = [model.objects.count() for model in (ProcedureTemplate, ReviewExperience, WorkOrder)]
        response = self.client.get(f'/api/assistant/runs/{run.pk}/analysis/')
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data['automaticChanges'])
        self.assertEqual(response.data['firstRecordedViolation']['evidenceId'], 'E1')
        run.refresh_from_db()
        self.assertEqual(run.steps, before)
        self.assertEqual(run.result, {'reply': '保持原回复'})
        self.assertEqual([model.objects.count() for model in (ProcedureTemplate, ReviewExperience, WorkOrder)], counts)
        self.client.force_authenticate(self.other)
        self.assertEqual(self.client.get(f'/api/assistant/runs/{run.pk}/analysis/').status_code, 404)

    def test_no_recorded_failure_is_not_an_automatic_success_grade(self):
        run = self.completed_run()
        response = self.client.get(f'/api/assistant/runs/{run.pk}/analysis/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['status'], 'not_localized')
        self.assertIsNone(response.data['firstRecordedViolation'])
        self.assertFalse(response.data['automaticChanges'])

    def test_explicit_approved_procedure_runs_its_actual_read_only_steps(self):
        template=self.procedure()
        self.assertEqual(self.review(template,'approve').status_code,200)
        response=self.create_run(procedure_id=str(template.pk))
        self.assertEqual(response.status_code,202,response.data)
        with patch('operations.ai_assistant._completion',side_effect=fixtures.completion): process_one()
        run=AgentRun.objects.get(pk=response.data['id'])
        self.assertEqual(run.status,'completed',run.error)
        self.assertEqual(run.input['asset_code'],'FAN-01')
        self.assertTrue(any(e.get('origin')=='APPROVED_READ_ONLY_PROCEDURE' and e['tool']=='asset_snapshot'
            and e['status']=='ok' for e in run.result['evidence']))
        template.refresh_from_db()
        self.assertTrue(any(a['action']=='read_only_regression' for a in template.audit))

    def test_malformed_new_fields_and_procedure_metadata_are_bad_requests(self):
        for field in ('case_id','procedure_id'):
            for value in ([],{},True,''):
                response=self.create_run(**{field:value})
                self.assertEqual(response.status_code,400,(field,value,response.data))
        self.assertEqual(AgentRun.objects.count(),0)

    def test_extracting_successful_tools_creates_only_an_unapproved_candidate(self):
        response=self.create_run()
        with patch('operations.ai_assistant._completion',side_effect=fixtures.completion): process_one()
        result=self.client.post('/api/assistant/procedures/from-run/',{'run_id':response.data['id']},format='json')
        self.assertEqual(result.status_code,201,result.data)
        self.assertEqual(result.data['status'],'candidate')
        self.assertTrue(result.data['steps'])
        self.assertFalse(any(s['tool'] in {'propose_control','draft_work_order'} for s in result.data['steps']))
        self.client.force_authenticate(self.other)
        self.assertEqual(self.client.post('/api/assistant/procedures/from-run/',{'run_id':response.data['id']},format='json').status_code,404)
        self.client.force_authenticate(self.viewer)
        self.assertEqual(self.client.post('/api/assistant/procedures/from-run/',{'run_id':response.data['id']},format='json').status_code,403)
