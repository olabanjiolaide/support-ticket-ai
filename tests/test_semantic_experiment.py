import csv
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

import test_compare_features as fixtures
from support_ticket_ai.semantic_experiment import (apply_scope, encode, run_experiment,
                                                   select_threshold, summarize_policy)


class FakeEncoder:
    def encode(self, texts, **kwargs):
        # Deterministic unit vectors; no network or optional packages needed.
        vectors = np.zeros((len(texts), 384), dtype=float)
        for index, text in enumerate(texts):
            vectors[index, 0 if 'password' in text or 'passwrod' in text else 1] = 1
        return vectors


class SemanticExperimentTests(unittest.TestCase):
    def test_bad_embedding_dimensions_finiteness_and_norm_rejected(self):
        for value in (np.zeros((1, 12)), np.full((1, 384), np.nan), np.zeros((1, 384))):
            encoder = type('BadEncoder', (), {'encode': lambda self, texts, **kwargs: value})()
            with self.assertRaises(ValueError):
                encode(encoder, ['one text'])

    def test_scope_rejection_and_equality_preserve_original_scores(self):
        rows = [{'score': .8, 'scope_score': .49}, {'score': .7, 'scope_score': .5}]
        transformed = apply_scope(rows)
        self.assertEqual([r['score'] for r in transformed], [0, .7])
        self.assertEqual(rows[0]['score'], .8)

    def test_failed_selection_does_not_fall_back_to_forced_predictions(self):
        rows = [{'expected_category': 'ACCOUNT', 'top_category': 'ACCOUNT', 'score': .9},
                {'expected_category': 'UNSUPPORTED', 'top_category': 'ACCOUNT', 'score': .99}]
        self.assertIsNone(select_threshold(rows)['selected_threshold'])
        self.assertIsNone(summarize_policy(rows, None)['metrics'])
        self.assertFalse(summarize_policy(rows, None)['policy_selected'])

    def test_threshold_uses_eligible_maximum_coverage_with_lowest_threshold_tie(self):
        rows = [{'expected_category': 'ACCOUNT', 'top_category': 'ACCOUNT', 'score': .8},
                {'expected_category': 'UNSUPPORTED', 'top_category': 'ACCOUNT', 'score': .2}]
        self.assertEqual(select_threshold(rows)['selected_threshold'], .5)

    def test_full_flow_with_fake_encoder_no_test_file_or_model_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            prepared, model, probes = fixtures.FeatureComparisonTests().fixture(root)
            negatives = root / 'negatives.csv'
            negatives.write_text('case_id,slice,text,expected_category,label_status\nn1,general,explain gravity,UNSUPPORTED,provisional\n')
            challenge = root / 'challenge.csv'
            challenge.write_text('case_id,split,text,expected_category\ns1,selection,password account help,ACCOUNT\ns2,selection,write a story,UNSUPPORTED\na1,audit,payment help please,PAYMENT\na2,audit,explain rain,UNSUPPORTED\n')
            with (prepared / 'train.csv').open() as handle:
                duplicate = next(csv.DictReader(handle))
            with challenge.open('a', newline='') as handle:
                csv.writer(handle).writerow(['s3', 'selection', duplicate['text'], duplicate['category']])
            before = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in model.iterdir()}
            seen = []
            class RecordingEncoder(FakeEncoder):
                def encode(self, texts, **kwargs):
                    seen.extend(texts)
                    return super().encode(texts, **kwargs)
            with patch('support_ticket_ai.semantic_experiment.select_threshold', wraps=select_threshold) as choose:
                report = run_experiment(model, prepared, root / 'cache', probes, challenge, negatives,
                                        encoder_factory=lambda path: RecordingEncoder())
                self.assertEqual(choose.call_count, 3)
                for call in choose.call_args_list:
                    self.assertTrue(all(row['split'] == 'selection' for row in call.args[0]))
            self.assertEqual(report['excluded_challenge_case_ids'], ['s3'])
            self.assertEqual(report['retained_challenge_partition_counts']['selection'], 2)
            self.assertFalse(report['test_evaluated'])
            self.assertFalse(report['encoder_fine_tuned'])
            self.assertTrue(report['encoder']['test_double_used'])
            self.assertEqual(report['training_counts']['unsupported'], 1)
            self.assertEqual(set(report['models']), {'word', 'semantic'})
            self.assertEqual(report['models']['semantic']['forced_supported_probe_metrics']['ambiguous_rows'], 1)
            self.assertEqual(before, {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in model.iterdir()})
            self.assertIn('explain gravity', seen)

    def test_validation_checksum_fails_before_loading_encoder(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            prepared, model, probes = fixtures.FeatureComparisonTests().fixture(root)
            negatives = root / 'negatives.csv'
            negatives.write_text('case_id,slice,text,expected_category,label_status\nn1,general,explain gravity,UNSUPPORTED,provisional\n')
            challenge = root / 'challenge.csv'
            challenge.write_text('case_id,split,text,expected_category\ns1,selection,password account help,ACCOUNT\ns2,selection,write a story,UNSUPPORTED\na1,audit,payment help please,PAYMENT\na2,audit,explain rain,UNSUPPORTED\n')
            (prepared / 'validation.csv').write_text('tampered')
            with patch('support_ticket_ai.semantic_experiment.load_encoder') as load:
                with self.assertRaisesRegex(ValueError, 'Checksum'):
                    run_experiment(model, prepared, root / 'cache', probes, challenge, negatives)
                load.assert_not_called()
