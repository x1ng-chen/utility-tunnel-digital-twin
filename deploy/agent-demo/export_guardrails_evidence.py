"""Export only explicit offline fixtures; never a database, account file or key."""
import argparse
import hashlib
import json
from pathlib import Path
import statistics
import zipfile

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'docs'/'guardrails-experience-20261027'


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--run',required=True,help='Name under .agent-eval-guards/runs')
    options=parser.parse_args()
    base=(ROOT/'.agent-eval-guards'/'runs').resolve();folder=(base/options.run).resolve()
    if folder.parent!=base: raise ValueError('Expected one isolated run directory.')
    report=json.loads((folder/'report.json').read_text(encoding='utf-8'))
    rows=report['rows']
    if len(rows)!=100 or any(r['executionMode']!='EXPLICIT_OFFLINE_STUB' for r in rows):
        raise ValueError('Only the 25-case, four-arm explicit offline packet is exportable here.')
    if not all(r['contractFixturePassed'] and r['noUnconfirmedWrite'] for r in rows):
        raise ValueError('Inspect failing fixtures before publishing a passing release.')
    for case in {r['caseId'] for r in rows}:
        group=[r for r in rows if r['caseId']==case]
        if len(group)!=4 or len({r['observationHash'] for r in group})!=1:
            raise ValueError('Four arms must share observations.')
        for memory in ('off','approved'):
            pair=[r for r in group if r['experienceMode']==memory]
            if len({r['snapshotHash'] for r in pair})!=1: raise ValueError('Pair snapshot mismatch.')
    if report['training']['observationHash'] in {r['observationHash'] for r in rows}:
        raise ValueError('Training and held-out observations overlap.')
    paths=[*(ROOT/'backend'/'operations').rglob('*.py'),*(ROOT/'backend'/'config').glob('*.py'),
        *(ROOT/'backend'/'operations'/'agent_catalog').glob('*.json')]
    fingerprint=hashlib.sha256()
    for path in sorted(paths):
        fingerprint.update(path.relative_to(ROOT/'backend').as_posix().encode()+b'\0')
        fingerprint.update(path.read_bytes().replace(b'\r\n',b'\n')+b'\0')
    if fingerprint.hexdigest()!=report['codeFingerprint']:
        raise ValueError('Backend code changed after the recorded run; repeat the offline matrix.')
    OUT.mkdir(parents=True,exist_ok=True)
    payload={p.name:p.read_bytes() for p in sorted(folder.glob('J??-memory-*-packet.json'))}
    for name in ('report.json','records.jsonl'): payload[name]=(folder/name).read_bytes()
    for name,count in (('legacy-composite-catalog.json',12),('legacy-regression-catalog.json',30)):
        content=(ROOT/'.agent-eval-guards'/name).read_bytes()
        if len(json.loads(content)['cases'])!=count: raise ValueError('Legacy case catalog mismatch.')
        payload[name]=content
    # Exact-value scan against local secrets. Do not print their values.
    from dotenv import dotenv_values
    secrets=[v for k,v in dotenv_values(ROOT/'.agent-demo'/'.env').items()
        if v and len(v)>=12 and k in {'DEEPSEEK_API_KEY','DJANGO_SECRET_KEY'}]
    account_file=ROOT/'.agent-eval-guards'/'users.json'
    secrets+=list(json.loads(account_file.read_text(encoding='utf-8')).values())
    for content in payload.values():
        if any(isinstance(s,str) and len(s)>=12 and s.encode() in content for s in secrets):
            raise ValueError('A local credential matched; export refused.')
    manifest={n:hashlib.sha256(b).hexdigest() for n,b in payload.items()}
    payload['manifest.json']=json.dumps(manifest,indent=2).encode()
    archive=OUT/'offline-records.zip'
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as output:
        for name,content in payload.items(): output.writestr(name,content)
    result={'scope':report['scope'],'executionMode':'EXPLICIT_OFFLINE_STUB','rows':len(rows),
        'codeFingerprint':report['codeFingerprint'],'guardVersion':report['guardVersion'],
        'training':report['training'],'experienceArms':{},'providerRequests':0,
        'realModelResults':'NOT_RUN','historicalResponseReplay':'NOT_RUN_THIS_RELEASE',
        'humanApproval':'NO_HUMAN_APPROVAL_IN_PUBLISHED_FIXTURES','actualMemoryBenefit':None,
        'tokens':None,'billVerifiedCost':None,'archiveSha256':hashlib.sha256(archive.read_bytes()).hexdigest()}
    for memory in ('off','approved'):
        result['experienceArms'][memory]=report['experienceArms'][memory]['groups']
        for arm in ('single','multi'):
            selected=[r for r in rows if r['experienceMode']==memory and r['mode']==arm]
            values=result['experienceArms'][memory][arm]
            values.update(boundaryCases=1,legalTasksCompleted=sum(r['run']['status']=='completed' for r in selected if r['expected']=='allow'),
                fixtureChecksPassed=sum(r['contractFixturePassed'] for r in selected),
                stubElapsedMedianMs=statistics.median(r['run']['runtime']['elapsedMs'] for r in selected),
                loadedExperienceCounts=sorted({r['loadedExperiences'] for r in selected}))
    (OUT/'offline-summary.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'rows':len(rows),'files':len(payload),'archiveBytes':archive.stat().st_size,'credentialScan':'PASS'},ensure_ascii=False))


if __name__=='__main__': main()
