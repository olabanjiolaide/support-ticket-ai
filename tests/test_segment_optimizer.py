import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.multiclass import OneVsRestClassifier

import test_multilabel_baseline as fixtures
import test_semantic_multilabel as encoders
from support_ticket_ai.resources import data_path
from support_ticket_ai.segment_optimizer import (discrepancies, duplicate_features, run,
                                                 transformed_probabilities, validate_protocol)


class SegmentOptimizerTests(unittest.TestCase):
    def prepared(self, root):
        manifest = fixtures.MultilabelBaselineTests.fixture(self, root)
        protocol = json.loads(data_path('segment_optimizer_protocol.json').read_text())
        protocol['development_input_sha256'] = manifest['files_sha256']
        path = root / 'protocol.json'
        path.write_text(json.dumps(protocol))
        return manifest, protocol, path

    def test_exact_parameter_transform_preserves_all_scores_without_refitting(self):
        features = np.array([[1., 0.], [0., 1.], [1., 1.], [-1., .2], [.1, -1.]])
        targets = np.array([[1, 0], [0, 1], [1, 1], [0, 1], [1, 0]])
        model = OneVsRestClassifier(LogisticRegression(C=10., tol=1e-8)).fit(features, targets)
        expected = model.predict_proba(features)
        actual = transformed_probabilities(model, duplicate_features(features))
        np.testing.assert_allclose(actual, expected, atol=1e-12)
        self.assertEqual(discrepancies(expected, actual)['rows_with_different_predicted_sets'], 0)

    def test_discrepancy_counts_rows_instead_of_individual_labels(self):
        result = discrepancies(np.array([[.8, .7], [.1, .2]]), np.array([[.2, .1], [.1, .3]]))
        self.assertEqual(result['rows_with_different_predicted_sets'], 1)
        self.assertAlmostEqual(result['max_absolute_score_difference'], .6)

    def test_four_train_only_fits_use_declared_tolerances_and_caps(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _, _, path = self.prepared(root)
            encoder = encoders.FakeEncoder()
            original_fit, original_open = OneVsRestClassifier.fit, Path.open
            fits = []
            def fit(heads, x, y, **kwargs):
                self.assertEqual(len(x), 12)
                self.assertEqual(y.shape, (12, 2))
                fits.append((heads.estimator.tol, heads.estimator.max_iter, x.shape[1]))
                return original_fit(heads, x, y, **kwargs)
            def guarded(path, *args, **kwargs):
                if path.parent == root:
                    self.assertIn(path.name, {'manifest.json', 'train.jsonl', 'selection.jsonl', 'protocol.json'})
                return original_open(path, *args, **kwargs)
            with patch.object(OneVsRestClassifier, 'fit', fit), patch.object(Path, 'open', guarded):
                report = run(root, root, path, encoder_factory=lambda _: encoder)
            self.assertEqual(fits, [(1e-4, 5000, 384), (1e-4, 5000, 768),
                                    (1e-8, 5000, 384), (1e-8, 5000, 768)])
            self.assertEqual(len(encoder.batches), 2)
            self.assertFalse(report['model_selection_performed'])
            self.assertFalse(report['calibration_read'])
            self.assertFalse(report['test_evaluated'])
            self.assertFalse(report['live_model_changed'])

    def test_protocol_grid_and_fingerprints_fail_before_encoder_load(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest, protocol, path = self.prepared(root)
            for key, value in [('tolerances', [1e-5]), ('max_iter', 1000), ('C', 1.)]:
                changed = copy.deepcopy(protocol)
                changed[key] = value
                with self.assertRaises(ValueError):
                    validate_protocol(changed, manifest)
            protocol['development_input_sha256']['train.jsonl'] = '0' * 64
            path.write_text(json.dumps(protocol))
            with patch('support_ticket_ai.segment_optimizer.load_encoder') as load:
                with self.assertRaisesRegex(ValueError, 'fingerprints'):
                    run(root, root, path)
                load.assert_not_called()


if __name__ == '__main__':
    unittest.main()
