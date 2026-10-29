import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4

import httpx
from fastapi.testclient import TestClient
from pydantic import ValidationError
from support_ticket_ai.api import create_app
from support_ticket_ai.need_review import NeedReview
from support_ticket_ai.proposals import OllamaProposer, ProposalFailure, align_plan

TEXT='Please find my order number, but I cannot access my account.'
DIGEST='a'*64


def generated():
    return {'segments':[
        {'text':'Please find my order number,','role':'request','group_id':'need-1'},
        {'text':'but I cannot access my account.','role':'obstacle','group_id':'need-2'}],
        'groups':[{'id':'need-1','title':'Retrieve the order number','category':'ORDER','kind':'goal'},
                  {'id':'need-2','title':'Restore account access','category':'ACCOUNT','kind':'obstacle'}],
        'relations':[{'source':'need-2','target':'need-1','kind':'may_block','evidence_parts':['part-1','part-2'],
                      'note':'Account access may be needed to retrieve the order number.'}],
        'clarification':'What happens when you try to sign in?'}


class ProposalTests(unittest.TestCase):
    def mock_engine(self, *, plan=None, response_update=None, digest_change=False, failure=None):
        calls=[];original=httpx.Client
        def handler(request):
            calls.append(request)
            self.assertEqual(request.url.host,'127.0.0.1');self.assertEqual(request.url.port,11434)
            if failure:raise failure
            if request.url.path=='/api/tags':
                digest='b'*64 if digest_change and len(calls)>1 else DIGEST
                return httpx.Response(200,json={'models':[{'name':'local:latest','digest':digest,'details':{'format':'gguf'}}]})
            body=json.loads(request.content)
            self.assertFalse(body['stream']);self.assertIn('properties',body['format'])
            self.assertEqual(body['options']['temperature'],0)
            self.assertEqual(json.loads(body['messages'][1]['content'])['customer_message'],TEXT)
            self.assertNotIn('tools',body)
            response={'model':'local:latest','done':True,'done_reason':'stop','message':{'content':json.dumps(generated() if plan is None else plan)}}
            response.update(response_update or {})
            return httpx.Response(200,json=response)
        mock=patch('support_ticket_ai.proposals.httpx.Client',side_effect=lambda **kwargs:original(transport=httpx.MockTransport(handler),**kwargs))
        self.enterContext(mock)
        return OllamaProposer('local'),calls

    def test_structured_local_adapter_and_server_derived_exact_offsets(self):
        engine,calls=self.mock_engine()
        result=engine.propose(TEXT)
        self.assertEqual(result['status'],'draft');self.assertTrue(result['requires_human_review'])
        self.assertEqual(result['model_digest'],DIGEST)
        self.assertEqual(result['source_sha256'],hashlib.sha256(TEXT.encode()).hexdigest())
        self.assertEqual(len(calls),3)
        self.assertEqual(result['review']['schema_version'],2)
        self.assertEqual(result['review']['parts'][1]['start'],29)
        self.assertEqual(result['review']['parts'][1]['role'],'obstacle')
        self.assertNotIn('confidence',result)

    def test_changed_omitted_reordered_and_extra_evidence_is_rejected(self):
        for change in ['changed','omitted','reordered','extra']:
            plan=generated()
            if change=='changed':plan['segments'][0]['text']='Find my order number.'
            elif change=='omitted':plan['segments'].pop()
            elif change=='reordered':plan['segments'].reverse()
            else:plan['segments'].append(copy.deepcopy(plan['segments'][0]))
            with self.assertRaises((ValueError,ValidationError)):align_plan(TEXT,plan)

    def test_unicode_and_repeated_excerpts_align_in_order(self):
        text='👩🏿‍💻 Help. Help.'
        plan={'segments':[{'text':part,'role':'context','group_id':None} for part in ['👩🏿‍💻 Help.','Help.']],
              'groups':[],'relations':[],'clarification':''}
        result=align_plan(text,plan)
        for part in result['parts']:
            self.assertEqual(text[part['start']:part['end']],part['text'])
        self.assertEqual(result['parts'][1]['start'],len('👩🏿‍💻 Help. '))

    def test_incomplete_generation_is_not_applied(self):
        engine,_=self.mock_engine(response_update={'done_reason':'length'})
        with self.assertRaises(ProposalFailure) as caught:engine.propose(TEXT)
        self.assertEqual(caught.exception.code,'incomplete_generation')

    def test_changing_model_identity_is_rejected(self):
        engine,_=self.mock_engine(digest_change=True)
        with self.assertRaises(ProposalFailure) as caught:engine.propose(TEXT)
        self.assertEqual(caught.exception.code,'model_changed')

    def test_invalid_response_does_not_echo_customer_data(self):
        engine,_=self.mock_engine(response_update={'message':{'content':TEXT}})
        with self.assertRaises(ProposalFailure) as caught:engine.propose(TEXT)
        self.assertEqual(caught.exception.code,'invalid_output');self.assertNotIn(TEXT,str(caught.exception))

    def test_model_mismatch_and_invalid_relationships_rejected(self):
        plan=generated();plan['relations'][0]['target']='need-9'
        with self.assertRaises(ValueError):align_plan(TEXT,plan)
        plan=generated();plan['relations'][0]['evidence_parts']=['part-1']
        with self.assertRaises(ValueError):align_plan(TEXT,plan)
        plan=generated();plan['relations'][0]['kind']='caused_by'
        with self.assertRaises(ValueError):align_plan(TEXT,plan)
        plan=generated();plan['clarification']=''
        with self.assertRaises(ValueError):align_plan(TEXT,plan)
        engine,_=self.mock_engine(response_update={'model':'different:latest'})
        with self.assertRaises(ProposalFailure) as caught:engine.propose(TEXT)
        self.assertEqual(caught.exception.code,'model_mismatch')

    def test_dependency_cycles_rejected(self):
        document=align_plan(TEXT,generated())
        document['relations']=[{'source':a,'target':b,'kind':'depends_on','evidence_parts':['part-1','part-2'],'note':'Review dependency.'}
                               for a,b in [('need-1','need-2'),('need-2','need-1')]]
        with self.assertRaises(ValidationError):NeedReview.model_validate(document)

    def test_timeout_and_concurrency_leave_slot_reusable(self):
        engine,_=self.mock_engine(failure=httpx.ReadTimeout('private backend details'))
        with self.assertRaises(ProposalFailure) as caught:engine.propose(TEXT)
        self.assertEqual(caught.exception.status,504);self.assertNotIn('private',str(caught.exception))
        self.assertTrue(engine.slot.acquire(blocking=False));engine.slot.release()
        engine.slot.acquire()
        with self.assertRaises(ProposalFailure) as caught:engine.propose(TEXT)
        self.assertEqual(caught.exception.status,409);engine.slot.release()

    def test_no_remote_urls_or_cloud_model_names(self):
        for name in ['https://example.com','qwen:cloud','../model','x'*101]:
            with self.assertRaises(ValueError):OllamaProposer(name)

    def test_generation_does_not_persist_or_overwrite_existing_review(self):
        with tempfile.TemporaryDirectory() as directory:
            with TestClient(create_app(requests_db=Path(directory)/'requests.sqlite3')) as client:
                self.assertFalse(client.get('/proposals/status').json()['configured'])
                self.assertEqual(client.post('/proposals',json={'text':TEXT}).status_code,503)
                engine,_=self.mock_engine();client.app.state.proposer=engine
                record=client.post('/requests',json={'text':TEXT,'client_request_id':str(uuid4()),'include_prediction':False}).json()
                before=client.get('/requests/'+record['id']).json()
                result=client.post('/proposals',json={'text':TEXT})
                self.assertEqual(result.status_code,200)
                self.assertEqual(client.get('/requests/'+record['id']).json(),before)
                review=result.json()['review']
                saved=client.post('/requests/'+record['id']+'/needs-review',json={'version':1,'actor':'Ola','review':review})
                self.assertEqual(saved.status_code,200,saved.text)
                after=saved.json()
                self.assertEqual(after['need_review']['review']['relations'],review['relations'])
                self.assertEqual(after['status'],'open');self.assertIsNone(after['confirmed_category'])

    def test_bad_body_does_not_echo_submitted_text(self):
        with TestClient(create_app()) as client:
            response=client.post('/proposals',json={'text':'private sentence','unexpected':'secret'})
            self.assertEqual(response.status_code,422);self.assertNotIn('private sentence',response.text)
