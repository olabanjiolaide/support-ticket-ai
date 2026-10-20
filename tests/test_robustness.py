import csv
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from support_ticket_ai.robustness import (PROBES_PATH, check_training_overlap,
                                          diagnostic_metrics, evaluate, load_probes)

CATEGORIES = {'ACCOUNT', 'CANCEL', 'CONTACT', 'DELIVERY', 'FEEDBACK', 'INVOICE', 'ORDER',
              'PAYMENT', 'REFUND', 'SHIPPING', 'SUBSCRIPTION'}


class RobustnessTests(unittest.TestCase):
    def test_shipped_probes_are_provisional_and_cover_each_category_and_slice(self):
        rows = load_probes(PROBES_PATH, CATEGORIES)
        self.assertEqual(len(rows), 98)
        self.assertTrue(all(row['label_status'] == 'provisional' for row in rows))
        for category in CATEGORIES:
            cases = [row for row in rows if row['expected_category'] == category]
            self.assertEqual(len(cases), 6)
            self.assertEqual({row['slice'] for row in cases}, {'plain', 'typo', 'indirect'})

    def test_ambiguous_cases_do_not_inflate_supported_accuracy(self):
        rows = [{'expected_category': 'ACCOUNT', 'top_category': 'ACCOUNT', 'score': .7},
                {'expected_category': 'REVIEW', 'top_category': 'ORDER', 'score': .9},
                {'expected_category': 'REVIEW', 'top_category': 'PAYMENT', 'score': .2},
                {'expected_category': 'UNSUPPORTED', 'top_category': 'ACCOUNT', 'score': .8}]
        result = diagnostic_metrics(rows, .7)
        self.assertEqual(result['supported_rows'], 1)
        self.assertEqual(result['selected_supported_accuracy'], 1)
        self.assertEqual(result['selected_supported_rows'], 1)  # threshold equality passes
        self.assertEqual(result['unsupported_suggestions'], 1)
        self.assertEqual(result['ambiguous_withheld_fraction'], .5)
        self.assertIsNone(diagnostic_metrics([], .7)['selected_supported_accuracy'])

    def test_duplicate_normalized_text_and_invalid_labels_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'probes.csv'
            for label, text, error in [('ACCOUNT', ' HELLO ', 'Duplicate'),
                                       ('MISSING', 'different', 'category')]:
                with path.open('w', newline='') as handle:
                    writer = csv.writer(handle)
                    writer.writerow(['case_id', 'slice', 'text', 'expected_category', 'label_status'])
                    writer.writerow(['one', 'plain', 'hello', 'ACCOUNT', 'provisional'])
                    writer.writerow(['two', 'plain', text, label, 'provisional'])
                with self.assertRaisesRegex(ValueError, error):
                    load_probes(path, {'ACCOUNT'})

    def test_overlap_check_uses_matching_train_only_and_detects_tampering(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            train = root / 'train.csv'
            train.write_text('ticket_id,text,category\n1,Hello world,ACCOUNT\n')
            manifest = root / 'manifest.json'
            manifest.write_text(json.dumps({'split_sha256': {'train': hashlib.sha256(train.read_bytes()).hexdigest()}}))
            metadata = {'preparation_manifest_sha256': hashlib.sha256(manifest.read_bytes()).hexdigest()}
            # No validation.csv or test.csv exists: neither is needed or read.
            result = check_training_overlap(root, metadata,
                                            [{'case_id': 'collision', 'text': 'HELLO   world'}], {'ACCOUNT'})
            self.assertEqual(result['exact_overlap_case_ids'], ['collision'])
            train.write_text(train.read_text() + '2,Other text,ACCOUNT\n')
            with self.assertRaisesRegex(ValueError, 'checksum'):
                check_training_overlap(root, metadata, [], {'ACCOUNT'})
            with self.assertRaisesRegex(ValueError, 'manifest'):
                check_training_overlap(root, {'preparation_manifest_sha256': 'wrong'}, [], {'ACCOUNT'})

    def test_invalid_thresholds_fail_before_loading_model(self):
        with patch('support_ticket_ai.robustness.TicketPredictor') as predictor:
            for threshold in (float('nan'), float('inf'), 0, -1, 1.1, True):
                with self.assertRaises(ValueError):
                    evaluate(Path('absent'), Path('absent'), threshold=threshold)
            predictor.assert_not_called()
