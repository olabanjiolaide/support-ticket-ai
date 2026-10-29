"""Local SQLite request workflow; predictions are immutable, reviews are explicit."""

from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sqlite3
from uuid import uuid4

CATEGORIES = ('ACCOUNT', 'CANCEL', 'CONTACT', 'DELIVERY', 'FEEDBACK', 'INVOICE',
              'ORDER', 'PAYMENT', 'REFUND', 'SHIPPING', 'SUBSCRIPTION')
STATUSES = ('open', 'needs_clarification', 'in_progress', 'resolved')


class StoreConflict(ValueError):
    pass


class RequestMissing(LookupError):
    pass


def now():
    return datetime.now(timezone.utc).isoformat(timespec='microseconds')


def payload_hash(payload):
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def lifecycle(row):
    return {key: row[key] for key in ('status', 'review_state', 'confirmed_category', 'resolution_note', 'resolved_at', 'version')}


class RequestStore:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self.connect()) as db:
            version = db.execute('PRAGMA user_version').fetchone()[0]
            if version not in (0, 1, 2):
                raise ValueError('Unsupported request database schema.')
            if version == 0:
                with db:
                    db.executescript('''
                    BEGIN IMMEDIATE;
                    CREATE TABLE requests (
                      id TEXT PRIMARY KEY, client_request_id TEXT NOT NULL UNIQUE,
                      payload_hash TEXT NOT NULL, message TEXT NOT NULL,
                      prediction_json TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                      status TEXT NOT NULL CHECK(status IN ('open','needs_clarification','in_progress','resolved')),
                      review_state TEXT NOT NULL CHECK(review_state IN ('pending','reviewed')),
                      confirmed_category TEXT, latest_note TEXT NOT NULL DEFAULT '',
                      resolution_note TEXT, resolved_at TEXT, version INTEGER NOT NULL CHECK(version > 0)
                    );
                    CREATE TABLE request_events (
                      sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                      request_id TEXT NOT NULL REFERENCES requests(id),
                      happened_at TEXT NOT NULL, actor TEXT NOT NULL, action TEXT NOT NULL,
                      note TEXT NOT NULL, before_json TEXT, after_json TEXT NOT NULL
                    );
                    CREATE INDEX requests_updated ON requests(created_at DESC,id DESC);
                    CREATE INDEX requests_status ON requests(status,review_state);
                    CREATE INDEX events_request ON request_events(request_id,sequence);
                    CREATE TRIGGER immutable_request_source BEFORE UPDATE OF message,prediction_json,created_at,client_request_id,payload_hash ON requests
                    BEGIN SELECT RAISE(ABORT,'Original request and prediction are immutable'); END;
                    PRAGMA user_version=1;
                    COMMIT;
                    ''')
            if version < 2:
                with db:
                    db.executescript("""
                    BEGIN IMMEDIATE;
                    CREATE TABLE IF NOT EXISTS request_need_reviews (
                      request_id TEXT PRIMARY KEY REFERENCES requests(id),
                      reviewed_at TEXT NOT NULL, actor TEXT NOT NULL,
                      request_version INTEGER NOT NULL, review_json TEXT NOT NULL
                    );
                    PRAGMA user_version=2;
                    COMMIT;
                    """)
            db.execute('SELECT id,version FROM requests LIMIT 0')

    def connect(self):
        db = sqlite3.connect(self.path, timeout=5)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        return db

    @staticmethod
    def record(row):
        result = dict(row)
        result['message'] = result.pop('message')
        result['prediction'] = json.loads(result.pop('prediction_json')) if result['prediction_json'] else None
        result.pop('prediction_json', None)
        result.pop('client_request_id', None)
        result.pop('payload_hash', None)
        return result

    @staticmethod
    def event(db, request_id, actor, action, note, before, after, timestamp):
        db.execute('INSERT INTO request_events(request_id,happened_at,actor,action,note,before_json,after_json) VALUES(?,?,?,?,?,?,?)',
                   (request_id, timestamp, actor, action, note,
                    json.dumps(before) if before is not None else None, json.dumps(after)))

    def existing(self, key, digest):
        with closing(self.connect()) as db:
            row = db.execute('SELECT * FROM requests WHERE client_request_id=?', (key,)).fetchone()
            if row and row['payload_hash'] != digest:
                raise StoreConflict('This save key was already used for another request.')
            return self.record(row) if row else None

    def create(self, key, digest, message, prediction):
        with closing(self.connect()) as db, db:
            db.execute('BEGIN IMMEDIATE')
            old = db.execute('SELECT * FROM requests WHERE client_request_id=?', (key,)).fetchone()
            if old:
                if old['payload_hash'] != digest:
                    raise StoreConflict('This save key was already used for another request.')
                return self.record(old)
            request_id, timestamp = str(uuid4()), now()
            db.execute('INSERT INTO requests(id,client_request_id,payload_hash,message,prediction_json,created_at,updated_at,status,review_state,version) VALUES(?,?,?,?,?,?,?,?,?,?)',
                       (request_id, key, digest, message, json.dumps(prediction, allow_nan=False) if prediction is not None else None,
                        timestamp, timestamp, 'open', 'pending', 1))
            row = db.execute('SELECT * FROM requests WHERE id=?', (request_id,)).fetchone()
            self.event(db, request_id, 'Local user', 'created', '', None, lifecycle(row), timestamp)
            return self.record(row)

    def get(self, request_id):
        with closing(self.connect()) as db, db:
            # Keep version, history and the latest grouped review in one read snapshot.
            db.execute('BEGIN')
            row = db.execute('SELECT * FROM requests WHERE id=?', (request_id,)).fetchone()
            if row is None:
                raise RequestMissing('Saved request not found.')
            result = self.record(row)
            events = []
            for event in db.execute('SELECT * FROM request_events WHERE request_id=? ORDER BY sequence', (request_id,)):
                item = dict(event)
                item['before'] = json.loads(item.pop('before_json')) if item['before_json'] else None
                item.pop('before_json', None)
                item['after'] = json.loads(item.pop('after_json'))
                events.append(item)
            result['history'] = events
            review = db.execute('SELECT * FROM request_need_reviews WHERE request_id=?', (request_id,)).fetchone()
            result['need_review'] = None
            if review:
                result['need_review'] = {**dict(review), 'review': json.loads(review['review_json'])}
                result['need_review'].pop('review_json')
            return result

    def list(self, *, q='', status=None, category=None, review_state=None, queue=None, limit=20, offset=0):
        clauses, parameters = [], []
        for column, value in (('status', status), ('confirmed_category', category), ('review_state', review_state)):
            if value is not None:
                clauses.append(f'{column}=?')
                parameters.append(value)
        if queue == 'review':
            clauses.append("(review_state='pending' OR status='needs_clarification')")
        if q:
            escaped = q.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
            clauses.append("(message LIKE ? ESCAPE '\\' OR id LIKE ? ESCAPE '\\' OR latest_note LIKE ? ESCAPE '\\')")
            id_search = q[4:] if re.fullmatch(r'REQ-[0-9a-f-]+', q, flags=re.I) else q
            id_search = id_search.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
            parameters += [f'%{escaped}%', f'%{id_search}%', f'%{escaped}%']
        where = ' WHERE ' + ' AND '.join(clauses) if clauses else ''
        with closing(self.connect()) as db, db:
            # A read transaction keeps total and page consistent during writes.
            db.execute('BEGIN')
            total = db.execute('SELECT COUNT(*) FROM requests' + where, parameters).fetchone()[0]
            rows = db.execute('SELECT * FROM requests' + where + ' ORDER BY created_at DESC,id DESC LIMIT ? OFFSET ?', parameters + [limit, offset])
            return {'items': [self.record(row) for row in rows], 'total': total, 'limit': limit, 'offset': offset}

    def change(self, request_id, *, version, action, actor, note='', category=None):
        if not actor.strip() or len(actor) > 80 or len(note) > 2000:
            raise ValueError('Use a reviewer label and a note of at most 2,000 characters.')
        if action not in {'review', 'clarify', 'start', 'resolve', 'reopen', 'note'}:
            raise ValueError('Unknown request action.')
        if action == 'review' and category not in CATEGORIES:
            raise ValueError('Choose a supported category for the human review.')
        if action in {'clarify', 'resolve', 'reopen', 'note'} and not note.strip():
            raise ValueError('A note is required for this action.')
        with closing(self.connect()) as db, db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT * FROM requests WHERE id=?', (request_id,)).fetchone()
            if row is None:
                raise RequestMissing('Saved request not found.')
            if row['version'] != version:
                raise StoreConflict('This request changed in another tab. Reload it before saving your changes.')
            before = lifecycle(row)
            after = dict(before)
            if row['status'] == 'resolved' and action not in {'reopen', 'note'}:
                raise StoreConflict('Reopen the resolved request before changing its review or handling status.')
            if action == 'review':
                after.update(confirmed_category=category, review_state='reviewed')
                if after['status'] == 'needs_clarification':
                    after['status'] = 'open'
            elif action == 'clarify':
                after.update(status='needs_clarification', review_state='pending', confirmed_category=None)
            elif action == 'start':
                if row['status'] != 'open' or row['review_state'] != 'reviewed' or not row['confirmed_category']:
                    raise StoreConflict('Confirm a category on an open request before starting work.')
                after['status'] = 'in_progress'
            elif action == 'resolve':
                if row['status'] != 'in_progress' or row['review_state'] != 'reviewed' or not row['confirmed_category']:
                    raise StoreConflict('Review the category and start handling the request before resolving it.')
                after.update(status='resolved', resolution_note=note, resolved_at=now())
            elif action == 'reopen':
                if row['status'] != 'resolved':
                    raise StoreConflict('Only a resolved request can be reopened.')
                after.update(status='open', review_state='pending', confirmed_category=None, resolution_note=None, resolved_at=None)
            after['version'] += 1
            timestamp = now()
            db.execute('UPDATE requests SET status=?,review_state=?,confirmed_category=?,resolution_note=?,resolved_at=?,version=?,updated_at=?,latest_note=? WHERE id=?',
                       (after['status'], after['review_state'], after['confirmed_category'], after['resolution_note'],
                        after['resolved_at'], after['version'], timestamp, note if note else row['latest_note'], request_id))
            self.event(db, request_id, actor.strip(), action, note.strip(), before, after, timestamp)
        return self.get(request_id)

    def save_need_review(self, request_id, *, version, actor, review):
        from .need_review import NeedReview
        # Revalidate at the persistence boundary, including direct store callers.
        document = NeedReview.model_validate(review).model_dump(mode='json', exclude_unset=True)
        if type(version) is not int or version < 1 or not actor.strip() or len(actor) > 80:
            raise ValueError('Use an expected version and reviewer label.')
        with closing(self.connect()) as db, db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT * FROM requests WHERE id=?', (request_id,)).fetchone()
            if row is None:
                raise RequestMissing('Saved request not found.')
            if row['version'] != version:
                raise StoreConflict('This request changed in another tab. Reload it before saving your changes.')
            if row['status'] == 'resolved':
                raise StoreConflict('Reopen the resolved request before changing its needs review.')
            if document['source_text'] != row['message']:
                raise StoreConflict('The review source does not match the saved original message.')
            timestamp = now()
            old = db.execute('SELECT review_json FROM request_need_reviews WHERE request_id=?', (request_id,)).fetchone()
            before = {**lifecycle(row), 'need_review': json.loads(old[0]) if old else None}
            db.execute('UPDATE requests SET version=version+1,updated_at=? WHERE id=?', (timestamp,request_id))
            db.execute("""INSERT INTO request_need_reviews(request_id,reviewed_at,actor,request_version,review_json)
                          VALUES(?,?,?,?,?) ON CONFLICT(request_id) DO UPDATE SET
                          reviewed_at=excluded.reviewed_at, actor=excluded.actor,
                          request_version=excluded.request_version, review_json=excluded.review_json""",
                       (request_id,timestamp,actor.strip(),version+1,json.dumps(document,ensure_ascii=False)))
            after_row = db.execute('SELECT * FROM requests WHERE id=?', (request_id,)).fetchone()
            after = {**lifecycle(after_row), 'need_review': document}
            self.event(db,request_id,actor.strip(),'needs_review','',before,after,timestamp)
        return self.get(request_id)

    def overview(self):
        with closing(self.connect()) as db, db:
            db.execute('BEGIN')
            rows = db.execute('SELECT status,review_state,confirmed_category,COUNT(*) AS count FROM requests GROUP BY status,review_state,confirmed_category').fetchall()
            by_status = dict.fromkeys(STATUSES, 0)
            by_category, pending, ready, total = {}, 0, 0, 0
            for row in rows:
                count = row['count']
                total += count
                by_status[row['status']] += count
                if row['review_state'] == 'pending' or row['status'] == 'needs_clarification':
                    pending += count
                if row['status'] == 'open' and row['review_state'] == 'reviewed':
                    ready += count
                if row['confirmed_category']:
                    by_category[row['confirmed_category']] = by_category.get(row['confirmed_category'], 0) + count
            recent = [dict(row) for row in db.execute('SELECT request_id,happened_at,actor,action FROM request_events ORDER BY sequence DESC LIMIT 10')]
            return {'total': total, 'by_status': by_status, 'pending_review': pending, 'ready_to_handle': ready,
                    'confirmed_categories': by_category, 'recent_activity': recent}
