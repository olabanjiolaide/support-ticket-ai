import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from support_ticket_ai.multilabel_baseline import load_development, measure, run, threshold_predictions
from support_ticket_ai.prepare import normalize


class MultilabelBaselineTests(unittest.TestCase):
    def fixture(self, root):
        manifest = {'schema_version': 1, 'dataset': 'Synthetic fixture',
                    'taxonomy_id': 'blendbanking77-v1', 'source_revision': 'a' * 40,
                    'label_vocabulary': ['account', 'payment'], 'files_sha256': {}, 'partition_counts': {}}
        for name, count in (('train', 12), ('selection', 4)):
            rows = []
            for index in range(count):
                labels = ['account', 'payment'] if index % 3 == 0 else ['account'] if index % 3 == 1 else ['payment']
                text = f'{name} unique {index} ' + ' '.join(labels)
                rows.append({'case_id': f'{name}:{index}', 'text': text, 'labels': labels,
                             'text_group_sha256': hashlib.sha256(normalize(text).encode()).hexdigest()})
            raw = ''.join(json.dumps(row) + '\n' for row in rows).encode()
            (root / f'{name}.jsonl').write_bytes(raw)
            manifest['files_sha256'][f'{name}.jsonl'] = hashlib.sha256(raw).hexdigest()
            manifest['partition_counts'][name] = count
        (root / 'manifest.json').write_text(json.dumps(manifest))
        return manifest

    def test_independent_threshold_keeps_multiple_and_empty_sets(self):
        expected = np.array([[1, 1], [0, 0], [1, 0]])
        np.testing.assert_array_equal(threshold_predictions([[.8, .7], [.4, .1], [.5, .49]]), expected)
        metrics = measure(np.array([[1, 1], [1, 0], [1, 0]]), expected)
        self.assertAlmostEqual(metrics['exact_set_accuracy'], 2 / 3)
        self.assertAlmostEqual(metrics['empty_prediction_fraction'], 1 / 3)

    def test_experiment_never_opens_calibration_test_or_source(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.fixture(root)  # No calibration/test/source files exist.
            original = Path.open
            opened = []
            def guarded(path, *args, **kwargs):
                if path.parent == root:
                    self.assertIn(path.name, {'manifest.json', 'train.jsonl', 'selection.jsonl'})
                    opened.append(path.name)
                return original(path, *args, **kwargs)
            with patch.object(Path, 'open', guarded):
                report = run(root)
            self.assertEqual(set(opened), {'manifest.json', 'train.jsonl', 'selection.jsonl'})
            self.assertFalse(report['calibration_read'])
            self.assertFalse(report['test_evaluated'])
            self.assertFalse(report['live_model_changed'])
            self.assertEqual(report['label_count'], 2)
            self.assertEqual(report['selection']['rows'], 4)

    def test_checksum_and_taxonomy_fail_before_training(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = self.fixture(root)
            with (root / 'train.jsonl').open('ab') as handle:
                handle.write(b'corrupt')
            with patch('support_ticket_ai.multilabel_baseline.OneVsRestClassifier') as classifier:
                with self.assertRaisesRegex(ValueError, 'Checksum'):
                    run(root)
                classifier.assert_not_called()
            manifest['taxonomy_id'] = 'bitext-support-v1'
            (root / 'manifest.json').write_text(json.dumps(manifest))
            with self.assertRaisesRegex(ValueError, 'taxonomy'):
                load_development(root)

    def test_rehashed_train_selection_overlap_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = self.fixture(root)
            train = json.loads((root / 'train.jsonl').read_text().splitlines()[0])
            rows = [json.loads(line) for line in (root / 'selection.jsonl').read_text().splitlines()]
            rows[0]['text'] = train['text']
            rows[0]['text_group_sha256'] = train['text_group_sha256']
            raw = ''.join(json.dumps(row) + '\n' for row in rows).encode()
            (root / 'selection.jsonl').write_bytes(raw)
            manifest['files_sha256']['selection.jsonl'] = hashlib.sha256(raw).hexdigest()
            (root / 'manifest.json').write_text(json.dumps(manifest))
            with self.assertRaisesRegex(ValueError, 'overlapping'):
                load_development(root)


if __name__ == '__main__':
    unittest.main()
