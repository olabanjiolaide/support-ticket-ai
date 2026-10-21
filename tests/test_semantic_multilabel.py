from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

import test_multilabel_baseline as fixtures
from support_ticket_ai.semantic_multilabel import run, source_fingerprints


class FakeEncoder:
    def __init__(self):
        self.batches = []

    def tokenizer(self, texts, **kwargs):
        return {'length': [300 if 'unique 0 ' in text else 8 for text in texts]}

    def encode(self, texts, **kwargs):
        self.batches.append(list(texts))
        values = np.zeros((len(texts), 384))
        for index, text in enumerate(texts):
            values[index, :3] = [float('account' in text), float('payment' in text), .1]
        return values / np.linalg.norm(values, axis=1, keepdims=True)


class SemanticMultilabelTests(unittest.TestCase):
    fixture = fixtures.MultilabelBaselineTests.fixture

    def test_semantic_uses_same_inputs_without_calibration_or_test(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.fixture(root)
            encoder = FakeEncoder()
            original = Path.open
            def guarded(path, *args, **kwargs):
                if path.parent == root:
                    self.assertIn(path.name, {'manifest.json', 'train.jsonl', 'selection.jsonl'})
                return original(path, *args, **kwargs)
            with patch.object(Path, 'open', guarded):
                report = run(root, root / 'absent-cache', encoder_factory=lambda _: encoder)
            self.assertEqual([len(batch) for batch in encoder.batches], [12, 4])
            self.assertTrue(all(text.startswith('train ') for text in encoder.batches[0]))
            self.assertTrue(all(text.startswith('selection ') for text in encoder.batches[1]))
            self.assertEqual(report['recipe']['threshold'], .5)
            self.assertFalse(report['recipe']['threshold_tuned'])
            self.assertFalse(report['calibration_read'])
            self.assertFalse(report['test_evaluated'])
            self.assertFalse(report['live_model_changed'])
            self.assertEqual(report['encoder']['implementation'], 'injected_test_double')
            self.assertIsNone(report['encoder']['source_file_sha256'])
            self.assertEqual(report['encoder']['truncation_audit']['train']['rows_over_256_tokens'], 1)
            self.assertEqual(report['encoder']['truncation_audit']['selection']['rows_over_256_tokens'], 1)
            for metric, delta in report['semantic_minus_word'].items():
                self.assertAlmostEqual(delta, report['semantic_selection'][metric] - report['word_baseline']['selection'][metric])

    def test_bad_input_fails_before_loading_encoder(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.fixture(root)
            (root / 'selection.jsonl').write_text('tampered')
            with patch('support_ticket_ai.semantic_multilabel.load_encoder') as factory:
                with self.assertRaisesRegex(ValueError, 'Checksum'):
                    run(root, root)
                factory.assert_not_called()

    def test_invalid_encoder_output_is_not_scored(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.fixture(root)
            encoder = FakeEncoder()
            encoder.encode = lambda texts, **kwargs: np.full((len(texts), 384), np.nan)
            with self.assertRaisesRegex(ValueError, 'invalid'):
                run(root, root, encoder_factory=lambda _: encoder)

    def test_missing_pinned_weights_fail_instead_of_claiming_fingerprint(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(FileNotFoundError):
                source_fingerprints(Path(directory))


if __name__ == '__main__':
    unittest.main()
