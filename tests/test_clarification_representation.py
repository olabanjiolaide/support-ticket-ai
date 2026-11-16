import json
import unittest
from unittest.mock import patch
import httpx
from support_ticket_ai.clarification_representation import expand_representation,evaluate,representation_schema
from support_ticket_ai.proposal_evidence import source_fragments
from support_ticket_ai.proposals import ProposalFailure,OllamaProposer

class RepresentationTests(unittest.TestCase):
    def test_options_are_quoted_without_selecting_or_paraphrasing(self):
        text='Either cancel order Q or keep it active.';evidence=source_fragments(text)
        raw={'kind':'action_choice','quotes':[{'fragment_id':'part-1','text':'cancel order Q'},{'fragment_id':'part-1','text':'keep it active'}]}
        result=expand_representation(raw,evidence)
        self.assertEqual(result['decision']['text'],'Which option would you like: “cancel order Q” or “keep it active”?')
        for quote in result['grounded_quotes']:self.assertEqual(text[quote['start']:quote['end']],quote['text'])

    def test_reference_note_and_none_render_separately(self):
        for kind,text,quote,decision in [
            ('unresolved_target','Change that order.','that order','ask'),
            ('conditional_note','Refund only if returned.','Refund only if returned.','note'),
            ('none','Send invoice.',None,'none')]:
            raw={'kind':kind,'quotes':[] if quote is None else [{'fragment_id':'part-1','text':quote}]}
            self.assertEqual(expand_representation(raw,source_fragments(text))['decision']['decision'],decision)

    def test_bad_source_duplicate_and_wrong_cardinality_rejected(self):
        q={'fragment_id':'part-1','text':'cancel order Q'}
        for raw in [
            {'kind':'action_choice','quotes':[q]},
            {'kind':'action_choice','quotes':[q,q]},
            {'kind':'unresolved_target','quotes':[{'fragment_id':'part-2','text':'order Q'}]},
            {'kind':'unresolved_target','quotes':[{'fragment_id':'part-1','text':'order Z'}]},
            {'kind':'none','quotes':[q]},
            {'kind':'none','quotes':[],'question':'invented'}]:
            with self.subTest(raw=raw),self.assertRaises(ProposalFailure):expand_representation(raw,source_fragments('cancel order Q'))

    def test_valid_source_is_not_treated_as_semantic_certification(self):
        text='Keep order J. Cancel order K.'
        raw={'kind':'action_choice','quotes':[{'fragment_id':'part-1','text':'Keep order J.'},{'fragment_id':'part-2','text':'Cancel order K.'}]}
        result=expand_representation(raw,source_fragments(text))
        self.assertTrue(result['requires_human_review'])
        self.assertEqual(result['representation'],raw)
        self.assertEqual(result['decision']['reason'],'alternative_choice')

    def test_single_chat_with_source_only_and_no_question_field(self):
        original=httpx.Client;calls=[];text='Please change that order.'
        def handler(request):
            if request.url.path=='/api/tags':return httpx.Response(200,json={'models':[{'name':'local:latest','digest':'a'*64,'details':{'format':'gguf'}}]})
            calls.append(json.loads(request.content))
            return httpx.Response(200,json={'model':'local:latest','done':True,'done_reason':'stop','message':{'content':json.dumps({'kind':'unresolved_target','quotes':[{'fragment_id':'part-1','text':'that order'}]})}})
        with patch('support_ticket_ai.proposals.httpx.Client',side_effect=lambda **kw:original(transport=httpx.MockTransport(handler),**kw)):
            result=evaluate(OllamaProposer('local'),text)
        self.assertEqual(len(calls),1)
        self.assertEqual(set(json.loads(calls[0]['messages'][1]['content'])),{'customer_message','source_fragments'})
        self.assertEqual(calls[0]['format'],representation_schema(source_fragments(text)))
        self.assertEqual(result['decision']['text'],'Which item do you mean by “that order”?')
