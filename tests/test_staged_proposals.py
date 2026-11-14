import copy
import json
import unittest
from unittest.mock import patch
import httpx
from support_ticket_ai.staged_proposals import StagedProposer
from support_ticket_ai.proposals import ProposalFailure

TEXT='Find my order number and also check my refund.'
DIGEST='a'*64
FIRST={'fragments':[{'fragment_id':'part-1','role':'request','category':'ORDER'}, {'fragment_id':'part-2','role':'request','category':'REFUND'}]}
SECOND={'segments':[{'fragment_id':'part-1','role':'request','group_id':'need-1'}, {'fragment_id':'part-2','role':'request','group_id':'need-2'}], 'groups':[{'id':'need-1','title':'Order number','category':'ORDER','kind':'goal'},{'id':'need-2','title':'Refund status','category':'REFUND','kind':'goal'}],'relations':[],'clarification':''}

class StagedTests(unittest.TestCase):
    def run_model(self, first=None, second=None):
        chats=[]; original=httpx.Client
        def handler(request):
            if request.url.path=='/api/tags':
                return httpx.Response(200,json={'models':[{'name':'local:latest','digest':DIGEST,'details':{'format':'gguf'}}]})
            chats.append(json.loads(request.content))
            output=(first or FIRST) if len(chats)==1 else (second or SECOND)
            return httpx.Response(200,json={'model':'local:latest','done':True,'done_reason':'stop','message':{'content':json.dumps(output)}})
        with patch('support_ticket_ai.proposals.httpx.Client',side_effect=lambda **kw:original(transport=httpx.MockTransport(handler),**kw)):
            result=StagedProposer('local').propose(TEXT)
        return result,chats

    def test_two_passes_restore_original_evidence_and_mark_experimental_identity(self):
        result,chats=self.run_model()
        self.assertEqual(len(chats),2)
        self.assertEqual(result['prompt_version'],5)
        self.assertEqual(result['interpretation_mode'],'staged')
        self.assertTrue(result['requires_human_review'])
        self.assertEqual([p['text'] for p in result['review']['parts']],['Find my order number','and also check my refund.'])
        self.assertEqual(json.loads(chats[1]['messages'][1]['content'])['fragment_classifications'],FIRST['fragments'])

    def test_bad_first_pass_ids_rejected_before_grouping(self):
        first=copy.deepcopy(FIRST);first['fragments'][1]['fragment_id']='part-1'
        with self.assertRaises(ProposalFailure) as caught:self.run_model(first=first)
        self.assertEqual(caught.exception.validation_code,'fragment_coverage')

    def test_grouping_cannot_demote_request_to_background_or_change_category(self):
        for field,value in [('role','context'),('category','ORDER')]:
            second=copy.deepcopy(SECOND)
            if field=='role':second['segments'][1]['role']=value
            else:second['groups'][1]['category']=value
            with self.assertRaises(ProposalFailure):self.run_model(second=second)

    def test_wrong_first_pass_meaning_is_not_claimed_to_be_corrected(self):
        first=copy.deepcopy(FIRST);first['fragments'][1].update(role='context',category=None)
        second=copy.deepcopy(SECOND);second['segments'][1].update(role='context',group_id='need-1');second['groups'].pop()
        result,_=self.run_model(first,second)
        self.assertEqual(len(result['review']['groups']),1)
        self.assertIn('not verified',result['validation'])
