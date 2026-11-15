import json
import unittest
from unittest.mock import patch
import httpx
from support_ticket_ai.clarification_pilot import validate_decision,score,evaluate
from support_ticket_ai.proposal_evidence import source_fragments
from support_ticket_ai.proposals import OllamaProposer,ProposalFailure
from support_ticket_ai.resources import data_path

class ClarificationTests(unittest.TestCase):
    def test_no_question_is_explicit_and_invalid_combinations_rejected(self):
        evidence=source_fragments('Find my order number.')
        none={'decision':'none','reason':'none','evidence_parts':[],'text':''}
        self.assertEqual(validate_decision(none,evidence),none)
        for changes in [{'text':'Please provide your order number.'},{'reason':'ambiguous_target'},{'evidence_parts':['part-1']}]:
            with self.assertRaises(ProposalFailure):validate_decision({**none,**changes},evidence)

    def test_unknown_evidence_and_blank_note_rejected(self):
        evidence=source_fragments('If delivery fails, refund it.')
        note={'decision':'note','reason':'conditional_instruction','evidence_parts':['part-1'],'text':'Refund only if delivery fails.'}
        self.assertEqual(validate_decision(note,evidence),note)
        for changes in [{'text':' '},{'evidence_parts':['part-9']},{'decision':'ask'}]:
            with self.assertRaises(ProposalFailure):validate_decision({**note,**changes},evidence)

    def test_structurally_valid_bad_question_is_not_semantically_certified(self):
        expected={'decision':'none','reason':'none','evidence_parts':[]}
        actual={'decision':'ask','reason':'ambiguous_target','evidence_parts':['part-1'],'text':'Provide the order number you requested.'}
        validate_decision(actual,source_fragments('Find my order number.'))
        self.assertEqual(score(expected,actual)['unexpected_clarification'],1)

    def test_fixture_ids_and_evidence_are_valid(self):
        fixture=json.loads(data_path('needs_clarification_development.json').read_text())
        self.assertEqual(len(fixture['cases']),14)
        for c in fixture['cases']:
            self.assertTrue(set(c['expected']['evidence_parts']).issubset({p['id'] for p in source_fragments(c['text'])['fragments']}))

    def test_transport_sends_only_source_not_expected_decisions(self):
        original=httpx.Client;chats=[]
        output={'decision':'ask','reason':'ambiguous_target','evidence_parts':['part-1'],'text':'Which order should have its address changed?'}
        def handler(request):
            if request.url.path=='/api/tags':return httpx.Response(200,json={'models':[{'name':'local:latest','digest':'a'*64,'details':{'format':'gguf'}}]})
            chats.append(json.loads(request.content))
            return httpx.Response(200,json={'model':'local:latest','done':True,'done_reason':'stop','message':{'content':json.dumps(output)}})
        with patch('support_ticket_ai.proposals.httpx.Client',side_effect=lambda **kw:original(transport=httpx.MockTransport(handler),**kw)):
            result=evaluate(OllamaProposer('local'),'Change the address on that one.')
        self.assertEqual(result['decision'],output)
        self.assertEqual(set(json.loads(chats[0]['messages'][1]['content'])),{'customer_message','source_fragments'})
