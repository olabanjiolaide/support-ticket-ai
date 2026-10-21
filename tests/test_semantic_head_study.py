import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from sklearn.multiclass import OneVsRestClassifier

import test_multilabel_baseline as fixtures
import test_semantic_multilabel as encoders
from support_ticket_ai.resources import data_path
from support_ticket_ai.semantic_head_study import CANDIDATES, run, select_candidate, validate_protocol


class SemanticHeadStudyTests(unittest.TestCase):
    fixture = fixtures.MultilabelBaselineTests.fixture

    def prepared(self, root):
        manifest = self.fixture(root)
        protocol = json.loads(data_path('semantic_head_protocol.json').read_text())
        protocol['development_input_sha256'] = manifest['files_sha256']
        path = root / 'protocol.json'
        path.write_text(json.dumps(protocol))
        return manifest, protocol, path

    def test_all_six_fit_train_only_and_share_one_encoding(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _, _, protocol_path = self.prepared(root)
            encoder = encoders.FakeEncoder()
            original_fit, original_open = OneVsRestClassifier.fit, Path.open
            fits = []
            def fit(heads, x, y, **kwargs):
                self.assertEqual(len(x), 12)
                self.assertEqual(y.shape, (12, 2))
                fits.append({'C': heads.estimator.C, 'class_weight': heads.estimator.class_weight})
                return original_fit(heads, x, y, **kwargs)
            def guarded(path, *args, **kwargs):
                if path.parent == root:
                    self.assertIn(path.name, {'manifest.json', 'train.jsonl', 'selection.jsonl', 'protocol.json'})
                return original_open(path, *args, **kwargs)
            with patch.object(OneVsRestClassifier, 'fit', fit), patch.object(Path, 'open', guarded):
                report = run(root, root, protocol_path, encoder_factory=lambda _: encoder)
            self.assertEqual(fits, CANDIDATES)
            self.assertEqual([len(batch) for batch in encoder.batches], [12, 4])
            self.assertEqual(len(report['candidates']), 6)
            self.assertEqual(report['control_candidate_index'], 2)
            self.assertFalse(report['calibration_read'])
            self.assertFalse(report['test_evaluated'])
            self.assertFalse(report['threshold_tuned'])
            self.assertFalse(report['live_model_changed'])
            self.assertTrue(all(c['threshold'] == .5 for c in report['candidates']))

    def test_protocol_cannot_change_grid_threshold_or_selection_rule(self):
        with tempfile.TemporaryDirectory() as directory:
            manifest, protocol, _ = self.prepared(Path(directory))
            validate_protocol(protocol, manifest)
            for key, value in [('threshold', .2), ('random_state', True),
                               ('selection_rule', 'maximize recall'), ('candidates', CANDIDATES[:2])]:
                altered = copy.deepcopy(protocol)
                altered[key] = value
                with self.assertRaises(ValueError):
                    validate_protocol(altered, manifest)
            altered = copy.deepcopy(protocol)
            altered['candidates'][2]['C'] = True
            with self.assertRaises(ValueError):
                validate_protocol(altered, manifest)

    def test_wrong_protocol_fingerprints_fail_before_loading_encoder(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _, protocol, path = self.prepared(root)
            protocol['development_input_sha256']['train.jsonl'] = '0' * 64
            path.write_text(json.dumps(protocol))
            with patch('support_ticket_ai.semantic_head_study.load_encoder') as load:
                with self.assertRaisesRegex(ValueError, 'fingerprints'):
                    run(root, root, path)
                load.assert_not_called()

    def test_selection_priority_and_stable_tie_break(self):
        def candidate(exact, f1, precision):
            return {'selection': {'exact_set_accuracy': exact, 'micro_f1': f1, 'micro_precision': precision}}
        choices = [candidate(.2, .9, .9), candidate(.3, .5, .6), candidate(.3, .6, .5),
                   candidate(.3, .6, .7), candidate(.3, .6, .7)]
        self.assertEqual(select_candidate(choices), 3)
        with self.assertRaises(ValueError):
            select_candidate([])


if __name__ == '__main__':
    unittest.main()
