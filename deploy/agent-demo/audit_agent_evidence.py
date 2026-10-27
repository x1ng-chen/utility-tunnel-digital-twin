"""Offline audit/replay of immutable recordings. No network, ORM or model calls."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys
import zipfile
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'backend'))
from operations.sprint_output import parse_output,check_output


def category(row):
    run=row.get('run',{});runtime=run.get('runtime',{});result=run.get('result',{})
    if row.get('controlledFaultInjection') or 'CONTROLLED_TIMEOUT' in run.get('error',''): return 'controlled_stub_not_provider'
    if row.get('createHttpStatus')==403: return 'server_permission_denied_no_model'
    codes=[c.get('providerHttpStatus') for c in runtime.get('calls',[])]+[row.get('providerHttpStatus')]
    if 402 in codes: return 'provider_balance_402'
    if any(c in (401,403) for c in codes): return 'provider_authentication'
    error=run.get('error',row.get('error',''))
    if error:
        if any(x in error for x in ('Expecting','Extra data','summary','JSON')): return 'output_format'
        if '引用' in error: return 'citation_contract'
        if '取证未调用' in error: return 'missing_tool_read'
        return 'other_failure_or_unattributed_transport'
    if result.get('taskOutcome') in {'unresolved_review','no_confirmable_draft','no_confirmable_action','incomplete'}: return 'incomplete_business_task'
    return 'lifecycle_finished_not_accuracy_scored'


def audit(archive):
    rows=[];replays=[]
    with zipfile.ZipFile(archive) as z:
        for name in sorted(z.namelist()):
            if not name.endswith('.jsonl'): continue
            for line,indexed in enumerate(z.read(name).decode('utf-8').splitlines(),1):
                row=json.loads(indexed);run=row.get('run',{});result=run.get('result',{})
                flat={'batch':name,'line':line,'caseId':row.get('caseId',row.get('packet')),'mode':row.get('mode'),
                    'category':category(row),'lifecycleStatus':row.get('status'),
                    'taskOutcome':result.get('taskOutcome'),'reviewDecision':result.get('review',{}).get('decision'),
                    'error':run.get('error',row.get('error','')),'humanFactScore':None}
                rows.append(flat)
                evidence=[];knowledge=set()
                for step in run.get('steps',[]):
                    pending=iter(step.get('traces',[]));stage_traces=[]
                    for i,call in enumerate(step.get('calls',[])):
                        message=call.get('message') or {};text=message.get('content')
                        if message.get('tool_calls'):
                            for tool in message['tool_calls']:
                                trace=next(pending,None)
                                if trace is None: break # malformed call may have stopped before execution
                                if trace['tool']!=tool.get('function',{}).get('name'):
                                    raise ValueError('Cannot reconstruct recorded tool order; do not assume future evidence was available.')
                                evidence.append(trace);stage_traces.append(trace)
                                if trace['tool']=='knowledge_search' and trace['status']=='ok':
                                    knowledge.update(h['id'] for h in trace['data'].get('hits',[]))
                        if not text or message.get('tool_calls'): continue
                        try:
                            output,enclosed=parse_output(text)
                            check_output(output,step['role'],evidence,knowledge,stage_traces,
                                known_guard_ids={f['id'] for f in result.get('guardrails',{}).get('findings',[])})
                            verdict='accepted_format_and_reference_shape_only';error=None
                        except (ValueError,TypeError) as exc: verdict='rejected';error=str(exc)
                        replays.append({'batch':name,'caseId':row.get('caseId'),'mode':row.get('mode'),
                            'role':step['role'],'callIndex':i,'replySha256':hashlib.sha256(text.encode()).hexdigest(),
                            'verdict':verdict,'error':error})
    return {'scope':'historical_failure_triage_and_recorded_final_reply_validation_not_new_model_evaluation',
        'sourceArchiveSha256':hashlib.sha256(Path(archive).read_bytes()).hexdigest(),
        'counts':dict(Counter(r['category'] for r in rows)),'rows':rows,'replyReplays':replays,
        'replayCounts':dict(Counter(r['verdict'] for r in replays)),
        'humanFactScore':None,'newPaidRequests':0,
        'limitations':['不同代码批次和重测不能合并为准确率。',
            '离线重放检查最终回复的格式与引用形状，不重放供应商推理，不能证明新模型会正确调用工具。',
            '旧普通问答包仅附初始top5知识，和Agent可检索全库的信息范围不一致；不据此发布RAG收益。',
            '无HTTP码的旧错误不能全部归因为余额，生命周期结束不等于任务正确。']}


def main():
    p=argparse.ArgumentParser();p.add_argument('--archive',type=Path,default=ROOT/'docs/software-sprint-20261027/evaluation/actual-traces.zip')
    p.add_argument('--output',type=Path,default=ROOT/'docs/agent-evidence-quality-20261027/failure-audit.json');args=p.parse_args()
    report=audit(args.archive);args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'records':len(report['rows']),'categories':report['counts'],'replay':report['replayCounts'],'newPaidRequests':0},ensure_ascii=False))


if __name__=='__main__': main()
