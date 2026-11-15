import copy
import json
import unittest
from unittest.mock import patch
import httpx
from support_ticket_ai.anchored_grouping import expand_anchors,anchor_schema,AnchoredStagedProposer
from support_ticket_ai.staged_proposals import MeaningPlan
from support_ticket_ai.proposals import ProposalFailure,align_fragment_plan

FIRST={'fragments':[{'fragment_id':'part-1','role':'negated','category':'REFUND'},{'fragment_id':'part-2','role':'request','category':'ORDER'}]}
OUTPUT={'groups':[{'anchor_fragment_id':'part-2','title':'Find order number','fragment_ids':['part-2']}],'ungrouped':['part-1'],'clarification':''}
TEXT='Do not refund it. Find my order number.'
class AnchorTests(unittest.TestCase):
    def test_active_anchor_enum_and_runtime_rejection(self):
        meanings=MeaningPlan.model_validate(FIRST)
        self.assertEqual(anchor_schema(meanings)['$defs']['AnchoredGroup']['properties']['anchor_fragment_id']['enum'],['part-2'])
        bad=copy.deepcopy(OUTPUT);bad['groups'][0].update(anchor_fragment_id='part-1',fragment_ids=['part-1']);bad['ungrouped']=['part-2']
        with self.assertRaises(ProposalFailure):expand_anchors(meanings,bad)
        review=align_fragment_plan(TEXT,expand_anchors(meanings,OUTPUT))
        self.assertEqual([g['category'] for g in review['groups']],['ORDER'])

    def test_required_note_in_schema_and_validator(self):
        meanings=MeaningPlan.model_validate({'fragments':[{'fragment_id':'part-1','role':'conditional','category':'REFUND'}]})
        self.assertEqual(anchor_schema(meanings)['properties']['clarification']['minLength'],1)
        raw={'groups':[{'anchor_fragment_id':'part-1','title':'Conditional refund','fragment_ids':['part-1']}],'ungrouped':[],'clarification':' '}
        with self.assertRaises(ProposalFailure) as caught:expand_anchors(meanings,raw)
        self.assertEqual(caught.exception.validation_code,'clarification_missing')
        raw['clarification']='Refund only if delivery fails.'
        self.assertEqual(expand_anchors(meanings,raw)['segments'][0]['role'],'conditional')

    def test_excluded_only_can_return_no_groups(self):
        meanings=MeaningPlan.model_validate({'fragments':[FIRST['fragments'][0]]})
        self.assertEqual(anchor_schema(meanings)['properties']['groups']['maxItems'],0)
        self.assertEqual(expand_anchors(meanings,{'groups':[],'ungrouped':['part-1'],'clarification':''})['groups'],[])

    def test_duplicate_missing_and_active_ungrouped_rejected(self):
        for mode in ['duplicate','missing','active_ungrouped']:
            raw=copy.deepcopy(OUTPUT)
            if mode=='duplicate':raw['groups'][0]['fragment_ids'].append('part-2')
            if mode=='missing':raw['ungrouped']=[]
            if mode=='active_ungrouped':raw.update(groups=[],ungrouped=['part-1','part-2'])
            with self.assertRaises(ProposalFailure):expand_anchors(MeaningPlan.model_validate(FIRST),raw)

    def test_transport_preserves_evidence_and_experimental_identity(self):
        original=httpx.Client;calls=[]
        def handler(request):
            if request.url.path=='/api/tags':return httpx.Response(200,json={'models':[{'name':'local:latest','digest':'a'*64,'details':{'format':'gguf'}}]})
            calls.append(json.loads(request.content))
            return httpx.Response(200,json={'model':'local:latest','done':True,'done_reason':'stop','message':{'content':json.dumps(FIRST if len(calls)==1 else OUTPUT)}})
        with patch('support_ticket_ai.proposals.httpx.Client',side_effect=lambda **kw:original(transport=httpx.MockTransport(handler),**kw)):
            result=AnchoredStagedProposer('local',role_prompt='focused').propose(TEXT)
        self.assertEqual((result['prompt_version'],result['grouping_contract']),(8,'anchored'))
        self.assertTrue(result['requires_human_review'])
        self.assertEqual(result['review']['source_text'],TEXT)
