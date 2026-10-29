import copy
import sqlite3
import tempfile
from pathlib import Path
import unittest
from uuid import uuid4
from fastapi.testclient import TestClient
from pydantic import ValidationError
from support_ticket_ai.api import create_app
from support_ticket_ai.need_review import NeedReview
from support_ticket_ai.needs_draft import NeedsDraft
from support_ticket_ai.proposals import align_plan
from support_ticket_ai.request_store import RequestStore
from test_proposals import TEXT, generated


def draft(adopted=False):
    proposed=align_plan(TEXT,generated())
    editable=copy.deepcopy(proposed) if adopted else None
    if editable:editable['schema_version']=3
    return {'editable':editable,'proposed':proposed,'model_draft':adopted,'proposal_adopted':adopted}


class NeedsDraftTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.db=Path(self.temp.name)/'requests.sqlite3'
        self.client=self.enterContext(TestClient(create_app(requests_db=self.db)))
        self.key=str(uuid4())

    def save(self,value=None,text=TEXT):
        return self.client.post('/requests',json={'text':text,'include_prediction':False,'client_request_id':self.key,'needs_draft':value or draft()})

    def test_proposals_are_durable_unreviewed_data_not_human_decisions(self):
        response=self.save();self.assertEqual(response.status_code,201,response.text)
        record=response.json()
        self.assertIsNotNone(record['needs_draft']);self.assertIsNone(record['need_review'])
        self.assertEqual(record['need_progress'],[])
        self.assertEqual((record['status'],record['review_state'],record['version']),('open','pending',1))
        self.assertIsNone(record['confirmed_category']);self.assertIsNone(record['prediction'])
        self.assertEqual(RequestStore(self.db).get(record['id'])['needs_draft'],record['needs_draft'])

    def test_incomplete_manual_choices_are_retained_but_not_valid_as_review(self):
        value=draft(True);value['model_draft']=False;value['proposal_adopted']=False
        plan=value['editable'];plan['parts'][0]['role']='unconfirmed';plan['parts'][0]['group_id']=None
        plan['groups'][0]['title']='';plan['groups'][0]['category']='';plan['groups'][0]['actions']=[{'description':'','target':None}]
        self.assertIsNotNone(NeedsDraft.model_validate(value))
        with self.assertRaises(ValidationError):NeedReview.model_validate(plan)
        result=self.save(value);self.assertEqual(result.status_code,201,result.text)
        self.assertEqual(result.json()['needs_draft']['editable']['parts'][0]['role'],'unconfirmed')

    def test_save_retry_is_idempotent_and_does_not_resurrect_a_reviewed_draft(self):
        first=self.save().json();again=self.save().json();self.assertEqual(first,again)
        self.assertEqual(self.client.get('/requests').json()['total'],1)
        result=self.client.post(f"/requests/{first['id']}/needs-review",json={'version':1,'actor':'Reviewer','review':align_plan(TEXT,generated())})
        self.assertEqual(result.status_code,200,result.text)
        reviewed=result.json();self.assertIsNone(reviewed['needs_draft'])
        self.assertIn('unreviewed_needs_draft',reviewed['history'][-1]['before'])
        self.assertEqual(self.save().json(),reviewed)
        changed=draft();changed['proposed']['groups'][0]['title']='A changed proposal'
        self.assertEqual(self.save(changed).status_code,409)

    def test_request_and_draft_creation_rollback_together(self):
        with sqlite3.connect(self.db) as db:
            db.execute("CREATE TRIGGER reject_draft BEFORE INSERT ON request_needs_drafts BEGIN SELECT RAISE(ABORT,'fixture failure'); END")
        response=self.save();self.assertEqual(response.status_code,503)
        self.assertEqual(self.client.get('/requests').json()['total'],0)
        with sqlite3.connect(self.db) as db:self.assertEqual(db.execute('SELECT COUNT(*) FROM request_events').fetchone()[0],0)

    def test_pending_draft_blocks_resolution_until_explicit_review_save(self):
        record=self.save().json();identifier=record['id']
        for action,extra in [('review',{'category':'ORDER'}),('start',{})]:
            record=self.client.post(f'/requests/{identifier}/actions',json={'version':record['version'],'actor':'Reviewer','action':action,**extra}).json()
        result=self.client.post(f'/requests/{identifier}/actions',json={'version':record['version'],'actor':'Reviewer','action':'resolve','note':'Premature'})
        self.assertEqual(result.status_code,409)
        stale=self.client.post(f'/requests/{identifier}/needs-review',json={'version':1,'actor':'Reviewer','review':align_plan(TEXT,generated())})
        self.assertEqual(stale.status_code,409)
        self.assertIsNotNone(self.client.get('/requests/'+identifier).json()['needs_draft'])

    def test_wrong_source_and_forged_evidence_rejected_without_echo(self):
        for value in [draft(),draft(True)]:
            bad=copy.deepcopy(value)
            if bad['editable']:bad['editable']['parts'][0]['text']='private altered evidence'
            else:bad['proposed']['source_text']='private altered source'
            response=self.save(bad);self.assertEqual(response.status_code,422,response.text)
            self.assertNotIn('private altered',response.text)
        response=self.save(text='A different request')
        self.assertEqual(response.status_code,422)

    def test_unicode_offsets_and_whitespace_survive_handoff(self):
        text='  😀 '+TEXT+'  '
        plan=generated();plan['segments'][0]['text']='😀 '+plan['segments'][0]['text']
        proposed=align_plan(text,plan)
        value={'editable':None,'proposed':proposed,'model_draft':False,'proposal_adopted':False}
        response=self.save(value,text);self.assertEqual(response.status_code,201,response.text)
        record=response.json();self.assertEqual(record['message'],text)
        for part in record['needs_draft']['proposed']['parts']:
            self.assertEqual(text[part['start']:part['end']],part['text'])

    def test_schema_three_migration_retains_old_records(self):
        response=self.client.post('/requests',json={'text':TEXT,'include_prediction':False,'client_request_id':self.key})
        record=response.json()
        with sqlite3.connect(self.db) as db:
            db.execute('DROP TABLE request_needs_drafts');db.execute('PRAGMA user_version=3')
        store=RequestStore(self.db);self.assertEqual(store.get(record['id'])['message'],TEXT)
        self.assertIsNone(store.get(record['id'])['needs_draft'])
        with sqlite3.connect(self.db) as db:self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0],4)
