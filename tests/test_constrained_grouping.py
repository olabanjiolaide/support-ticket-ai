import json
import unittest
from unittest.mock import patch
import httpx
from support_ticket_ai.constrained_grouping import assignment_schema,expand_assignments,ConstrainedStagedProposer
from support_ticket_ai.staged_proposals import MeaningPlan
from support_ticket_ai.proposals import ProposalFailure,align_fragment_plan

MEANINGS={'fragments':[{'fragment_id':'part-1','role':'negated','category':'REFUND'},{'fragment_id':'part-2','role':'request','category':'ORDER'}]}
OUTPUT={'assignments':{'part-2':'need-1','part-1':None},'groups':[{'id':'need-1','title':'Find order number'}],'clarification':''}
TEXT='Do not refund it. Find my order number.'

class ConstrainedTests(unittest.TestCase):
    def test_schema_requires_exact_source_keys_and_nonnull_active_assignment(self):
        schema=assignment_schema(MeaningPlan.model_validate(MEANINGS))['properties']['assignments']
        self.assertFalse(schema['additionalProperties'])
        self.assertEqual(schema['required'],['part-1','part-2'])
        self.assertEqual(schema['properties']['part-2']['type'],'string')
        self.assertIn({'type':'null'},schema['properties']['part-1']['anyOf'])

    def test_object_order_restores_original_evidence(self):
        plan=expand_assignments(MeaningPlan.model_validate(MEANINGS),OUTPUT)
        review=align_fragment_plan(TEXT,plan)
        self.assertEqual([p['role'] for p in review['parts']],['negated','request'])
        self.assertEqual(review['groups'][0]['category'],'ORDER')

    def test_null_active_rejected_with_text_free_diagnostics(self):
        raw={**OUTPUT,'assignments':{'part-1':None,'part-2':None}}
        with self.assertRaises(ProposalFailure) as caught:expand_assignments(MeaningPlan.model_validate(MEANINGS),raw)
        self.assertEqual(caught.exception.diagnostics,{'stage':'membership_validation','fragment_id':'part-2','classified_role':'request','classified_category':'ORDER'})
        self.assertNotIn(TEXT,str(caught.exception.diagnostics))

    def test_missing_and_invented_keys_rejected(self):
        for assignments in [{'part-1':None},{'part-1':None,'part-2':'need-1','part-9':None}]:
            with self.assertRaises(ProposalFailure):expand_assignments(MeaningPlan.model_validate(MEANINGS),{**OUTPUT,'assignments':assignments})

    def test_transport_selects_constrained_schema_and_keeps_human_review(self):
        original=httpx.Client;calls=[]
        def handler(request):
            if request.url.path=='/api/tags':return httpx.Response(200,json={'models':[{'name':'local:latest','digest':'a'*64,'details':{'format':'gguf'}}]})
            calls.append(json.loads(request.content))
            return httpx.Response(200,json={'model':'local:latest','done':True,'done_reason':'stop','message':{'content':json.dumps(MEANINGS if len(calls)==1 else OUTPUT)}})
        with patch('support_ticket_ai.proposals.httpx.Client',side_effect=lambda **kw:original(transport=httpx.MockTransport(handler),**kw)):
            result=ConstrainedStagedProposer('local',role_prompt='focused').propose(TEXT)
        self.assertEqual((result['prompt_version'],result['grouping_contract']),(7,'constrained'))
        self.assertTrue(result['requires_human_review'])
        self.assertIn('assignments',calls[1]['format']['properties'])
