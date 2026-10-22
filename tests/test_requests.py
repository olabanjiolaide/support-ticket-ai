import copy
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4

from fastapi.testclient import TestClient
import joblib
import sklearn

from support_ticket_ai.api import create_app
from support_ticket_ai.request_store import RequestStore, StoreConflict
from support_ticket_ai.train import build_model


class RequestWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.model = self.root / 'model'; self.model.mkdir()
        model = build_model()
        model.fit(['password reset', 'account login', 'card charged', 'bank payment'], ['ACCOUNT','ACCOUNT','PAYMENT','PAYMENT'])
        joblib.dump(model, self.model / 'model.joblib')
        self.sha = hashlib.sha256((self.model / 'model.joblib').read_bytes()).hexdigest()
        (self.model / 'validation_metrics.json').write_text(json.dumps({'model_sha256':self.sha,'versions':{'scikit-learn':sklearn.__version__}}))
        self.db = self.root / 'requests.sqlite3'
        self.app = create_app(self.model, requests_db=self.db)
        self.client = self.enterContext(TestClient(self.app))

    def save(self, **updates):
        body = {'text':'password reset', 'client_request_id':str(uuid4()), 'include_prediction':True, **updates}
        response = self.client.post('/requests', json=body)
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()

    def action(self, record, action, expected=200, **updates):
        body = {'version':record['version'], 'action':action, 'actor':'Ola', **updates}
        response = self.client.post(f"/requests/{record['id']}/actions", json=body)
        self.assertEqual(response.status_code, expected, response.text)
        return response.json()

    def test_prediction_alone_is_never_saved(self):
        self.assertEqual(self.client.post('/predict',json={'text':'password reset'}).status_code,200)
        self.assertEqual(self.client.get('/requests/overview').json()['total'],0)
        self.assertTrue(self.client.get('/workspace/config').json()['storage_available'])

    def test_saved_snapshot_comes_from_server_and_confirmation_does_not_resolve(self):
        record = self.save()
        original = copy.deepcopy(record['prediction'])
        self.assertEqual(original['model_sha256'],self.sha)
        record = self.action(record,'review',category='PAYMENT',note='Human correction.')
        self.assertEqual(record['confirmed_category'],'PAYMENT')
        self.assertEqual(record['status'],'open')
        self.assertEqual(record['review_state'],'reviewed')
        self.assertEqual(record['prediction'],original)
        self.assertIsNone(record['resolved_at'])
        self.assertEqual(len(record['history']),2)
        self.assertEqual(record['history'][-1]['after']['confirmed_category'],'PAYMENT')
        stats = self.client.get('/requests/overview').json()
        self.assertEqual((stats['pending_review'],stats['ready_to_handle'],stats['by_status']['resolved']),(0,1,0))

    def test_review_is_required_before_handling_or_resolving(self):
        record=self.save()
        self.action(record,'start',expected=409)
        self.action(record,'resolve',note='Attempt without review',expected=409)
        record=self.action(record,'review',category='ACCOUNT')
        self.action(record,'resolve',note='Not started',expected=409)
        record=self.action(record,'start')
        self.assertEqual(record['status'],'in_progress')
        record=self.action(record,'resolve',note='Password access restored.')
        self.assertEqual(record['status'],'resolved')
        self.assertEqual(record['resolution_note'],'Password access restored.')
        self.assertIsNotNone(record['resolved_at'])
        self.assertEqual(self.client.get('/requests',params={'status':'resolved'}).json()['total'],1)

    def test_clarification_invalidates_current_review_but_preserves_history(self):
        record=self.action(self.save(),'review',category='ACCOUNT',note='Initial classification')
        record=self.action(record,'clarify',note='Which account action needs help?')
        self.assertEqual((record['status'],record['review_state'],record['confirmed_category']),('needs_clarification','pending',None))
        self.assertEqual(record['history'][-1]['before']['confirmed_category'],'ACCOUNT')
        self.assertEqual(self.client.get('/requests',params={'queue':'review'}).json()['total'],1)
        self.action(record,'start',expected=409)
        record=self.action(record,'review',category='PAYMENT',note='Customer clarified the card issue.')
        self.assertEqual((record['status'],record['review_state']),('open','reviewed'))

    def test_reopen_requires_resolution_and_retains_resolution_event(self):
        record=self.save()
        self.action(record,'reopen',note='Not yet resolved',expected=409)
        record=self.action(record,'review',category='ACCOUNT')
        record=self.action(record,'start')
        record=self.action(record,'resolve',note='Restored access')
        self.action(record,'review',category='PAYMENT',expected=409)
        self.action(record,'clarify',note='Needs more info',expected=409)
        record=self.action(record,'reopen',note='Customer reported the issue again.')
        self.assertEqual((record['status'],record['review_state'],record['confirmed_category']),('open','pending',None))
        self.assertIsNone(record['resolution_note'])
        self.assertEqual(record['history'][-1]['before']['resolution_note'],'Restored access')

    def test_create_is_idempotent_without_repeating_inference(self):
        key=str(uuid4())
        predictor=self.app.state.predictor
        with patch.object(predictor,'predict',wraps=predictor.predict) as infer:
            first=self.save(client_request_id=key)
            second=self.save(client_request_id=key)
            self.assertEqual(first['id'],second['id'])
            self.assertEqual(infer.call_count,1)
        self.assertEqual(self.client.get('/requests/overview').json()['total'],1)
        self.assertEqual(len(self.client.get('/requests/'+first['id']).json()['history']),1)
        response=self.client.post('/requests',json={'text':'changed message','client_request_id':key})
        self.assertEqual(response.status_code,409)
        self.assertEqual(self.client.get('/requests/'+first['id']).json()['message'],'password reset')

    def test_stale_action_cannot_overwrite_or_append_history(self):
        record=self.save()
        updated=self.action(record,'note',note='First saved note')
        self.action(record,'review',category='PAYMENT',expected=409)
        stored=self.client.get('/requests/'+record['id']).json()
        self.assertEqual(stored['version'],updated['version'])
        self.assertEqual(stored['latest_note'],'First saved note')
        self.assertEqual(len(stored['history']),2)

    def test_notes_are_append_only_through_api_and_do_not_change_review(self):
        record=self.save()
        record=self.action(record,'note',note='First note')
        record=self.action(record,'note',note='Second note')
        self.assertEqual(record['review_state'],'pending')
        self.assertEqual([e['note'] for e in record['history']],['','First note','Second note'])
        self.assertEqual(self.client.patch('/requests/'+record['id'],json={'prediction':{}}).status_code,405)

    def test_manual_save_and_review_work_when_models_are_unavailable(self):
        with patch.dict('os.environ',{},clear=True), TestClient(create_app(requests_db=self.root/'manual.sqlite3')) as client:
            body={'text':'Please clarify this request','client_request_id':str(uuid4()),'include_prediction':False}
            record=client.post('/requests',json=body).json()
            self.assertIsNone(record['prediction'])
            response=client.post('/requests/'+record['id']+'/actions',json={'version':1,'action':'review','actor':'Reviewer','category':'CONTACT'})
            self.assertEqual(response.status_code,200)
            self.assertEqual(response.json()['status'],'open')
            body['include_prediction']=True;body['client_request_id']=str(uuid4())
            self.assertEqual(client.post('/requests',json=body).status_code,503)
            self.assertEqual(client.get('/requests/overview').json()['total'],1)

    def test_filters_literal_search_and_pagination(self):
        records=[self.save(text=text,include_prediction=False) for text in ['100% refund','under_score','normal request',"quote ' OR 1=1 --"]]
        record=self.action(records[0],'review',category='REFUND')
        self.action(record,'start')
        for q,total in [('%',1),('_',1),("' OR 1=1 --",1),('REQUEST',1),('not present',0)]:
            self.assertEqual(self.client.get('/requests',params={'q':q}).json()['total'],total)
        self.assertEqual(self.client.get('/requests',params={'category':'REFUND','status':'in_progress'}).json()['total'],1)
        self.assertEqual(self.client.get('/requests',params={'review_state':'pending'}).json()['total'],3)
        first=self.client.get('/requests',params={'limit':2}).json()
        second=self.client.get('/requests',params={'limit':2,'offset':2}).json()
        self.assertEqual(self.client.get('/requests',params={'q':'REQ-'+records[0]['id'][:8].upper()}).json()['total'],1)
        self.assertEqual(first['total'],4)
        self.assertEqual(len({r['id'] for r in first['items']+second['items']}),4)

    def test_invalid_input_never_echoes_messages_or_forges_snapshot(self):
        for update in [{'text':' '},{'text':'x'*2001},{'include_prediction':'false'},{'prediction':{'category':'HACK'}},{'mode':'unknown'}]:
            response=self.client.post('/requests',json={'text':'private sentinel','client_request_id':str(uuid4()),**update})
            self.assertEqual(response.status_code,422)
            self.assertNotIn('private sentinel',response.text)
        record=self.save()
        for update in [{'actor':' '},{'version':True},{'category':'UNKNOWN'},{'note':'x'*2001}]:
            body={'version':record['version'],'action':'review','actor':'Reviewer','category':'ACCOUNT',**update}
            self.assertEqual(self.client.post('/requests/'+record['id']+'/actions',json=body).status_code,422)
        for action in ['clarify','resolve','reopen','note']:
            self.action(record,action,expected=422)
        self.assertEqual(self.client.get('/requests',params={'limit':101}).status_code,422)
        self.assertEqual(self.client.get('/requests',params={'status':'nonsense'}).status_code,422)
        self.assertEqual(self.client.get('/requests',params={'category':'nonsense'}).status_code,422)
        self.assertEqual(self.client.get('/requests/'+str(uuid4())).status_code,404)

    def test_database_reopens_with_prediction_and_history_intact(self):
        record=self.action(self.save(),'review',category='ACCOUNT',note='Reviewed locally')
        with TestClient(create_app(self.model,requests_db=self.db)) as reopened:
            stored=reopened.get('/requests/'+record['id']).json()
            self.assertEqual(stored,record)
            self.assertEqual(reopened.get('/requests/overview').json()['confirmed_categories'],{'ACCOUNT':1})

    def test_database_trigger_rejects_source_mutation(self):
        record=self.save()
        with sqlite3.connect(self.db) as db:
            with self.assertRaises(sqlite3.IntegrityError):
                db.execute('UPDATE requests SET prediction_json=? WHERE id=?',('{}',record['id']))
        self.assertEqual(self.client.get('/requests/'+record['id']).json()['prediction'],record['prediction'])

    def test_concurrent_review_uses_one_revision_and_one_event(self):
        record=self.save()
        store=RequestStore(self.db)
        def mutate(category):
            try:return store.change(record['id'],version=1,action='review',actor='Concurrent reviewer',category=category)
            except StoreConflict:return None
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(mutate,['ACCOUNT','PAYMENT']))
        self.assertEqual(sum(r is not None for r in results),1)
        stored=store.get(record['id'])
        self.assertEqual(stored['version'],2)
        self.assertEqual(len(stored['history']),2)

    def test_storage_unavailable_does_not_break_stateless_predictions(self):
        with patch.dict('os.environ',{},clear=True), TestClient(create_app(self.model)) as client:
            self.assertFalse(client.get('/workspace/config').json()['storage_available'])
            self.assertEqual(client.get('/requests').status_code,503)
            self.assertEqual(client.post('/predict',json={'text':'password reset'}).status_code,200)

    def test_storage_errors_are_generic_and_schema_versions_are_checked(self):
        with patch.object(self.app.state.request_store,'list',side_effect=sqlite3.OperationalError('secret database path')):
            with self.assertLogs('support_ticket_ai.request_api',level='ERROR'):
                response=self.client.get('/requests')
            self.assertEqual(response.status_code,503)
            self.assertNotIn('secret database path',response.text)
        other=self.root/'future.sqlite3'
        with sqlite3.connect(other) as db:db.execute('PRAGMA user_version=999')
        with self.assertRaises(ValueError):RequestStore(other)
