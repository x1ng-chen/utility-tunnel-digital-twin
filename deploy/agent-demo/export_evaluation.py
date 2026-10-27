"""Export actual traces and descriptive counts; never invent a factual accuracy score."""
import argparse
from collections import Counter
import csv
import hashlib
import io
import json
import importlib.metadata
from pathlib import Path
import statistics
import zipfile
ROOT=Path(__file__).resolve().parents[2]
parser=argparse.ArgumentParser();parser.add_argument('--secret-env');args=parser.parse_args()
source=ROOT/'.agent-eval-sprint'
target=ROOT/'docs/software-sprint-20261027/evaluation';target.mkdir(exist_ok=True)
secrets=[]
if args.secret_env:
    from dotenv import dotenv_values
    secrets=[v for k,v in dotenv_values(args.secret_env).items() if v and len(v)>=16 and any(t in k for t in ('KEY','SECRET','PASSWORD','TOKEN'))]
manifest=[];summary=[];flat=[]
archive_path=target/'actual-traces.zip'
with zipfile.ZipFile(archive_path,'w',zipfile.ZIP_DEFLATED) as archive:
    for file in sorted(source.rglob('*')):
        if file.parent.name!='runs' or not file.is_file(): continue
        if file.suffix not in {'.json','.jsonl'}: continue
        blob=file.read_bytes();text=blob.decode('utf-8')
        if any(value in text for value in secrets): raise SystemExit('Credential match in '+file.name+'; export stopped.')
        archive.writestr(file.name,blob)
        manifest.append({'path':file.name,'bytes':len(blob),'sha256':hashlib.sha256(blob).hexdigest()})
        if file.suffix!='.jsonl': continue
        rows=[json.loads(line) for line in text.splitlines() if line.strip()]
        for mode in sorted({r['mode'] for r in rows}):
            group=[r for r in rows if r['mode']==mode];elapsed=[];calls=0;known_tokens=0;unknown_usage=0
            for row in group:
                run=row.get('run',{});runtime=run.get('runtime',{});result=run.get('result',{})
                ms=runtime.get('elapsedMs',row.get('elapsedMs'))
                if ms is not None: elapsed.append(ms)
                controlled=row.get('controlledFaultInjection',False)
                calls+=0 if controlled else runtime.get('modelCalls',row.get('modelCalls',0))
                usage=runtime.get('tokens') or row.get('provider',{}).get('usage')
                if usage: known_tokens+=usage.get('total_tokens',0)
                if not controlled and not runtime.get('tokenUsageComplete',bool(row.get('provider',{}).get('usage'))): unknown_usage+=1
                flat.append({'batch':file.name,'caseId':row.get('caseId',row.get('packet','')),'mode':mode,
                    'status':row['status'],'review':result.get('review',{}).get('decision'),'taskOutcome':result.get('taskOutcome'),
                    'providerRequestAttempts':0 if controlled else runtime.get('modelCalls',row.get('modelCalls',0)),
                    'controlledFaultInjection':controlled,'elapsedMs':ms,
                    'proposals':len(result.get('proposals',[])),'error':run.get('error',row.get('error','')),
                    'humanScoring':'PENDING','factAccuracy':None})
            summary.append({'batch':file.name,'mode':mode,'rows':len(group),
                'statuses':dict(Counter(r['status'] for r in group)),
                'reviewDecisions':dict(Counter(r.get('run',{}).get('result',{}).get('review',{}).get('decision','none') for r in group)),
                'modelCalls':calls,'controlledFaultCases':sum(bool(r.get('controlledFaultInjection')) for r in group),
                'knownTotalTokens':known_tokens,'rowsWithUnknownOrIncompleteUsage':unknown_usage,
                'medianElapsedMs':statistics.median(elapsed) if elapsed else None,
                'humanScoring':'PENDING','factualAccuracy':None,'billVerifiedCost':None})
    for pattern in ('live-control-*.json','retrieval-checks.json','browser/result.json','concurrent-soak.json','natural-expiry.json','backup-restore.json'):
        for file in (ROOT/'.agent-demo').glob(pattern):
            blob=file.read_bytes()
            if any(value.encode() in blob for value in secrets): raise SystemExit('Credential match in '+file.name)
            archive.writestr('demo/'+str(file.relative_to(ROOT/'.agent-demo')).replace('\\','/'),blob)
            manifest.append({'path':'demo/'+file.name,'bytes':len(blob),'sha256':hashlib.sha256(blob).hexdigest()})
    model_manifest=ROOT/'.agent-knowledge/model-manifest.json'
    if model_manifest.exists():
        blob=model_manifest.read_bytes();archive.writestr('environment/model-manifest.json',blob)
        manifest.append({'path':'environment/model-manifest.json','bytes':len(blob),'sha256':hashlib.sha256(blob).hexdigest()})
    versions={}
    for name in ('Django','djangorestframework','sentence-transformers','torch','numpy','transformers','huggingface-hub'):
        try: versions[name]=importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError: versions[name]=None
    blob=json.dumps(versions,indent=2).encode();archive.writestr('environment/package-versions.json',blob)
    manifest.append({'path':'environment/package-versions.json','bytes':len(blob),'sha256':hashlib.sha256(blob).hexdigest()})
report={'scope':'descriptive_execution_statistics_not_factual_accuracy','batches':summary,
    'rows':flat,'manualGroup':'NOT_RUN','humanScoring':'PENDING','actualSavingsProven':False,
    'limitations':['样本小且含重测，批次不能合并算准确率。','completed是生命周期结束，不等于复核通过或任务正确。',
        '配对只在同一批次、同case、同snapshotHash下比较。','程序确认不是人工验收。费用按账单核对。']}
(target/'summary.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
(target/'manifest.json').write_text(json.dumps({'archiveSha256':hashlib.sha256(archive_path.read_bytes()).hexdigest(),'files':manifest},ensure_ascii=False,indent=2),encoding='utf-8')
with (target/'human-scoring.csv').open('w',encoding='utf-8-sig',newline='') as stream:
    fields=['caseId','group','reviewer','startTime','endTime','coverageCorrect','identityCorrect','qualityTimeCorrect',
        'factCorrect','citationExists','citationApplicable','candidateAndCounterEvidence','permissionCorrect',
        'workOrderBehaviorCorrect','completedTask','notes']
    writer=csv.DictWriter(stream,fieldnames=fields);writer.writeheader()
    for case in ('INS-01','INS-02','INS-03','INS-04','DIA-01','DIA-02','DIA-03','DIA-04','ORD-01','ORD-02','ORD-03','ORD-04'):
        for group in ('human','ordinary_model','single','multi'): writer.writerow({'caseId':case,'group':group})
md=['# 实际模型与仿真执行记录','','下表为真实请求生命周期统计，**不是人工事实准确率或获奖效果证明**。原始响应、失败、工具轨迹和固定数据包见 `actual-traces.zip`，散列见 `manifest.json`。',
    '','| 批次 | 方式 | 记录数 | 状态统计 | 供应商请求次数（含失败、排除桩） | 已知Token | 耗时中位数 ms |','|---|---|---:|---|---:|---:|---:|']
for row in summary:
    md.append('| '+row['batch']+' | '+row['mode']+' | '+str(row['rows'])+' | '+json.dumps(row['statuses'],ensure_ascii=False)+' | '+str(row['modelCalls'])+' | '+str(row['knownTotalTokens'])+' | '+str(row['medianElapsedMs'])+' |')
md+=['','首次失败和修订后重测分批保留。S05为显式受控超时桩，不计供应商请求或真实模型成绩；权限拒绝也不调用模型。人工组与人工评分未运行；模板见 `human-scoring.csv`。回执为模拟，不能计入真机通过。','',
    '普通问答不使用工具；读取同批原始数据包和手册。单/三Agent有同一总预算；简单巡检只取证，复杂任务才运行三个角色。',
    '独立复核结果与任务完成度另见 `summary.json`。成本不按猜测单价推算，实际账单仍待核对。']
(target/'README.md').write_text('\n'.join(md)+'\n',encoding='utf-8')
print('Exported',len(manifest),'evidence files; credentials excluded; human scores remain pending.')
