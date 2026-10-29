import copy
import json
from unittest.mock import patch
import unittest
import httpx
from fastapi.testclient import TestClient
from support_ticket_ai.api import create_app
from support_ticket_ai.proposals import OllamaProposer, ProposalFailure, ProposalOutputError, align_plan
from test_proposals import TEXT, DIGEST, generated


class ProposalRecoveryTests(unittest.TestCase):
    def engine(self, outputs, *, clock=None):
        original=httpx.Client;self.chats=[]
        def handler(request):
            if request.url.path=='/api/tags':
                return httpx.Response(200,json={'models':[{'name':'local:latest','digest':DIGEST,'details':{'format':'gguf'}}]})
            body=json.loads(request.content);self.chats.append(body)
            value=outputs[min(len(self.chats)-1,len(outputs)-1)]
            content=json.dumps(value) if not isinstance(value,str) else value
            if clock is not None:clock[0]=121
            return httpx.Response(200,json={'model':'local:latest','done':True,'done_reason':'stop','message':{'content':content}})
        self.enterContext(patch('support_ticket_ai.proposals.httpx.Client',side_effect=lambda **kwargs:original(transport=httpx.MockTransport(handler),**kwargs)))
        return OllamaProposer('local')

    def test_one_repair_can_recover_but_must_pass_original_evidence_checks(self):
        broken=generated();broken['segments'][0]['text']='Please find my order number!'
        engine=self.engine([broken,generated()]);result=engine.propose(TEXT)
        self.assertEqual(result['generation_attempts'],2)
        self.assertEqual(result['recovered_from_validation'],'evidence_mismatch')
        self.assertEqual(result['review']['source_text'],TEXT)
        second=json.loads(self.chats[1]['messages'][1]['content'])
        self.assertEqual(second['customer_message'],TEXT)
        self.assertEqual(second['validation_retry']['code'],'evidence_mismatch')
        self.assertEqual(len(self.chats),2)

    def test_repeated_invalid_output_stops_and_returns_safe_specific_diagnostics(self):
        engine=self.engine([{'private customer field':TEXT}])
        with self.assertRaises(ProposalFailure) as caught:engine.propose(TEXT)
        error=caught.exception
        self.assertEqual((error.code,error.validation_code,error.attempts),('invalid_output','schema_invalid',2))
        self.assertNotIn(TEXT,str(error));self.assertNotIn('private customer field',str(error))
        self.assertEqual(len(self.chats),2)
        self.assertTrue(engine.slot.acquire(blocking=False));engine.slot.release()

    def test_json_group_relationship_and_clarification_failures_are_distinct(self):
        for mutation,code in [('group','unknown_need'),('unassigned','unassigned_need'),('duplicate','duplicate_need'),('link','relationship_invalid'),('question','clarification_missing')]:
            plan=generated()
            if mutation=='unassigned':plan['segments'][0]['group_id']=None
            if mutation=='duplicate':plan['groups'][1]['id']='need-1'
            if mutation=='group':plan['segments'][0]['group_id']='need-9'
            if mutation=='link':plan['relations'][0]['target']='need-9'
            if mutation=='question':plan['clarification']=''
            with self.assertRaises(ProposalOutputError) as caught:align_plan(TEXT,plan)
            self.assertEqual(caught.exception.validation_code,code)
        engine=self.engine([TEXT])
        with self.assertRaises(ProposalFailure) as caught:engine.propose(TEXT)
        self.assertEqual(caught.exception.validation_code,'invalid_json')

    def test_shared_time_budget_stops_instead_of_starting_more_attempts(self):
        clock=[0];engine=self.engine([generated()],clock=clock)
        with patch('support_ticket_ai.proposals.monotonic',side_effect=lambda:clock[0]):
            with self.assertRaises(ProposalFailure) as caught:engine.propose(TEXT)
        self.assertEqual(caught.exception.status,504)
        self.assertEqual(len(self.chats),1)

    def test_http_error_payload_identifies_stage_without_raw_model_text(self):
        engine=self.engine([{'sensitive field':TEXT}])
        with TestClient(create_app()) as client:
            client.app.state.proposer=engine
            response=client.post('/proposals',json={'text':TEXT})
            self.assertEqual(response.status_code,502)
            self.assertEqual(response.json()['validation_code'],'schema_invalid')
            self.assertEqual(response.json()['attempts'],2)
            self.assertEqual(response.json()['prompt_version'],2)
            self.assertNotIn(TEXT,response.text);self.assertNotIn('sensitive field',response.text)
