import copy
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from uuid import uuid4
from fastapi.testclient import TestClient
from support_ticket_ai.api import create_app
from support_ticket_ai.breakdown import preview
from support_ticket_ai.request_store import RequestStore, StoreConflict, RequestMissing

TEXT='Cancel order A. Keep order B.'


def contract():
    parts=preview(TEXT)['parts']
    groups=[]
    for index,target in enumerate(['order A','order B'],1):
        start=TEXT.index(target)
        groups.append({'id':f'need-{index}','title':['Cancel first order','Keep second order'][index-1],
                       'kind':'goal','category':'ORDER','actions':[{'description':['Review cancellation','Retain active order'][index-1],
                       'target':{'text':target,'start':start,'end':start+len(target)}}],'unknowns':[]})
    return {'schema_version':3,'source_text':TEXT,'parts':[{k:p[k] for k in ['id','start','end','text']}|{'role':'request','group_id':f'need-{index}'} for index,p in enumerate(parts,1)],
            'groups':groups,'relations':[],'clarification':''}


class NeedContractTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.db=Path(self.temp.name)/'requests.sqlite3';self.store=RequestStore(self.db)
        self.record=self.store.create(str(uuid4()),'test',TEXT,None)
        self.id=self.record['id']

    def save(self, document=None):
        current=self.store.get(self.id)
        self.record=self.store.save_need_review(self.id,version=current['version'],actor='Reviewer',review=document or contract())
        return self.record

    def parent(self,action,**kwargs):
        current=self.store.get(self.id)
        self.record=self.store.change(self.id,version=current['version'],actor='Reviewer',action=action,**kwargs)
        return self.record

    def progress(self,need,status):
        current=self.store.get(self.id)
        return self.store.change_need(self.id,version=current['version'],actor='Reviewer',need_id=need,status=status,note='Reviewed outcome')

    def start(self):
        self.parent('review',category='ORDER');self.parent('start')

    def test_exact_targets_roundtrip_and_forgery_rejected_without_echo(self):
        with TestClient(create_app(requests_db=self.db)) as client:
            doc=contract();doc['groups'][1]['actions'][0]['target']['text']='invented private target'
            response=client.post(f'/requests/{self.id}/needs-review',json={'version':1,'actor':'Reviewer','review':doc})
            self.assertEqual(response.status_code,422)
            self.assertNotIn('invented private target',response.text)
        saved=self.save()
        self.assertEqual(saved['need_review']['review'],contract())
        self.assertEqual([p['status'] for p in saved['need_progress']],['open','open'])
        self.assertEqual(self.store.get(self.id)['prediction'],None)

    def test_partial_resolution_does_not_resolve_parent_and_blocks_completion(self):
        self.save();self.start()
        self.progress('need-1','in_progress');self.progress('need-1','resolved')
        current=self.store.get(self.id)
        self.assertEqual(current['status'],'in_progress')
        self.assertEqual([p['status'] for p in current['need_progress']],['resolved','open'])
        with self.assertRaises(StoreConflict):self.parent('resolve',note='Too early')
        self.progress('need-2','dismissed')
        done=self.parent('resolve',note='First cancelled; second retained, no change needed.')
        self.assertEqual(done['status'],'resolved')
        self.assertEqual(RequestStore(self.db).get(self.id)['need_progress'],done['need_progress'])
        with self.assertRaises(StoreConflict):self.progress('need-1','open')
        self.parent('reopen',note='Customer disputed cancellation');self.progress('need-1','open')
        self.assertEqual(self.store.get(self.id)['history'][-1]['action'],'need_progress')

    def test_unknowns_cannot_be_resolved_and_changes_reset_active_progress(self):
        doc=contract();doc['groups'][0]['unknowns']=['Has order A shipped?']
        self.save(doc);self.start();self.progress('need-1','in_progress')
        with self.assertRaises(StoreConflict):self.progress('need-1','resolved')
        changed=copy.deepcopy(doc);changed['groups'][0]['unknowns']=[]
        result=self.save(changed)
        self.assertEqual(result['need_progress'][0]['status'],'open')
        self.assertEqual(result['history'][-1]['after']['reset_need_progress'],['need-1'])
        self.progress('need-1','in_progress');self.progress('need-1','resolved')
        changed['groups'][0]['actions'][0]['target']=changed['groups'][1]['actions'][0]['target']
        with self.assertRaises(StoreConflict):self.save(changed)
        self.progress('need-1','open');self.save(changed)

    def test_unchanged_review_preserves_progress_and_removal_requires_reopen(self):
        self.save();self.start();self.progress('need-1','in_progress');self.progress('need-1','resolved')
        result=self.save()
        self.assertEqual(result['need_progress'][0]['status'],'resolved')
        doc=contract();doc['groups'].pop(0);doc['parts'][0]['role']='context';doc['parts'][0]['group_id']=None
        with self.assertRaises(StoreConflict):self.save(doc)

    def test_strict_progress_api_and_stale_update_are_transactional(self):
        self.save();self.start()
        with TestClient(create_app(requests_db=self.db)) as client:
            version=self.store.get(self.id)['version']
            body={'version':version,'actor':'Reviewer','need_id':'need-1','status':'in_progress','note':'Started investigation'}
            self.assertEqual(client.post(f'/requests/{self.id}/need-progress',json={**body,'note':' '}).status_code,422)
            self.assertEqual(client.post(f'/requests/{self.id}/need-progress',json=body).status_code,200)
            self.assertEqual(client.post(f'/requests/{self.id}/need-progress',json={**body,'need_id':'need-2'}).status_code,409)
        self.assertEqual(self.store.get(self.id)['need_progress'][1]['status'],'open')

    def test_two_concurrent_updates_cannot_both_win(self):
        self.save();self.start();version=self.store.get(self.id)['version']
        def change(need):
            try:self.store.change_need(self.id,version=version,actor='Reviewer',need_id=need,status='in_progress',note='Started');return True
            except StoreConflict:return False
        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertEqual(sorted(pool.map(change,['need-1','need-2'])),[False,True])

    def test_schema_two_migration_preserves_saved_review(self):
        saved=self.save()
        with sqlite3.connect(self.db) as db:
            db.execute('DROP TABLE request_need_progress');db.execute('PRAGMA user_version=2')
        self.store=RequestStore(self.db)
        self.assertEqual(self.store.get(self.id)['need_review'],saved['need_review'])
        self.assertEqual(len(self.store.get(self.id)['need_progress']),2)
        with sqlite3.connect(self.db) as db:self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0],3)

    def test_old_schema_cannot_silently_use_new_contract_fields(self):
        from pydantic import ValidationError
        doc=contract();doc['schema_version']=2
        with self.assertRaises(ValidationError):self.save(doc)
        with self.assertRaises(RequestMissing):self.progress('need-1','in_progress')
