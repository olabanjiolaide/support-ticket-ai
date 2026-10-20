import csv
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from support_ticket_ai.compare_features import build_character_model, compare, main
from support_ticket_ai.prepare import prepare
from support_ticket_ai.train import run_training


class FeatureComparisonTests(unittest.TestCase):
    def fixture(self, root):
        source = root / 'source.csv'
        with source.open('w', newline='') as handle:
            writer = csv.writer(handle)
            writer.writerow(['instruction', 'category'])
            for label, term in [('ACCOUNT', 'password reset'), ('PAYMENT', 'payment declined')]:
                for index in range(12):
                    writer.writerow([f'{term} request {index}', label])
        license_path = root / 'license.txt'
        license_path.write_text('Synthetic fixture')
        prepared = root / 'prepared'
        prepare(source, prepared, 'a' * 40, license_path)
        model = root / 'model'
        run_training(prepared, model)
        (prepared / 'test.csv').unlink()
        probes = root / 'probes.csv'
        with probes.open('w', newline='') as handle:
            writer = csv.writer(handle)
            writer.writerow(['case_id', 'slice', 'text', 'expected_category', 'label_status'])
            writer.writerows([['one', 'typo', 'passwrod reset plz', 'ACCOUNT', 'provisional'],
                              ['two', 'plain', 'compose a sonnet', 'UNSUPPORTED', 'provisional'],
                              ['three', 'ambiguous', 'please help me', 'REVIEW', 'provisional']])
        return prepared, model, probes

    def test_end_to_end_without_test_file_and_without_mutating_bundle(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            prepared, model, probes = self.fixture(root)
            before = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in model.iterdir()}
            report = compare(model, prepared, probes)
            self.assertFalse(report['test_evaluated'])
            self.assertFalse(report['live_model_changed'])
            self.assertFalse(report['candidate_bundle_exported'])
            self.assertEqual(report['label_status_counts'], {'provisional': 3})
            for result in report['models'].values():
                self.assertEqual(result['probes']['fixed_cutoff']['supported_rows'], 1)
                self.assertEqual(result['probes']['fixed_cutoff']['ambiguous_rows'], 1)
                self.assertEqual(result['validation']['confusion_matrix_labels'], ['ACCOUNT', 'PAYMENT'])
            self.assertEqual(before, {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in model.iterdir()})

    def test_tampered_validation_rejected_before_character_training(self):
        with tempfile.TemporaryDirectory() as directory:
            prepared, model, probes = self.fixture(Path(directory))
            with (prepared / 'validation.csv').open('a') as handle:
                handle.write('extra,untrusted text,ACCOUNT\n')
            with patch('support_ticket_ai.compare_features.build_character_model') as build:
                with self.assertRaisesRegex(ValueError, 'Checksum'):
                    compare(model, prepared, probes)
                build.assert_not_called()

    def test_probe_training_collision_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            prepared, model, probes = self.fixture(Path(directory))
            with (prepared / 'train.csv').open() as handle:
                text = next(csv.DictReader(handle))['text']
            content = probes.read_text().replace('passwrod reset plz', text)
            probes.write_text(content)
            with self.assertRaisesRegex(ValueError, 'overlap'):
                compare(model, prepared, probes)

    def test_character_vocabulary_is_fitted_before_probe_transformation(self):
        model = build_character_model()
        model.fit(['password reset', 'password login', 'payment card', 'payment refused'],
                  ['ACCOUNT', 'ACCOUNT', 'PAYMENT', 'PAYMENT'])
        before = dict(model.named_steps['tfidf'].vocabulary_)
        model.predict(['ZZZnovelprobeZZZ'])
        self.assertEqual(before, model.named_steps['tfidf'].vocabulary_)
        self.assertNotIn('zzz', before)

    def test_existing_report_is_preserved_without_training(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'report.json'
            path.write_text('original')
            with patch('sys.argv', ['compare_features', 'absent', 'absent', str(path)]), \
                    patch('support_ticket_ai.compare_features.compare') as run:
                self.assertEqual(main(), 1)
                run.assert_not_called()
            self.assertEqual(path.read_text(), 'original')
