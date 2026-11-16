import copy
import json
import unittest
from unittest.mock import patch
import httpx
from support_ticket_ai.question_comparison import saved_messages,compare_questions,summarize,VARIANTS
from support_ticket_ai.proposals import OllamaProposer
from support_ticket_ai.combined_pilot import QUESTION_SYSTEMS

class QuestionComparisonTests(unittest.TestCase):
    def report(self):
        return {'evaluation_mode':'combined_conditions_questions','cases':[
            {'id':'a','proposal':{'review':{'source_text':'Either cancel order T or keep it active.'}}},
            {'id':'b','proposal':{'review':{'source_text':'Keep order U open.'}}}]}

    def test_missing_source_and_duplicates_rejected(self):
        for kind in ['missing','duplicate']:
            report=self.report()
            if kind=='missing':report['cases'][1]={'id':'b','valid_structured_response':False}
            else:report['cases'][1]['id']='a'
            with self.subTest(kind=kind),self.assertRaises(ValueError):saved_messages(report)

    def test_same_payload_schema_options_alternating_prompts_failures_retained(self):
        original=httpx.Client;calls=[]
        def handler(request):
            if request.url.path=='/api/tags':return httpx.Response(200,json={'models':[{'name':'local:latest','digest':'a'*64,'details':{'format':'gguf'}}]})
            self.assertEqual(request.url.path,'/api/chat')
            calls.append(json.loads(request.content))
            return httpx.Response(200,json={'model':'local:latest','done':True,'done_reason':'length' if len(calls)==1 else 'stop',
                'message':{'content':json.dumps({'decision':'none','reason':'none','evidence_parts':[],'text':''})}})
        with patch('support_ticket_ai.proposals.httpx.Client',side_effect=lambda **kw:original(transport=httpx.MockTransport(handler),**kw)):
            rows=compare_questions(OllamaProposer('local'),saved_messages(self.report()),'a'*64)
        self.assertEqual(len(calls),4)
        self.assertEqual(rows[0]['variant_order'],list(VARIANTS))
        self.assertEqual(rows[1]['variant_order'],list(reversed(VARIANTS)))
        for offset in [0,2]:
            left,right=copy.deepcopy(calls[offset:offset+2])
            self.assertEqual(left['messages'][1],right['messages'][1])
            left['messages'][0]['content']=right['messages'][0]['content']='SYSTEM'
            self.assertEqual(left,right)
        self.assertTrue(calls[0]['messages'][0]['content'].startswith(QUESTION_SYSTEMS[VARIANTS[0]]))
        self.assertFalse(rows[0]['both_valid'])
        self.assertTrue(rows[1]['both_valid'])
        self.assertEqual(summarize(rows)['variants'][VARIANTS[0]]['failed'],1)
        self.assertEqual(summarize(rows)['attempted_pairs'],2)
