import csv
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from support_ticket_ai.freeze_review import build_manifest, main, verify_manifest
from support_ticket_ai.review_cases import load_cases

ROOT = Path(__file__).resolve().parents[1]


class ReviewReservationTests(unittest.TestCase):
    def fixture(self, path, *, reverse=False, newline='\n'):
        rows = [{'case_id': f'case-{i}-{j}', 'family_id': f'family-{i}', 'text': f'request scenario {i} variation {j}'}
                for i in range(12) for j in range(2)]
        if reverse:
            rows.reverse()
        with path.open('w', newline='') as handle:
            writer = csv.DictWriter(handle, fieldnames=['case_id', 'family_id', 'text'], lineterminator=newline)
            writer.writeheader()
            writer.writerows(rows)
        return rows

    def test_all_cases_reserved_and_families_do_not_cross_partitions(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'cases.csv'
            rows = self.fixture(path)
            manifest = build_manifest(path)
            parts = [set(ids) for ids in manifest['partition_case_ids'].values()]
            self.assertEqual(set.union(*parts), {r['case_id'] for r in rows})
            for i, part in enumerate(parts):
                for other in parts[i+1:]:
                    self.assertFalse(part & other)
            for row in rows:
                split = manifest['family_partitions'][row['family_id']]
                self.assertIn(row['case_id'], manifest['partition_case_ids'][split])

    def test_assignments_and_canonical_hash_ignore_row_order_and_csv_newlines(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first, second = root / 'first.csv', root / 'second.csv'
            self.fixture(first)
            self.fixture(second, reverse=True, newline='\r\n')
            self.assertEqual(build_manifest(first), build_manifest(second))

    def test_modified_collection_or_partition_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cases, frozen = root / 'cases.csv', root / 'manifest.json'
            self.fixture(cases)
            manifest = build_manifest(cases)
            frozen.write_text(json.dumps(manifest))
            verify_manifest(cases, frozen)
            manifest['partition_case_ids']['audit'].append(manifest['partition_case_ids']['train'][0])
            frozen.write_text(json.dumps(manifest))
            with self.assertRaisesRegex(ValueError, 'changed'):
                verify_manifest(cases, frozen)
            frozen.write_text(json.dumps(build_manifest(cases)))
            cases.write_text(cases.read_text().replace('request scenario 0 variation 0', 'changed scenario'))
            with self.assertRaisesRegex(ValueError, 'changed'):
                verify_manifest(cases, frozen)

    def test_existing_reservation_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cases, frozen = root / 'cases.csv', root / 'manifest.json'
            self.fixture(cases)
            frozen.write_text('preserve me')
            with patch('sys.argv', ['freeze_review', str(cases), str(frozen)]):
                self.assertEqual(main(), 1)
            self.assertEqual(frozen.read_text(), 'preserve me')

    def test_too_few_families_fail_before_reservation(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'cases.csv'
            path.write_text('case_id,family_id,text\none,one,Only one family\n')
            with self.assertRaisesRegex(ValueError, 'six'):
                build_manifest(path)

    def test_shipped_collection_is_unlabeled_and_reserved_before_training(self):
        path = ROOT / 'data/ambiguity_review_cases.csv'
        rows = load_cases(path)
        self.assertEqual(len(rows), 72)
        self.assertEqual(set(rows[0]), {'case_id', 'family_id', 'text'})
        manifest = verify_manifest(path, ROOT / 'data/ambiguity_review_manifest.json')
        self.assertEqual(manifest['partition_row_counts'], {'train': 48, 'selection': 12, 'audit': 12})
        self.assertTrue(manifest['labels_pending'])
        self.assertFalse(manifest['independent_audit_established'])
