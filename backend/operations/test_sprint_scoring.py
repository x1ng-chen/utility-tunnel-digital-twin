import csv
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from django.test import SimpleTestCase
from .sprint_scoring import DIMENSIONS,dump,score_bundle,pair_eligibility,import_human


class ScoringTests(SimpleTestCase):
    def test_all_42_cases_have_maintainer_rubrics(self):
        from .sprint_scoring import RUBRICS
        from .agent_evaluation import entries
        self.assertEqual(set(RUBRICS),{r['id'] for suite in ('composite','regression') for r in entries(suite)})

    def row(self):
        return {'blindId':'abc','caseId':'DIA-01','group':'multi','snapshotHash':'s','packetSha256':'p',
            'knowledgeVersion':'k','codeFingerprint':'c','budget':{'modelCalls':12},'actualModels':['same-model'],
            'createHttpStatus':202}

    def score(self,entries):
        with TemporaryDirectory() as directory:
            root=Path(directory);dump(root/'heldout-key.json',{'rows':[self.row()],'humanGroup':'NOT_RUN'})
            fields=['blindId','reviewerId','reviewerKind','startedAt','endedAt',*DIMENSIONS,'evidenceNotes','attestation']
            with (root/'ratings.csv').open('w',encoding='utf-8',newline='') as f:
                w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(entries)
            return score_bundle(root,root/'ratings.csv')

    def rating(self):
        return {'blindId':'abc','reviewerId':'r1','reviewerKind':'assistant_review','startedAt':'2026-10-27T01:00:00Z',
            'endedAt':'2026-10-27T01:01:00Z','evidenceNotes':'E1的原始量不是ppm。','attestation':'I_REVIEWED_THIS_RESPONSE',
            **{d:'2' for d in DIMENSIONS}}

    def test_pending_is_not_zero_or_human_score(self):
        r=self.score([{'blindId':'abc'}]);self.assertEqual(r['pendingRows'],1);self.assertEqual(r['groups'],{})
        self.assertIsNone(r['humanFactAccuracy']);self.assertEqual(r['independentHumanRatings'],0)

    def test_assistant_scores_separate_and_na_excluded(self):
        rating=self.rating();rating['diagnostic_reasoning']='NA';r=self.score([rating])
        self.assertEqual(r['independentHumanRatings'],0);self.assertNotIn('diagnostic_reasoning',r['groups']['assistant_review:multi']['dimensions'])

    def test_invalid_duplicate_unsigned_and_partial_ratings_rejected(self):
        for change in ({'facts':''},{'endedAt':'2026-10-27T00:59:00Z'},{'startedAt':'2026-10-27T01:00:00'},
                       {'attestation':''},{'reviewerKind':'model_pretending_human'},{'blindId':'unknown'}):
            with self.subTest(change=change),self.assertRaises(ValueError): self.score([{**self.rating(),**change}])
        with self.assertRaises(ValueError): self.score([self.rating(),self.rating()])

    def test_pairs_require_identical_snapshot_model_and_budget(self):
        row=self.row();self.assertEqual(pair_eligibility(row,row),[])
        for field in ('snapshotHash','packetSha256','knowledgeVersion','codeFingerprint','budget','actualModels'):
            with self.subTest(field=field): self.assertTrue(pair_eligibility(row,{**row,field:None}))
        self.assertIn('controlled_stub',pair_eligibility(row,{**row,'controlledStub':True}))

    def test_human_import_keeps_source_and_no_independent_score(self):
        with TemporaryDirectory() as directory:
            root=Path(directory);dump(root/'heldout-key.json',{'rows':[self.row()],'humanGroup':'NOT_RUN'})
            value={'caseId':'DIA-01','snapshotHash':'s','operatorId':'TEST_FIXTURE_NOT_REAL_PARTICIPANT',
                'startedAt':'2026-10-27T00:00:00Z','endedAt':'2026-10-27T00:01:00Z','responseText':'测试夹具回答',
                'operationEvidence':'TEST_FIXTURE_NO_ACTUAL_OPERATION','priorExposure':'none'}
            with (root/'human.csv').open('w',encoding='utf-8',newline='') as f:
                w=csv.DictWriter(f,fieldnames=list(value));w.writeheader();w.writerow(value)
            result=import_human(root,root/'human.csv');self.assertEqual(result['importedHumanResponses'],1)
            self.assertEqual(result['independentHumanRatings'],0)
            self.assertEqual(score_bundle(root,root/'human-ratings.csv')['groups'],{})
            with self.assertRaises(ValueError): import_human(root,root/'human.csv')

    def test_empty_human_sheet_does_not_become_experiment(self):
        with TemporaryDirectory() as directory:
            root=Path(directory);dump(root/'heldout-key.json',{'rows':[self.row()],'humanGroup':'NOT_RUN'})
            (root/'human.csv').write_text('caseId,snapshotHash,operatorId\nDIA-01,s,\n',encoding='utf-8')
            result=import_human(root,root/'human.csv');self.assertEqual(result['importedHumanResponses'],0)
            self.assertEqual(result['humanGroup'],'NOT_RUN')
