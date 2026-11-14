import copy
import json
import unittest
from unittest.mock import patch
import httpx
from support_ticket_ai.compact_grouping import expand_memberships,CompactStagedProposer
from support_ticket_ai.staged_proposals import MeaningPlan
from support_ticket_ai.proposals import ProposalFailure,ProposalOutputError,align_fragment_plan

TEXT='Cancel order A. Keep order B.'
MEANINGS={'fragments':[{'fragment_id':'part-1','role':'request','category':'ORDER'},{'fragment_id':'part-2','role':'request','category':'ORDER'}]}
PLAN={'memberships':[{'fragment_id':'part-1','group_id':'need-1'},{'fragment_id':'part-2','group_id':'need-2'}],'groups':[{'id':'need-1','title':'Cancel A'},{'id':'need-2','title':'Keep B'}],'clarification':''}

class MembershipTests(unittest.TestCase):
    def expand(self,plan=None,meanings=None):
        return expand_memberships(MeaningPlan.model_validate(meanings or MEANINGS),plan or PLAN)

    def test_labels_derived_and_targets_stay_separate(self):
        review=align_fragment_plan(TEXT,self.expand())
        self.assertEqual([g['category'] for g in review['groups']],['ORDER','ORDER'])
        self.assertEqual([g['title'] for g in review['groups']],['Cancel A','Keep B'])

    def test_excluded_only_evidence_creates_no_need(self):
        meanings={'fragments':[{'fragment_id':'part-1','role':'negated','category':'REFUND'}]}
        plan={'memberships':[{'fragment_id':'part-1','group_id':None}],'groups':[],'clarification':''}
        review=align_fragment_plan('Do not refund it.',self.expand(plan,meanings))
        self.assertEqual(review['groups'],[])
        plan['groups']=[{'id':'need-1','title':'Refund'}];plan['memberships'][0]['group_id']='need-1'
        with self.assertRaises(ProposalFailure) as error:self.expand(plan,meanings)
        self.assertEqual(error.exception.validation_code,'empty_need')

    def test_roles_categories_and_unknown_fields_cannot_be_supplied(self):
        for field,value in [('role','context'),('category','REFUND'),('text','invented')]:
            plan=copy.deepcopy(PLAN);plan['memberships'][0][field]=value
            with self.assertRaises(ProposalFailure):self.expand(plan)

    def test_invalid_memberships_rejected(self):
        for variant in ['duplicate','unknown','unassigned','mixed']:
            plan=copy.deepcopy(PLAN);meanings=copy.deepcopy(MEANINGS)
            if variant=='duplicate':plan['memberships'][1]['fragment_id']='part-1'
            if variant=='unknown':plan['memberships'][1]['group_id']='need-9'
            if variant=='unassigned':plan['memberships'][1]['group_id']=None
            if variant=='mixed':
                plan['memberships'][1]['group_id']='need-1';plan['groups'].pop();meanings['fragments'][1]['category']='REFUND'
            with self.assertRaises(ProposalFailure):self.expand(plan,meanings)

    def test_condition_still_requires_explicit_note(self):
        meanings={'fragments':[{'fragment_id':'part-1','role':'conditional','category':'REFUND'}]}
        plan={'memberships':[{'fragment_id':'part-1','group_id':'need-1'}],'groups':[{'id':'need-1','title':'Conditional refund'}],'clarification':''}
        with self.assertRaises(ProposalOutputError):align_fragment_plan('If delivery fails, refund it.',self.expand(plan,meanings))

    def test_transport_uses_compact_schema_then_normal_evidence_checks(self):
        original=httpx.Client;calls=[]
        def handler(request):
            if request.url.path=='/api/tags':return httpx.Response(200,json={'models':[{'name':'local:latest','digest':'a'*64,'details':{'format':'gguf'}}]})
            calls.append(json.loads(request.content))
            return httpx.Response(200,json={'model':'local:latest','done':True,'done_reason':'stop','message':{'content':json.dumps(MEANINGS if len(calls)==1 else PLAN)}})
        with patch('support_ticket_ai.proposals.httpx.Client',side_effect=lambda **kw:original(transport=httpx.MockTransport(handler),**kw)):
            result=CompactStagedProposer('local',role_prompt='focused').propose(TEXT)
        self.assertEqual(result['prompt_version'],6)
        self.assertEqual(result['grouping_contract'],'memberships')
        self.assertEqual(result['role_prompt'],'focused')
        self.assertEqual(set(calls[1]['format']['properties']),{'memberships','groups','clarification'})
        self.assertTrue(result['requires_human_review'])

    def test_structure_still_does_not_guarantee_correct_grouping(self):
        plan=copy.deepcopy(PLAN);plan['memberships'][1]['group_id']='need-1';plan['groups'].pop()
        self.assertEqual(len(align_fragment_plan(TEXT,self.expand(plan))['groups']),1)
