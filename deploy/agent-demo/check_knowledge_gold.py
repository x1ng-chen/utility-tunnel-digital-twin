"""Local retrieval only; gold target matching is not model-answer accuracy."""
import argparse
from contextlib import nullcontext
import json
import os
from pathlib import Path
import sys
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'backend'))
os.environ.setdefault('DJANGO_SETTINGS_MODULE','config.agent_demo_settings')
import django
django.setup()
from operations.sprint_knowledge import search,version,model_fingerprint


def main():
    p=argparse.ArgumentParser();p.add_argument('--keyword-only',action='store_true');p.add_argument('--output',type=Path)
    args=p.parse_args();rows=[]
    cases=json.loads((ROOT/'docs/agent-evidence-quality-20261027/knowledge-gold.json').read_text(encoding='utf-8'))
    with patch('operations.sprint_knowledge.local_model',return_value=(None,'explicit_keyword_test')) if args.keyword_only else nullcontext():
        for case in cases:
            result=search(case['query']);hits=result['hits']
            matched=[h for h in hits if h.get('clause')==case.get('clause') and case.get('standard','') in h.get('standard','')]
            checks={'targetOrAbstention':not hits if case.get('noAnswer') else bool(matched),
                'sourceMetadata':all(h.get('bodyVerified') and h.get('sha256') and h.get('source') and (h.get('page') or h.get('sectionUrl')) for h in matched),
                'referenceOnly':all(h.get('applicability')=='reference_only_not_automatic_control_policy' for h in matched),
                'noSilentLegacy':all(h['sourceKind']!='historical_case' for h in hits)}
            rows.append({**case,'passed':all(checks.values()),'checks':checks,'retrieval':result})
    report={'scope':'retrieval_top5_target_and_abstention_not_semantic_answer_or_human_score',
        'knowledgeVersion':version(),'embeddingFingerprint':None if args.keyword_only else model_fingerprint(),
        'passed':sum(r['passed'] for r in rows),'total':len(rows),'rows':rows}
    output=args.output or ROOT/'.agent-demo'/('knowledge-gold-keyword.json' if args.keyword_only else 'knowledge-gold-hybrid.json')
    output.parent.mkdir(parents=True,exist_ok=True);output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'passed':report['passed'],'total':report['total'],'modes':sorted({r['retrieval']['mode'] for r in rows}),
        'failed':[r['id'] for r in rows if not r['passed']],'output':str(output)}))
    return 0 if report['passed']==report['total'] else 1


if __name__=='__main__': sys.exit(main())
