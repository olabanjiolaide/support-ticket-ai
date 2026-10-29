import copy
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import sqlite3
import tempfile
import unittest
from uuid import uuid4

from fastapi.testclient import TestClient
from support_ticket_ai.api import create_app
from support_ticket_ai.breakdown import preview
from support_ticket_ai.request_store import RequestStore, StoreConflict

TEXT = 'My order was cancelled last week. I cannot find the item again. Is it out of stock?'


def document(text=TEXT):
    parts = preview(text)['parts']
    return {'schema_version':1, 'source_text':text,
            'parts':[{k:p[k] for k in ('id','start','end','text')} | {
                'role':'context' if i==0 else 'request', 'group_id':'need-1','category':None}
                     for i,p in enumerate(parts)],
            'groups':[{'id':'need-1','title':'Locate the item and check availability','category':'ORDER'}],
            'clarification':'Could you share the product name or link?'}


class NeedReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.db=Path(self.temp.name)/'requests.sqlite3'
        self.client=self.enterContext(TestClient(create_app(requests_db=self.db)))
        self.record=self.client.post('/requests',json={'text':TEXT,'client_request_id':str(uuid4()),'include_prediction':False}).json()

    def save(self, review=None, version=None, status=200):
        response=self.client.post(f"/requests/{self.record['id']}/needs-review",json={
            'version':self.record['version'] if version is None else version,'actor':'Ola',
            'review':document() if review is None else review})
        self.assertEqual(response.status_code,status,response.text)
        return response.json()

    def test_structured_review_preserves_lifecycle_source_and_history(self):
        result=self.save()
        for key in ('message','prediction','status','review_state','confirmed_category','resolution_note','resolved_at'):
            self.assertEqual(result[key],self.record[key])
        self.assertEqual(result['version'],2)
        self.assertEqual(result['need_review']['review'],document())
        event=result['history'][-1]
        self.assertEqual(event['action'],'needs_review')
        self.assertIsNone(event['before']['need_review'])
        self.assertEqual(event['after']['need_review'],document())
        changed=document();changed['groups'][0]['title']='Find the missing product listing'
        later=self.save(changed,version=2)
        self.assertEqual(later['history'][-1]['before']['need_review'],document())
        self.assertEqual(later['history'][-1]['after']['need_review'],changed)
        self.assertEqual(RequestStore(self.db).get(self.record['id'])['need_review']['review'],changed)
        self.assertEqual(self.client.get('/requests/overview').json()['pending_review'],1)

    def test_preserve_all_exact_evidence_and_reject_duplicate_or_forged_spans(self):
        for mutation in ['omit','duplicate','offset','text','unknown']:
            review=document()
            if mutation=='omit': review['parts'].pop()
            elif mutation=='duplicate': review['parts'][1]=copy.deepcopy(review['parts'][0])
            elif mutation=='offset': review['parts'][0]['end']-=1
            elif mutation=='text': review['parts'][0]['text']='forged evidence'
            else: review['parts'][0]['id']='part-12'
            self.save(review,status=422)
        self.assertEqual(self.client.get(f"/requests/{self.record['id']}").json()['version'],1)

    def test_reject_unassigned_requests_background_only_unknown_groups_and_duplicate_groups(self):
        for mutation in ['unassigned','background','reference','duplicate','unreviewed']:
            review=document()
            if mutation=='unassigned': review['parts'][1]['group_id']=None
            elif mutation=='background':
                for part in review['parts']: part['role']='context'
            elif mutation=='reference': review['parts'][1]['group_id']='need-2'
            elif mutation=='duplicate': review['groups'].append(copy.deepcopy(review['groups'][0]))
            else: review['parts'][0]['role']='unconfirmed'
            self.save(review,status=422)

    def test_need_categories_are_separate_from_fragment_categories(self):
        for category in ['ACCOUNT','OUTSIDE_SCOPE','UNCLEAR']:
            review=document();review['parts'][1]['category']=category
            self.save(review,status=422)
        review=document();review['groups'][0]['category']='OUTSIDE_SCOPE'
        self.assertEqual(self.save(review)['need_review']['review']['groups'][0]['category'],'OUTSIDE_SCOPE')

    def test_unresolved_relationship_requires_clarification(self):
        for role in ['conditional','alternative','unclear']:
            review=document();review['parts'][1]['role']=role;review['clarification']=''
            self.save(review,status=422)
        review=document();review['groups'][0]['category']='UNCLEAR';review['clarification']=''
        self.save(review,status=422)

    def test_foreign_original_source_is_rejected_even_with_valid_spans(self):
        review=document(TEXT.replace('last week','yesterday'))
        self.save(review,status=409)

    def test_stale_version_conflicts_without_overwriting(self):
        self.save()
        review=document();review['groups'][0]['title']='Stale replacement'
        self.save(review,status=409)
        current=self.client.get(f"/requests/{self.record['id']}").json()
        self.assertEqual(current['need_review']['review'],document())
        self.assertEqual(len(current['history']),2)

    def test_atomic_concurrent_group_reviews(self):
        repository=RequestStore(self.db)
        def write(actor):
            try:
                repository.save_need_review(self.record['id'],version=1,actor=actor,review=document())
                return 'saved'
            except StoreConflict:
                return 'conflict'
        with ThreadPoolExecutor(max_workers=2) as executor:
            self.assertEqual(sorted(executor.map(write,['one','two'])),['conflict','saved'])
        self.assertEqual(len(repository.get(self.record['id'])['history']),2)

    def test_schema_one_migration_is_additive_and_retains_existing_requests(self):
        with sqlite3.connect(self.db) as db:
            db.execute('DROP TABLE request_need_reviews');db.execute('PRAGMA user_version=1')
        repository=RequestStore(self.db)
        self.assertEqual(repository.get(self.record['id'])['message'],TEXT)
        self.assertEqual(len(repository.get(self.record['id'])['history']),1)
        with sqlite3.connect(self.db) as db:
            self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0],4)
        self.save()

    def test_resolved_request_requires_reopening_before_editing_groups(self):
        repository=RequestStore(self.db)
        record=repository.change(self.record['id'],version=1,action='review',actor='Ola',category='ORDER')
        record=repository.change(record['id'],version=record['version'],action='start',actor='Ola')
        record=repository.change(record['id'],version=record['version'],action='resolve',actor='Ola',note='Product located.')
        self.save(version=record['version'],status=409)

    def test_strict_bounds_and_no_fabricated_model_provenance(self):
        for mutation in ['title','category','model','version','extra']:
            review=document()
            if mutation=='title':review['groups'][0]['title']=' '
            elif mutation=='category':review['groups'][0]['category']='INVENTED'
            elif mutation=='model':review['groups'][0]['model_sha256']='a'*64
            elif mutation=='version':review['schema_version']=True
            else:review['private_customer_data']='do not echo this'
            response=self.save(review,status=422)
            self.assertNotIn('do not echo this',str(response))

    def test_zero_needs_when_everything_is_background(self):
        review=document();review['groups']=[]
        for part in review['parts']:part.update(role='context',group_id=None)
        result=self.save(review)
        self.assertEqual(result['need_review']['review']['groups'],[])
