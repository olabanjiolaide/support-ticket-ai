import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
from sklearn.multiclass import OneVsRestClassifier

import test_multilabel_baseline as fixtures
import test_semantic_multilabel as encoders
from support_ticket_ai.prepare import normalize
from support_ticket_ai.resources import data_path
from support_ticket_ai.segment_pooling import (choose_representation, make_representations, run,
                                              segment_spans, validate_protocol)


class SegmentPoolingTests(unittest.TestCase):
    def prepared(self, root):
        manifest = fixtures.MultilabelBaselineTests.fixture(self, root)
        manifest['label_vocabulary'] = ['account', 'delivery', 'payment']
        for name in ('train', 'selection'):
            path = root / f'{name}.jsonl'
            rows = [json.loads(line) for line in path.read_text().splitlines()]
            for i, row in enumerate(rows):
                if i % 3 == 0:
                    row['labels'] = ['account', 'delivery', 'payment']
                if i == 0:
                    row['text'] = f'{name} unique zero account and payment and delivery'
                    row['text_group_sha256'] = hashlib.sha256(normalize(row['text']).encode()).hexdigest()
            raw = ''.join(json.dumps(row) + '\n' for row in rows).encode()
            path.write_bytes(raw)
            manifest['files_sha256'][path.name] = hashlib.sha256(raw).hexdigest()
        (root / 'manifest.json').write_text(json.dumps(manifest))
        protocol = json.loads(data_path('segment_pooling_protocol.json').read_text())
        protocol['development_input_sha256'] = manifest['files_sha256']
        path = root / 'protocol.json'
        path.write_text(json.dumps(protocol))
        return manifest, protocol, path

    def test_spans_preserve_unicode_connectors_and_all_characters_with_cap(self):
        for text in ['💳 Change my email and refund my purchase. Please resend the invoice',
                     'If it arrived, do not cancel; also check my invoice',
                     'also, cancel transfer', 'hello',
                     ' and '.join(f'please handle request {i}' for i in range(12))]:
            spans, capped = segment_spans(text)
            self.assertEqual(spans[0][0], 0)
            self.assertEqual(spans[-1][1], len(text))
            self.assertEqual(''.join(text[a:b] for a, b in spans), text)
            self.assertTrue(all(a < b for a, b in spans))
            self.assertLessEqual(len(spans), 4)
            self.assertTrue(all(first[1] == second[0] for first, second in zip(spans, spans[1:])))
            if 'request 11' in text:
                self.assertTrue(capped)
                self.assertEqual(len(spans), 4)
        self.assertEqual(segment_spans('candy band butter')[0], [(0, 17)])
        with self.assertRaises(ValueError):
            segment_spans('  ')

    def test_feature_norm_duplication_gram_and_zero_mean_fallback(self):
        whole = np.array([[1., 0.], [0., 1.]])
        bags = [np.array([[1., 0.], [-1., 0.]]), np.array([[.6, .8], [-.8, .6]])]
        features = make_representations(whole, bags)
        for values in features.values():
            np.testing.assert_allclose(np.linalg.norm(values, axis=1), 1)
        duplicate = features['whole_duplicate']
        np.testing.assert_allclose(duplicate @ duplicate.T, whole @ whole.T)
        np.testing.assert_allclose(features['whole_segment_mean'][0], duplicate[0])
        self.assertFalse(np.allclose(features['whole_segment_mean'][1], features['whole_segment_max'][1]))

    def test_selection_requires_overall_gain_and_three_intent_nonregression(self):
        def candidate(exact, three, f1=.7, precision=.8):
            return {'selection': {'exact_set_accuracy': exact, 'micro_f1': f1, 'micro_precision': precision,
                                  'by_true_label_count': {'3': {'exact_set_accuracy': three}}}}
        control = candidate(.4, .1)
        self.assertEqual(choose_representation([control, candidate(.9, .9), candidate(.5, .09), candidate(.4, .2)]), 0)
        self.assertEqual(choose_representation([control, control, candidate(.5, .1), candidate(.5, .2)]), 2)
        self.assertEqual(choose_representation([control, control, candidate(.5, .1), candidate(.6, .1)]), 3)

    def test_train_only_fits_and_no_calibration_test_source_access(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _, _, protocol_path = self.prepared(root)
            encoder = encoders.FakeEncoder()
            original_fit, original_open = OneVsRestClassifier.fit, Path.open
            dimensions = []
            def fit(heads, x, y, **kwargs):
                self.assertEqual(len(x), 12)
                self.assertEqual(y.shape, (12, 3))
                self.assertEqual(heads.estimator.C, 10.)
                self.assertEqual(heads.estimator.tol, 1e-4)
                self.assertEqual(heads.estimator.max_iter, 1000)
                dimensions.append(x.shape[1])
                return original_fit(heads, x, y, **kwargs)
            def guarded(path, *args, **kwargs):
                if path.parent == root:
                    self.assertIn(path.name, {'manifest.json', 'train.jsonl', 'selection.jsonl', 'protocol.json'})
                return original_open(path, *args, **kwargs)
            with patch.object(OneVsRestClassifier, 'fit', fit), patch.object(Path, 'open', guarded):
                report = run(root, root, protocol_path, encoder_factory=lambda _: encoder)
            self.assertEqual(dimensions, [384, 768, 768, 768])
            self.assertEqual(len(encoder.batches), 4)  # Whole and unique local segments, per partition.
            self.assertFalse(report['calibration_read'])
            self.assertFalse(report['test_evaluated'])
            self.assertFalse(report['live_model_changed'])
            self.assertFalse(report['model_exported'])
            self.assertEqual(report['encoder']['implementation'], 'injected_test_double')

    def test_changed_recipe_or_input_fails_before_encoder_load(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest, protocol, path = self.prepared(root)
            for key, value in [('C', 1.), ('threshold', .2), ('pooling', 'different pooling'),
                               ('selection_rule', 'maximize recall')]:
                changed = copy.deepcopy(protocol)
                changed[key] = value
                with self.assertRaises(ValueError):
                    validate_protocol(changed, manifest)
            protocol['development_input_sha256']['train.jsonl'] = '0' * 64
            path.write_text(json.dumps(protocol))
            with patch('support_ticket_ai.segment_pooling.load_encoder') as load:
                with self.assertRaisesRegex(ValueError, 'fingerprints'):
                    run(root, root, path)
                load.assert_not_called()

    def test_missing_three_label_slice_fails_before_encoder_load(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = fixtures.MultilabelBaselineTests.fixture(self, root)
            protocol = json.loads(data_path('segment_pooling_protocol.json').read_text())
            protocol['development_input_sha256'] = manifest['files_sha256']
            path = root / 'protocol.json'
            path.write_text(json.dumps(protocol))
            with patch('support_ticket_ai.segment_pooling.load_encoder') as load:
                with self.assertRaisesRegex(ValueError, 'three-label'):
                    run(root, root, path)
                load.assert_not_called()


if __name__ == '__main__':
    unittest.main()
