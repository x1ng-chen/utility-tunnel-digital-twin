import json
from django.test import SimpleTestCase
from .sprint_output import parse_output,check_output
from .sprint_knowledge import search,local_model
from unittest.mock import patch


class OutputBoundaryTests(SimpleTestCase):
    def test_measurement_citation_must_actually_contain_the_reading(self):
        from .sprint_validation import validate_facts
        assets={'FAN-01':{'asset_code':'FAN-01','readings':[{'metric_key':'rotational.speed','value':0,'unit':'rpm'}]}}
        evidence=[{'id':'E1','status':'ok','data':{'text':'风机手册'}},
            {'id':'E2','status':'ok','data':{'station':{'items':[assets['FAN-01']]}}}]
        fact={'asset_code':'FAN-01','metric_key':'rotational.speed','value':0,'unit':'rpm','evidence_id':'E1'}
        with self.assertRaisesMessage(ValueError,'未包含'): validate_facts({'facts':[fact]},evidence,assets)
        validate_facts({'facts':[{**fact,'evidence_id':'E2'}]},evidence,assets)
        with self.assertRaises(ValueError): validate_facts({'facts':[{**fact,'value':False,'evidence_id':'E2'}]},evidence,assets)
        with self.assertRaises(ValueError): validate_facts({'facts':[{'asset_code':'FAN-01','exists':False}]},evidence,assets)
        for change in ({'controller_id':'CTRL-99'},{'unit':None},{'evidence_id':None}):
            with self.subTest(change=change),self.assertRaises(ValueError):
                validate_facts({'facts':[{**fact,**change}]},evidence,assets)

    def test_rejected_call_is_only_failure_reference(self):
        e=[{'id':'E1','status':'ok'},{'id':'E2','status':'rejected'}]
        value={'summary':'E2拒绝访问；E1为测量','evidence_ids':['E1'],'rejection_ids':['E2']}
        check_output(value,'diagnosis',e,set(),[])
        for key in ('evidence_ids','rejection_ids'):
            wrong={**value,key:['E2'] if key=='evidence_ids' else []}
            with self.assertRaises(ValueError): check_output(wrong,'diagnosis',e,set(),[])

    def test_bad_envelopes_and_duplicate_keys_do_not_become_tool_calls(self):
        for text in ('{"summary":"a","summary":"b"}','{"summary":"a"}\n<DSML>invoke</DSML>',
                     '{"summary":"a","value":NaN}','```json\n{}\n```\n```json\n{}\n```'):
            with self.subTest(text=text),self.assertRaises(ValueError): parse_output(text)
        value,enclosed=parse_output('说明\n```json\n{"summary":"合法封装"}\n```')
        self.assertTrue(enclosed);self.assertEqual(value['summary'],'合法封装')

    def test_wrong_typed_structures_and_knowledge_ids_rejected(self):
        for value in ({'evidence_ids':['K1']},{'missing':'无'},{'request_evidence':[]},{'facts':{}}):
            with self.subTest(value=value),self.assertRaises(ValueError):
                check_output({'summary':'检查',**value},'diagnosis',[],{'K1'},[])

    def test_unverified_clause_edition_and_unrelated_query_abstain(self):
        with patch('operations.sprint_knowledge.local_model',return_value=(None,'test_missing')):
            for query in ('GB50838第999条','GB/T 50838-2015（2015年版）7.5.7','GB/T50838-2030','GB99999-2026第1条','zxqv-93828471'):
                with self.subTest(query=query):
                    result=search(query);self.assertEqual(result['hits'],[]);self.assertEqual(result['answerability'],'no_supported_answer')
            result=search('GB/T50838-2015（2024年版）7.5.7火灾通风')
            self.assertTrue(result['hits']);self.assertTrue(all(r['clause']=='7.5.7' and r['editionYear']==2024 for r in result['hits']))
            self.assertTrue(search('5.3.2通风状态')['hits'])

    def test_old_frozen_knowledge_does_not_use_new_dense_index(self):
        from .sprint_scoring import digest
        docs=[{'id':'K1','sourceKind':'internal_guidance','text':'风机转速反馈','source':'frozen-test','version':'TEST_OLD'}]
        with patch('operations.sprint_knowledge.local_model',return_value=(object(),None)),patch('operations.sprint_knowledge.embeddings') as dense:
            result=search('风机',documents=docs)
            self.assertEqual(result['knowledgeVersion'],digest(docs));self.assertEqual(result['fallbackReason'],'frozen_corpus_differs_from_loaded_index')
            self.assertEqual(result['mode'],'keyword_fallback');dense.assert_not_called()
