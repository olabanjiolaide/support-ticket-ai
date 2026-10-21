import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
from sklearn.multiclass import OneVsRestClassifier

import test_segment_pooling as fixtures
import test_semantic_multilabel as encoders
from support_ticket_ai.resources import data_path
from support_ticket_ai.segment_pooling import check_numerical_control, run, validate_protocol


class StableSegmentTests(unittest.TestCase):
    def prepared(self, root):
        manifest, _, path = fixtures.SegmentPoolingTests.prepared(self, root)
        protocol = json.loads(data_path('segment_stable_protocol.json').read_text())
        protocol['development_input_sha256'] = manifest['files_sha256']
        path.write_text(json.dumps(protocol))
        return manifest, protocol, path

    def test_all_four_train_only_fits_use_same_strict_settings(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _, _, path = self.prepared(root)
            original_fit, original_open = OneVsRestClassifier.fit, Path.open
            settings = []
            def fit(heads, x, y, **kwargs):
                self.assertEqual(len(x), 12)
                self.assertEqual(y.shape, (12, 3))
                settings.append((heads.estimator.tol, heads.estimator.max_iter, heads.estimator.C))
                return original_fit(heads, x, y, **kwargs)
            def guarded(path, *args, **kwargs):
                if path.parent == root:
                    self.assertIn(path.name, {'manifest.json', 'train.jsonl', 'selection.jsonl', 'protocol.json'})
                return original_open(path, *args, **kwargs)
            with patch.object(OneVsRestClassifier, 'fit', fit), patch.object(Path, 'open', guarded):
                report = run(root, root, path, encoder_factory=lambda _: encoders.FakeEncoder())
            self.assertEqual(settings, [(1e-8, 5000, 10.)] * 4)
            self.assertTrue(report['comparison_usable'])
            self.assertTrue(report['duplicate_control']['passed'])
            self.assertFalse(report['calibration_read'])
            self.assertFalse(report['test_evaluated'])
            self.assertFalse(report['live_model_changed'])

    def test_numerical_gate_checks_both_score_difference_and_label_sets(self):
        base = np.array([[.50001, .2]])
        self.assertFalse(check_numerical_control(base, np.array([[.49999, .2]]))['passed'])
        self.assertFalse(check_numerical_control(base, np.array([[.51, .2]]))['passed'])
        self.assertTrue(check_numerical_control(base, np.array([[.50002, .2]]))['passed'])

    def test_failed_control_retains_whole_despite_candidate_nomination(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _, _, path = self.prepared(root)
            failed = {'max_absolute_score_difference': .2, 'rows_with_different_predicted_sets': 3, 'passed': False}
            with patch('support_ticket_ai.segment_pooling.check_numerical_control', return_value=failed), \
                    patch('support_ticket_ai.segment_pooling.choose_representation', return_value=2):
                report = run(root, root, path, encoder_factory=lambda _: encoders.FakeEncoder())
            self.assertEqual(report['protocol_nomination_index'], 2)
            self.assertEqual(report['selected_candidate_index'], 0)
            self.assertFalse(report['comparison_usable'])

    def test_changed_tolerance_or_gate_fails_before_loading_encoder(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest, protocol, path = self.prepared(root)
            for key, value in [('tolerance', 1e-6), ('max_iter', 1000), ('numerical_control', {})]:
                changed = copy.deepcopy(protocol)
                changed[key] = value
                path.write_text(json.dumps(changed))
                with patch('support_ticket_ai.segment_pooling.load_encoder') as load:
                    with self.assertRaises(ValueError):
                        run(root, root, path)
                    load.assert_not_called()
            validate_protocol(protocol, manifest)


if __name__ == '__main__':
    unittest.main()
