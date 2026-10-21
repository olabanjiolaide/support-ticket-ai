import csv
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
from scipy import sparse
from sklearn.feature_extraction.text import TfidfVectorizer

import test_compare_features as fixtures
from test_semantic_experiment import FakeEncoder
from support_ticket_ai.data import load_tickets
from support_ticket_ai.hybrid_experiment import combine_features, main, run_experiment


class HybridExperimentTests(unittest.TestCase):
    def fixture(self, root):
        prepared, _, probes = fixtures.FeatureComparisonTests().fixture(root)
        negatives = root / 'negatives.csv'
        negatives.write_text('case_id,slice,text,expected_category,label_status\n'
                             'n1,outside,explain gravity,UNSUPPORTED,provisional\n')
        return prepared, probes, negatives

    def test_combination_sparse_aligned_normalized_and_finite(self):
        embeddings = np.zeros((2, 384))
        embeddings[:, 0] = 1
        characters = sparse.csr_matrix([[1, 0, 0], [0, 0, 0]], dtype=float)
        joint = combine_features(embeddings, characters)
        self.assertTrue(sparse.issparse(joint))
        self.assertEqual(joint.shape, (2, 387))
        np.testing.assert_allclose(np.asarray(joint.multiply(joint).sum(axis=1)).ravel(), [1, 1])
        self.assertAlmostEqual(joint[0, 0], 1 / np.sqrt(2))
        self.assertAlmostEqual(joint[0, 384], 1 / np.sqrt(2))
        self.assertEqual(joint[1, 0], 1)
        for embedding, character in [(embeddings[:1], characters), (np.zeros((2, 3)), characters),
                                      (np.full((2, 384), np.nan), characters),
                                      (embeddings, sparse.csr_matrix([[np.inf], [0]]))]:
            with self.assertRaises(ValueError):
                combine_features(embedding, character)

    def test_vocabulary_fits_train_only_and_scope_scores_are_shared(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            prepared, probes, negatives = self.fixture(root)
            train_texts = [r.text for r in load_tickets(prepared / 'train.csv', categories=frozenset({'ACCOUNT', 'PAYMENT'}))]
            fit_calls = []
            class RecordingVectorizer(TfidfVectorizer):
                def fit_transform(self, raw_documents, y=None):
                    fit_calls.append(list(raw_documents))
                    values = super().fit_transform(raw_documents, y)
                    self.train_vocabulary = dict(self.vocabulary_)
                    self.train_idf = self.idf_.copy()
                    return values
            vectorizers = []
            def factory(**kwargs):
                instance = RecordingVectorizer(**kwargs)
                vectorizers.append(instance)
                return instance
            with patch('support_ticket_ai.hybrid_experiment.TfidfVectorizer', side_effect=factory):
                report = run_experiment(prepared, root / 'cache', probes_path=probes,
                                        negatives_path=negatives, encoder_factory=lambda p: FakeEncoder())
            self.assertEqual(fit_calls, [train_texts])
            self.assertEqual(vectorizers[0].train_vocabulary, vectorizers[0].vocabulary_)
            np.testing.assert_array_equal(vectorizers[0].train_idf, vectorizers[0].idf_)
            self.assertFalse((prepared / 'test.csv').exists())
            self.assertTrue(report['test_double_used'])
            for key in ('test_evaluated', 'live_model_changed', 'candidate_bundle_exported',
                        'threshold_selection_performed', 'encoder_fine_tuned'):
                self.assertFalse(report[key])
            semantic, hybrid = [report['models'][name] for name in ('semantic', 'hybrid')]
            self.assertEqual([r['scope_score'] for r in semantic['cases']],
                             [r['scope_score'] for r in hybrid['cases']])
            self.assertEqual(hybrid['development_with_scope']['ambiguous_rows'], 1)
            for row in hybrid['cases']:
                self.assertEqual(row['accepted_with_scope'], row['score'] >= .5 and row['scope_score'] >= .5)

    def test_invalid_validation_precedes_model_loading(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            prepared, probes, negatives = self.fixture(root)
            (prepared / 'validation.csv').write_text('changed')
            with patch('support_ticket_ai.hybrid_experiment.load_encoder') as load:
                with self.assertRaisesRegex(ValueError, 'Checksum'):
                    run_experiment(prepared, root / 'cache', probes_path=probes, negatives_path=negatives)
                load.assert_not_called()

    def test_negative_overlap_rejected_before_encoder_loading(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            prepared, probes, negatives = self.fixture(root)
            with probes.open() as handle:
                request = next(csv.DictReader(handle))['text']
            negatives.write_text(negatives.read_text().replace('explain gravity', request))
            with patch('support_ticket_ai.hybrid_experiment.load_encoder') as load:
                with self.assertRaisesRegex(ValueError, 'overlap'):
                    run_experiment(prepared, root / 'cache', probes_path=probes, negatives_path=negatives)
                load.assert_not_called()

    def test_existing_report_preserved_and_partial_report_removed(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'report.json'
            output.write_text('original')
            with patch('sys.argv', ['hybrid', 'absent', str(output)]), \
                    patch('support_ticket_ai.hybrid_experiment.run_experiment') as run:
                self.assertEqual(main(), 1)
                run.assert_not_called()
            self.assertEqual(output.read_text(), 'original')
            output.unlink()
            with patch('sys.argv', ['hybrid', 'absent', str(output)]), \
                    patch('support_ticket_ai.hybrid_experiment.run_experiment', side_effect=ValueError('failed')):
                self.assertEqual(main(), 1)
            self.assertFalse(output.exists())
