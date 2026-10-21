import csv
from importlib.util import find_spec
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import test_compare_features as fixtures
from test_semantic_experiment import FakeEncoder
from support_ticket_ai.finetune_experiment import (load_inputs, main, run_experiment,
                                                  training_subset)
from support_ticket_ai.data import load_tickets


class FineTuningExperimentTests(unittest.TestCase):
    def fixture(self, root):
        prepared, _, probes = fixtures.FeatureComparisonTests().fixture(root)
        negatives = root / 'negatives.csv'
        negatives.write_text('case_id,slice,text,expected_category,label_status\n'
                             'n1,outside,explain gravity,UNSUPPORTED,provisional\n')
        return prepared, probes, negatives

    def test_subset_reproducible_balanced_and_independent_of_row_order(self):
        with tempfile.TemporaryDirectory() as directory:
            prepared, _, _ = self.fixture(Path(directory))
            rows = load_tickets(prepared / 'train.csv', categories=frozenset({'ACCOUNT', 'PAYMENT'}))
            subset = training_subset(rows, 3, 42)
            self.assertEqual([r.ticket_id for r in subset],
                             [r.ticket_id for r in training_subset(list(reversed(rows)), 3, 42)])
            self.assertEqual(len(subset), 6)
            self.assertEqual(sum(r.category == 'ACCOUNT' for r in subset), 3)
            for invalid in (0, -1, True, .5):
                with self.assertRaises(ValueError):
                    training_subset(rows, invalid, 42)

    def test_checksum_failure_precedes_encoder_loading(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            prepared, probes, negatives = self.fixture(root)
            (prepared / 'validation.csv').write_text('changed')
            with patch('support_ticket_ai.finetune_experiment.load_encoder') as load:
                with self.assertRaisesRegex(ValueError, 'Checksum'):
                    run_experiment(prepared, root / 'cache', probes_path=probes, negatives_path=negatives)
                load.assert_not_called()

    def test_scope_training_overlap_with_development_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            prepared, probes, negatives = self.fixture(Path(directory))
            negatives.write_text(negatives.read_text().replace('explain gravity', 'compose a sonnet'))
            with self.assertRaisesRegex(ValueError, 'overlap'):
                load_inputs(prepared, probes, negatives)

    def test_train_validation_overlap_rejected_even_with_matching_checksum(self):
        from support_ticket_ai.robustness import fingerprint
        with tempfile.TemporaryDirectory() as directory:
            prepared, probes, negatives = self.fixture(Path(directory))
            path = prepared / 'validation.csv'
            with (prepared / 'train.csv').open() as handle:
                duplicate = next(csv.DictReader(handle))
            with path.open('a', newline='') as handle:
                csv.writer(handle).writerow([duplicate['ticket_id'], duplicate['text'], duplicate['category']])
            manifest = json.loads((prepared / 'manifest.json').read_text())
            manifest['split_sha256']['validation'] = fingerprint(path)
            (prepared / 'manifest.json').write_text(json.dumps(manifest))
            with self.assertRaisesRegex(ValueError, 'overlap'):
                load_inputs(prepared, probes, negatives)

    def test_orchestration_never_fits_evaluation_rows_or_reads_test(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            prepared, probes, negatives = self.fixture(root)
            self.assertFalse((prepared / 'test.csv').exists())
            fitting_ids = []
            def train(encoder, rows, categories, recipe):
                fitting_ids.extend(r.ticket_id for r in rows)
                return {'optimizer_steps': 1}
            with patch('support_ticket_ai.finetune_experiment.encoder_fingerprint', side_effect=['before', 'after']):
                report = run_experiment(prepared, root / 'cache', probes_path=probes, negatives_path=negatives,
                                        encoder_factory=lambda path: FakeEncoder(), trainer=train)
            train_ids = {r.ticket_id for r in load_tickets(prepared / 'train.csv', categories=frozenset({'ACCOUNT', 'PAYMENT'}))}
            val_ids = {r.ticket_id for r in load_tickets(prepared / 'validation.csv', categories=frozenset({'ACCOUNT', 'PAYMENT'}))}
            self.assertTrue(set(fitting_ids) <= train_ids)
            self.assertFalse(set(fitting_ids) & val_ids)
            self.assertEqual(report['fine_tuning_ticket_ids'], fitting_ids)
            self.assertTrue(report['test_double_used'])
            for key in ('test_evaluated', 'live_model_changed', 'candidate_bundle_exported',
                        'threshold_selection_performed', 'checkpoint_selection_performed', 'encoder_fine_tuned'):
                self.assertFalse(report[key])
            self.assertEqual(set(report['models']), {'frozen', 'fine_tuned'})
            self.assertEqual(report['models']['frozen']['development_with_scope']['ambiguous_rows'], 1)

    def test_unchanged_encoder_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            prepared, probes, negatives = self.fixture(root)
            with patch('support_ticket_ai.finetune_experiment.encoder_fingerprint', return_value='same'):
                with self.assertRaisesRegex(ValueError, 'did not change'):
                    run_experiment(prepared, root / 'cache', probes_path=probes, negatives_path=negatives,
                                   encoder_factory=lambda path: FakeEncoder(), trainer=lambda *args: {})

    def test_existing_report_preserved_and_failed_run_leaves_no_report(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'report.json'
            path.write_text('original')
            with patch('sys.argv', ['finetune', 'absent', str(path)]), \
                    patch('support_ticket_ai.finetune_experiment.run_experiment') as run:
                self.assertEqual(main(), 1)
                run.assert_not_called()
            self.assertEqual(path.read_text(), 'original')
            path.unlink()
            with patch('sys.argv', ['finetune', 'absent', str(path)]), \
                    patch('support_ticket_ai.finetune_experiment.run_experiment', side_effect=ValueError('failed')):
                self.assertEqual(main(), 1)
            self.assertFalse(path.exists())

    @unittest.skipUnless(find_spec('torch'), 'Optional Torch dependency is not installed')
    def test_real_autograd_updates_encoder_and_restores_inference_mode(self):
        import torch
        from support_ticket_ai.data import Ticket
        from support_ticket_ai.finetune_experiment import RECIPE, encoder_fingerprint, fine_tune_encoder

        class TinyEncoder(torch.nn.Module):
            def __init__(self):
                super().__init__()
                self.embeddings = torch.nn.Embedding(2, 384)

            def tokenize(self, texts):
                return {'ids': torch.tensor([0 if 'password' in text else 1 for text in texts])}

            def forward(self, features):
                return {'sentence_embedding': self.embeddings(features['ids'])}

        encoder = TinyEncoder()
        encoder.requires_grad_(False)
        before = encoder_fingerprint(encoder)
        records = [Ticket('a', 'password help', 'ACCOUNT'), Ticket('b', 'payment help', 'PAYMENT')]
        result = fine_tune_encoder(encoder, records, ['ACCOUNT', 'PAYMENT'], dict(RECIPE))
        self.assertNotEqual(before, encoder_fingerprint(encoder))
        self.assertEqual(result['optimizer_steps'], 1)
        self.assertFalse(encoder.training)
        self.assertTrue(all(not p.requires_grad for p in encoder.parameters()))
