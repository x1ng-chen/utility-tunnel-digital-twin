"""Package the two offline review bundles; never include runtime credentials."""
import hashlib
import json
from pathlib import Path
import zipfile
from dotenv import dotenv_values
ROOT=Path(__file__).resolve().parents[2]
TARGET=ROOT/'docs/agent-evidence-quality-20261027'


def main():
    values=[]
    for path in (ROOT/'.agent-demo/.env',ROOT/'backend/.env'):
        if path.is_file():
            values.extend(v.encode() for k,v in dotenv_values(path).items() if v and len(v)>=16 and any(s in k for s in ('KEY','TOKEN','PASSWORD','SECRET')))
    manifest=[];destination=TARGET/'review-bundles.zip'
    # Explicit allowlist; do not walk the runtime directory containing .env/DBs.
    folders={'composite':ROOT/'.agent-demo/review-quality-v2','regression':ROOT/'.agent-demo/review-regression-v2'}
    with zipfile.ZipFile(destination,'w',zipfile.ZIP_DEFLATED) as z:
        for label,folder in folders.items():
            for file in sorted(folder.rglob('*')):
                if not file.is_file(): continue
                if file.suffix not in {'.json','.csv'}: raise ValueError('Unexpected bundle type: '+file.name)
                data=file.read_bytes()
                if any(secret in data for secret in values): raise ValueError('Credential detected; export stopped.')
                path=label+'/'+file.relative_to(folder).as_posix();z.writestr(path,data)
                manifest.append({'path':path,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()})
        data=(TARGET/'review-protocol.md').read_bytes();z.writestr('review-protocol.md',data)
        manifest.append({'path':'review-protocol.md','bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()})
    report={'archiveSha256':hashlib.sha256(destination.read_bytes()).hexdigest(),'files':manifest,
        'sourceArchive':'docs/software-sprint-20261027/evaluation/actual-traces.zip',
        'scope':'12_composite_and_30_regression_historical_packets_and_blank_review_forms',
        'historicalResponses':66,'caseCount':42,'independentHumanScores':0,'humanGroup':'NOT_RUN',
        'newPaidRequests':0,'credentialsMatched':False}
    (TARGET/'review-bundle-manifest.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'files':len(manifest),'bytes':destination.stat().st_size,'newPaidRequests':0,'credentialsMatched':False}))


if __name__=='__main__': main()
