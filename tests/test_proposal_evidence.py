"""Numbered evidence contracts; authored model responses are not live model evaluations."""
import copy
import hashlib
import json
import unittest
from unittest.mock import patch
import httpx
from fastapi.testclient import TestClient
from support_ticket_ai.api import create_app
from support_ticket_ai.proposal_evidence import source_fragments
from support_ticket_ai.proposals import (OllamaProposer, ProposalOutputError, ProposalFailure,
    align_fragment_plan, align_plan, fragment_schema, prompt_sha256)
from test_proposals import TEXT, DIGEST, generated

REGRESSION='Please, what is my order number and also check if the refund had been made for my cancelled ordered.'


def referenced():
    plan=generated()
    plan['segments']=[{'fragment_id':f'part-{i+1}','role':segment['role'],'group_id':segment['group_id']}
                      for i,segment in enumerate(plan['segments'])]
    return plan


class NumberedEvidenceTests(unittest.TestCase):
    def engine(self, outputs):
        original=httpx.Client;self.chats=[]
        def handler(request):
            if request.url.path=='/api/tags':
                return httpx.Response(200,json={'models':[{'name':'local:latest','digest':DIGEST,'details':{'format':'gguf'}}]})
            body=json.loads(request.content);self.chats.append(body)
            output=outputs[min(len(self.chats)-1,len(outputs)-1)]
            return httpx.Response(200,json={'model':'local:latest','done':True,'done_reason':'stop','message':{'content':json.dumps(output)}})
        self.enterContext(patch('support_ticket_ai.proposals.httpx.Client',side_effect=lambda **kwargs:original(transport=httpx.MockTransport(handler),**kwargs)))
        return OllamaProposer('local')

    def assert_coverage(self,text,parts):
        cursor=0
        for index,part in enumerate(parts,1):
            self.assertEqual(part['id'],f'part-{index}')
            self.assertEqual(text[part['start']:part['end']],part['text'])
            self.assertFalse(text[cursor:part['start']].strip())
            cursor=part['end']
        self.assertFalse(text[cursor:].strip())

    def test_reported_coordination_case_preserves_typo_and_conjunction(self):
        evidence=source_fragments(REGRESSION)
        self.assertEqual(len(evidence['fragments']),2)
        self.assertEqual(evidence['fragments'][1]['text'],'and also check if the refund had been made for my cancelled ordered.')
        self.assert_coverage(REGRESSION,evidence['fragments'])
        self.assertFalse(evidence['grouped_remainder'])
        from support_ticket_ai.resources import data_path
        cases=json.loads(data_path('needs_evidence_regressions.json').read_text())['cases']
        for case in cases:
            plan=copy.deepcopy(case['expected_plan'])
            plan['segments']=[{'fragment_id':f'part-{i+1}','role':item['role'],'group_id':item['group_id']} for i,item in enumerate(plan['segments'])]
            self.assertEqual(align_fragment_plan(case['text'],plan),align_plan(case['text'],case['expected_plan']))

    def test_unicode_whitespace_repetition_and_boundary_limit_preserve_coverage(self):
        for text in ['  👩🏿‍💻 Help.\n Help.  ', 'A.\n\nB.\tand also check C.', '取消订单。 Vérifiez le remboursement.', ' '.join('Help.' for _ in range(30))]:
            parts=source_fragments(text)['fragments'];self.assertLessEqual(len(parts),24)
            self.assert_coverage(text,parts)
        self.assertTrue(source_fragments(' '.join('Help.' for _ in range(30)))['grouped_remainder'])

    def test_schema_limits_ids_and_count_to_this_source(self):
        schema=fragment_schema(source_fragments(TEXT))
        self.assertEqual(schema['$defs']['FragmentAssignment']['properties']['fragment_id']['enum'],['part-1','part-2'])
        self.assertEqual(schema['properties']['segments']['minItems'],2)
        self.assertEqual(schema['properties']['segments']['maxItems'],2)

    def test_missing_duplicate_reordered_and_invented_ids_rejected(self):
        for change in ['missing','duplicate','reordered','invented']:
            value=referenced()
            if change=='missing':value['segments'].pop()
            elif change=='duplicate':value['segments'][1]['fragment_id']='part-1'
            elif change=='reordered':value['segments'].reverse()
            else:value['segments'][1]['fragment_id']='part-9'
            with self.assertRaises(ProposalOutputError) as caught:align_fragment_plan(TEXT,value)
            self.assertEqual(caught.exception.validation_code,'fragment_coverage')

    def test_model_cannot_supply_rewritten_evidence_or_offsets(self):
        for field,value in [('text','Rewritten source'),('start',1),('end',999)]:
            plan=referenced();plan['segments'][0][field]=value
            with self.assertRaises(ProposalOutputError) as caught:align_fragment_plan(TEXT,plan)
            self.assertEqual(caught.exception.validation_code,'schema_invalid')
        self.assertEqual(align_fragment_plan(TEXT,referenced()),align_plan(TEXT,generated()))

    def test_semantic_errors_can_pass_structure_and_need_human_review(self):
        plan=referenced();plan['groups'][0]['category']='PAYMENT'
        review=align_fragment_plan(TEXT,plan)
        self.assertEqual(review['groups'][0]['category'],'PAYMENT')
        self.assertEqual(review['source_text'],TEXT)  # Exact evidence is not category correctness.

    def test_group_and_relationship_checks_still_apply(self):
        for change,code in [('unknown','unknown_need'),('unassigned','unassigned_need'),('relationship','relationship_invalid'),('clarification','clarification_missing')]:
            plan=referenced()
            if change=='unknown':plan['segments'][0]['group_id']='need-9'
            if change=='unassigned':plan['segments'][0]['group_id']=None
            if change=='relationship':plan['relations'][0]['evidence_parts']=['part-1']
            if change=='clarification':plan['clarification']=''
            with self.assertRaises(ProposalOutputError) as caught:align_fragment_plan(TEXT,plan)
            self.assertEqual(caught.exception.validation_code,code)

    def test_default_engine_uses_ids_and_original_server_text(self):
        engine=self.engine([referenced()]);result=engine.propose(TEXT)
        self.assertEqual((result['evidence_mode'],result['prompt_version']),('fragments',4))
        self.assertEqual(result['source_sha256'],hashlib.sha256(TEXT.encode()).hexdigest())
        self.assertEqual(result['review'],align_plan(TEXT,generated()))
        payload=json.loads(self.chats[0]['messages'][1]['content'])
        self.assertEqual(payload['source_fragments'],source_fragments(TEXT)['fragments'])
        self.assertEqual(result['generation_attempts'],1)
        self.assertTrue(result['requires_human_review'])

    def test_one_retry_recovers_id_coverage_without_repairing_model_output(self):
        bad=referenced();bad['segments'][1]['fragment_id']='part-1'
        engine=self.engine([bad,referenced()]);result=engine.propose(TEXT)
        self.assertEqual(result['generation_attempts'],2)
        self.assertEqual(result['recovered_from_validation'],'fragment_coverage')
        second=json.loads(self.chats[1]['messages'][1]['content'])
        self.assertEqual(second['validation_retry']['code'],'fragment_coverage')
        self.assertNotIn('previous_output',second)

    def test_failed_id_generation_returns_safe_api_diagnostics(self):
        bad=referenced();bad['segments'][1]['fragment_id']='part-1';engine=self.engine([bad])
        with TestClient(create_app()) as client:
            client.app.state.proposer=engine
            result=client.post('/proposals',json={'text':TEXT})
        self.assertEqual(result.status_code,502)
        self.assertEqual((result.json()['validation_code'],result.json()['prompt_version']),('fragment_coverage',4))
        self.assertEqual(result.json()['evidence_mode'],'fragments')
        self.assertNotIn(TEXT,result.text)
        self.assertTrue(engine.slot.acquire(blocking=False));engine.slot.release()

    def test_modes_are_explicit_and_have_distinct_prompt_identities(self):
        self.assertNotEqual(prompt_sha256('fragments'),prompt_sha256('excerpts'))
        self.assertEqual(OllamaProposer('local',evidence_mode='excerpts').prompt_version,2)
        with self.assertRaises(ValueError):OllamaProposer('local',evidence_mode='automatic')

    def test_combined_noun_phrase_is_not_claimed_to_be_two_detected_needs(self):
        text='Tell me my order number and refund status.'
        self.assertEqual(len(source_fragments(text)['fragments']),1)
        self.assertIn('not detected needs',source_fragments(text)['limitations'])

    def test_reported_valid_but_incomplete_proposal_is_measured_as_a_missed_need(self):
        from support_ticket_ai.proposal_metrics import compare
        from support_ticket_ai.resources import data_path
        case=json.loads(data_path('needs_evidence_regressions.json').read_text())['cases'][0]
        bad=copy.deepcopy(case['expected_plan'])
        bad['segments'][1].update(role='context',group_id='need-1')
        bad['groups'].pop()
        bad['clarification']='Please provide your order number and confirm if a refund has been processed for your cancelled order.'
        actual=align_plan(REGRESSION,bad)
        metrics=compare(align_plan(REGRESSION,case['expected_plan']),actual)
        self.assertEqual(metrics['missed_needs'],1)
        self.assertEqual(metrics['unexpected_clarification'],1)
        self.assertFalse(metrics['category_set_match'])
        # Structural acceptance must not be confused with semantic success or patched to a canned answer.
        self.assertEqual(len(actual['groups']),1)

    def test_prompt_comparison_uses_same_evidence_and_distinct_versioned_identity(self):
        from support_ticket_ai.proposals import fragment_system, FRAGMENT_SYSTEM_V3
        self.assertEqual(fragment_system(3),FRAGMENT_SYSTEM_V3)
        self.assertNotEqual(prompt_sha256('fragments',3),prompt_sha256('fragments',4))
        self.assertEqual(OllamaProposer('local',fragment_prompt_version=3).prompt_version,3)
        with self.assertRaises(ValueError):OllamaProposer('local',fragment_prompt_version=9)
        engine=self.engine([referenced()]);engine.prompt_version=3;engine.fragment_prompt_version=3
        old=engine.propose(TEXT)
        old_payload=json.loads(self.chats[-1]['messages'][1]['content'])
        old_system=self.chats[-1]['messages'][0]['content']
        engine.prompt_version=4;engine.fragment_prompt_version=4
        new=engine.propose(TEXT)
        new_payload=json.loads(self.chats[-1]['messages'][1]['content'])
        new_system=self.chats[-1]['messages'][0]['content']
        self.assertEqual(old_payload,new_payload)
        self.assertNotEqual(old_system,new_system)
        self.assertEqual((old['prompt_version'],new['prompt_version']),(3,4))
        self.assertNotEqual(old['prompt_sha256'],new['prompt_sha256'])
        self.assertEqual(old['review'],new['review'])  # Authored output, not live quality evidence.
        self.assertIn('only the cancellation is historical',new_system)
        self.assertIn('supply the answer they are requesting',new_system)
