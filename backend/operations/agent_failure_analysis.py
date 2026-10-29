"""Find recorded contract violations, not an oracle for arbitrary model failures."""
def analyze(run):
    events = []
    for index, step in enumerate(run.steps):
        for trace in step.get('traces', []):
            if trace.get('status') == 'rejected':
                events.append({'stageIndex': index, 'role': step.get('role'), 'kind': 'tool_rejected',
                    'evidenceId': trace.get('id'), 'tool': trace.get('tool'),
                    'message': trace.get('data', {}).get('error', '工具调用被拒绝。')})
        for event in step.get('guardViolations', []):
            events.append({'stageIndex': index, 'role': step.get('role'), 'kind': 'guard_violation',
                'ruleId': event.get('ruleId'), 'message': event.get('message')})
        for event in step.get('formatRepairs', []):
            events.append({'stageIndex': index, 'role': step.get('role'), 'kind': 'output_contract', 'message': event.get('error')})
        output = step.get('output') or {}
        if step.get('role') == 'review' and output.get('decision') in {'revise', 'insufficient'}:
            events.append({'stageIndex': index, 'role': 'review', 'kind': 'review_requested_change',
                'message': output.get('summary'), 'modelJudgmentNotGroundTruth': True})
    if run.result.get('taskContract', {}).get('passed') is False:
        events.append({'stageIndex': len(run.steps), 'kind': 'required_product_missing',
            'message': '；'.join(run.result['taskContract'].get('missing', []))})
    templates={'tool_rejected':('未授权或非法工具请求必须被拒绝','reject_invalid_tool_and_preserve_trace'),
        'guard_violation':('结构化断言必须符合原始证据','block_conflicting_claim_without_executing'),
        'output_contract':('错误引用或结构必须显式修正','reject_or_bounded_format_repair'),
        'required_product_missing':('缺少必需取证产品不能标为完成','mark_task_incomplete')}
    candidates=[{'title':templates[e['kind']][0],'expectedHandling':templates[e['kind']][1],
        'sourceRunId':str(run.pk),'stageIndex':e.get('stageIndex'),'evidenceId':e.get('evidenceId'),
        'status':'candidate_requires_review','sourceScope':run.snapshot.get('source'),
        'heldOutEvaluationEligible':False} for e in events if e['kind'] in templates][:8]
    return {'version': 'trajectory-contract-v1', 'runId': str(run.pk), 'events': events,
        'regressionCandidates':candidates,
        'firstRecordedViolation': next((e for e in events if e['kind'] != 'review_requested_change'), None),
        'status': 'recorded_issues' if events else 'not_localized', 'runStatus': run.status,
        'runError': run.error or None, 'source': run.snapshot.get('source'),
        'snapshotHash': run.snapshot.get('sha256'), 'automaticChanges': False,
        'boundary': '借鉴执行轨迹分析；只定位已记录问题，不证明首个违规即最终根因，不自动改规则或发布经验。'}
