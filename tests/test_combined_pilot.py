import json
import unittest
from unittest.mock import patch
import httpx
from support_ticket_ai.combined_pilot import evaluate
from support_ticket_ai.staged_proposals import StagedProposer
from support_ticket_ai.proposals import ProposalFailure

class CombinedTests(unittest.TestCase):
    def run_case(self,text,outputs,question_contract="ask-only"):
        original=httpx.Client;calls=[]
        def handler(request):
            if request.url.path=='/api/tags':return httpx.Response(200,json={'models':[{'name':'local:latest','digest':'a'*64,'details':{'format':'gguf'}}]})
            calls.append(json.loads(request.content))
            return httpx.Response(200,json={'model':'local:latest','done':True,'done_reason':'stop','message':{'content':json.dumps(outputs[len(calls)-1])}})
        with patch('support_ticket_ai.proposals.httpx.Client',side_effect=lambda **kw:original(transport=httpx.MockTransport(handler),**kw)):
            result=evaluate(StagedProposer('local',role_prompt='focused'),text,question_contract)
        return result,calls

    def test_condition_survives_none_question_without_model_invented_note(self):
        text='If delivery fails, refund it.'
        outputs=[{'fragments':[{'fragment_id':'part-1','role':'conditional','category':'REFUND'}]},
            {'groups':[{'anchor_fragment_id':'part-1','title':'Conditional refund','fragment_ids':['part-1']}],'ungrouped':[]},
            {'decision':'none','reason':'none','evidence_parts':[],'text':''}]
        result,calls=self.run_case(text,outputs)
        self.assertEqual(len(calls),3)
        self.assertEqual(result['preserved_conditions'][0]['text'],text)
        self.assertIn(text,result['review']['clarification'])
        self.assertEqual(result['question']['decision'],'none')
        self.assertNotIn('clarification',calls[1]['format']['properties'])
        self.assertNotIn('expected',json.loads(calls[2]['messages'][1]['content']))

    def test_ambiguous_target_question_remains_separate_from_conditions(self):
        outputs=[{'fragments':[{'fragment_id':'part-1','role':'request','category':'SHIPPING'}]},
            {'groups':[{'anchor_fragment_id':'part-1','title':'Change address','fragment_ids':['part-1']}],'ungrouped':[]},
            {'decision':'ask','reason':'ambiguous_target','evidence_parts':['part-1'],'text':'Which order should have its address changed?'}]
        result,_=self.run_case('Change the address on that one.',outputs)
        self.assertEqual(result['preserved_conditions'],[])
        self.assertEqual(result['review']['clarification'],outputs[-1]['text'])

    def test_note_from_question_pass_is_rejected(self):
        outputs=[{'fragments':[{'fragment_id':'part-1','role':'request','category':'ORDER'}]},
            {'groups':[{'anchor_fragment_id':'part-1','title':'Find order','fragment_ids':['part-1']}],'ungrouped':[]},
            {'decision':'note','reason':'conditional_instruction','evidence_parts':['part-1'],'text':'Invented condition'}]
        with self.assertRaises(ProposalFailure) as caught:self.run_case('Find my order number.',outputs)
        self.assertEqual(caught.exception.diagnostics['combined_stage'],'question')
        self.assertEqual(caught.exception.diagnostics['generation_calls'],3)

    def test_reused_contract_retains_note_without_inventing_preserved_evidence(self):
        from support_ticket_ai.clarification_pilot import CONSTRAINED_SYSTEM,decision_schema
        from support_ticket_ai.proposal_evidence import source_fragments
        text='Find my order number.'
        outputs=[{'fragments':[{'fragment_id':'part-1','role':'request','category':'ORDER'}]},
            {'groups':[{'anchor_fragment_id':'part-1','title':'Find order','fragment_ids':['part-1']}],'ungrouped':[]},
            {'decision':'note','reason':'conditional_instruction','evidence_parts':['part-1'],'text':'Invented condition'}]
        result,calls=self.run_case(text,outputs,'reused-constrained')
        self.assertEqual(calls[2]['messages'][0]['content'],CONSTRAINED_SYSTEM+'\nJSON schema: '+json.dumps(decision_schema(source_fragments(text),'constrained')))
        self.assertEqual(calls[2]['format'],decision_schema(source_fragments(text),'constrained'))
        self.assertEqual(result['clarification_decision'],outputs[-1])
        self.assertEqual(result['question']['decision'],'none')
        self.assertEqual(result['preserved_conditions'],[])
        self.assertEqual(result['review']['clarification'],'')

    def test_followup_fixture_labels_align_and_inputs_are_new(self):
        from support_ticket_ai.resources import data_path
        from support_ticket_ai.proposals import align_plan
        from support_ticket_ai.proposal_evidence import source_fragments
        from support_ticket_ai.clarification_pilot import validate_decision
        old=json.loads(data_path('needs_role_contrasts.json').read_bytes())['cases']
        cases=json.loads(data_path('needs_frozen_followup.json').read_bytes())['cases']
        self.assertEqual(len(cases),12)
        self.assertEqual(len({c['id'] for c in cases}),len(cases))
        self.assertFalse({c['text'] for c in old}&{c['text'] for c in cases})
        for case in cases:
            align_plan(case['text'],case['expected_plan'])
            expected=case['expected_clarification']
            validate_decision({**expected,'text':'Review this ambiguity or condition.' if expected['decision']!='none' else ''},source_fragments(case['text']))

    def test_meaning_variant_changes_only_question_system_and_preserves_raw_wording(self):
        from support_ticket_ai.combined_pilot import MEANING_FOCUSED_SYSTEM
        outputs=[{'fragments':[{'fragment_id':'part-1','role':'request','category':'ORDER'}]},
            {'groups':[{'anchor_fragment_id':'part-1','title':'Order choice','fragment_ids':['part-1']}],'ungrouped':[]},
            {'decision':'ask','reason':'alternative_choice','evidence_parts':['part-1'],'text':'Which order should I cancel?'}]
        text='Either cancel order Q or keep it active.'
        baseline,old_calls=self.run_case(text,outputs,'reused-constrained')
        result,new_calls=self.run_case(text,outputs,'meaning-focused')
        self.assertEqual(new_calls[:2],old_calls[:2])
        self.assertEqual(new_calls[2]['format'],old_calls[2]['format'])
        self.assertEqual(new_calls[2]['messages'][1],old_calls[2]['messages'][1])
        self.assertEqual(new_calls[2]['messages'][0]['content'],MEANING_FOCUSED_SYSTEM+'\nJSON schema: '+json.dumps(new_calls[2]['format']))
        self.assertEqual(result['question'],outputs[-1])
        self.assertEqual(result['review']['parts'][0]['role'],'request')
        self.assertEqual(result,baseline)
