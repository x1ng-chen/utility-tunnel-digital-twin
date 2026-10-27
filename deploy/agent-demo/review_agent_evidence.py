"""Create source-bound human review bundles or import completed rating sheets."""
import argparse
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'backend'))
from operations.sprint_scoring import build_bundle,score_bundle,import_human,dump


def main():
    p=argparse.ArgumentParser();sub=p.add_subparsers(dest='command',required=True)
    b=sub.add_parser('build');b.add_argument('--archive',type=Path,default=ROOT/'docs/software-sprint-20261027/evaluation/actual-traces.zip')
    b.add_argument('--batch',default='20261027T005814Z');b.add_argument('--output',required=True,type=Path)
    s=sub.add_parser('score');s.add_argument('--bundle',required=True,type=Path);s.add_argument('--ratings',required=True,type=Path);s.add_argument('--output',required=True,type=Path)
    h=sub.add_parser('add-human');h.add_argument('--bundle',required=True,type=Path);h.add_argument('--responses',required=True,type=Path)
    a=p.parse_args()
    if a.command=='build': result=build_bundle(a.archive,a.batch,a.output)
    elif a.command=='add-human': result=import_human(a.bundle,a.responses)
    else: result=score_bundle(a.bundle,a.ratings);dump(a.output,result)
    print(json.dumps(result,ensure_ascii=False))


if __name__=='__main__': main()
