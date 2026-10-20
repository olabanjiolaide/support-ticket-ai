import csv
import hashlib
from pathlib import Path
import tempfile
import unittest

import numpy as np

import test_compare_features as fixtures
from support_ticket_ai.scope_experiment import (NEGATIVES_PATH, reject_negative_overlap,
                                               run_experiment, score_policies)
from support_ticket_ai.robustness import PROBES_PATH, load_probes


class FixedProbabilities:
    def __init__(self, classes, scores):
        self.classes_ = classes
        self.scores = np.array(scores)

    def predict_proba(self, texts):
        if len(texts) != len(self.scores):
            raise AssertionError('Wrong fixture row count')
        return self.scores


class ScopeExperimentTests(unittest.TestCase):
    def test_policy_composition_preserves_boundaries_and_class_order(self):
        probes = [{'case_id': str(i), 'slice': 'fixture', 'text': str(i),
                   'expected_category': target, 'label_status': 'provisional'}
                  for i, target in enumerate(['ACCOUNT', 'UNSUPPORTED', 'PAYMENT', 'REVIEW'])]
        category = FixedProbabilities(['ACCOUNT', 'PAYMENT'], [[.7, .3], [.9, .1], [.4, .6], [.8, .2]])
        # Reversed binary order catches assuming SUPPORTED is always column 0.
        scope = FixedProbabilities(['UNSUPPORTED', 'SUPPORTED'], [[.5, .5], [.8, .2], [.2, .8], [.1, .9]])
        result = score_policies(category, scope, probes)
        cases = result['cases']
        self.assertTrue(cases[0]['combined'])  # both boundaries accept equality
        self.assertFalse(cases[1]['combined'])
        self.assertFalse(cases[2]['combined'])
        self.assertTrue(cases[2]['scope_gate_only'])
        self.assertEqual(result['policies']['combined']['unsupported_suggestions'], 0)
        self.assertEqual(result['policies']['combined']['supported_coverage'], .5)
        self.assertEqual(result['policies']['combined']['ambiguous_rows'], 1)
        self.assertTrue(all(not row['combined'] or row['category_cutoff_only'] for row in cases))

    def test_wrong_training_targets_and_normalized_probe_overlap_rejected(self):
        with self.assertRaisesRegex(ValueError, 'UNSUPPORTED'):
            reject_negative_overlap([{'expected_category': 'ACCOUNT', 'text': 'hello'}], [])
        with self.assertRaisesRegex(ValueError, 'overlap'):
            reject_negative_overlap([{'expected_category': 'UNSUPPORTED', 'text': 'HELLO  world'}],
                                    [{'text': 'hello world'}])

    def test_shipped_negative_training_texts_are_distinct_from_probes(self):
        categories = {'ACCOUNT', 'CANCEL', 'CONTACT', 'DELIVERY', 'FEEDBACK', 'INVOICE',
                      'ORDER', 'PAYMENT', 'REFUND', 'SHIPPING', 'SUBSCRIPTION'}
        negatives = load_probes(NEGATIVES_PATH, categories)
        self.assertEqual(len(negatives), 48)
        self.assertTrue(all(row['label_status'] == 'provisional' for row in negatives))
        reject_negative_overlap(negatives, load_probes(PROBES_PATH, categories))

    def test_end_to_end_without_validation_or_test_and_no_bundle_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            prepared, model, probes = fixtures.FeatureComparisonTests().fixture(root)
            (prepared / 'validation.csv').unlink()  # test.csv already removed by fixture
            negatives = root / 'negatives.csv'
            with negatives.open('w', newline='') as handle:
                writer = csv.writer(handle)
                writer.writerow(['case_id', 'slice', 'text', 'expected_category', 'label_status'])
                writer.writerows([['n1', 'general', 'explain gravity', 'UNSUPPORTED', 'provisional'],
                                  ['n2', 'general', 'solve a geometry puzzle', 'UNSUPPORTED', 'provisional']])
            before = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in model.iterdir()}
            result = run_experiment(model, prepared, probes, negatives)
            self.assertFalse(result['test_evaluated'])
            self.assertFalse(result['source_validation_evaluated'])
            self.assertFalse(result['live_model_changed'])
            self.assertEqual(result['training_counts']['UNSUPPORTED'], 2)
            self.assertEqual(set(result['policies']), {'category_cutoff_only', 'scope_gate_only', 'combined'})
            self.assertEqual(before, {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in model.iterdir()})
