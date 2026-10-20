import copy
import csv
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import test_compare_features as fixtures
import test_semantic_experiment as semantic_fixtures
from support_ticket_ai.evaluate_review import (FROZEN_REPORT_PATH, evaluate_review, frozen_thresholds,
                                              load_reconciled, write_probes)
from support_ticket_ai.review_cases import new_review
from support_ticket_ai.semantic_experiment import run_experiment


class ReviewedPilotEvaluationTests(unittest.TestCase):
    def fixture(self, root):
        cases = root / 'cases.csv'
        cases.write_text('case_id,family_id,text\ns,f1,password help please\nm,f2,password help and card payment help\nc,f3,it happened again\no,f4,write an adventure\n')
        labels = new_review(cases, 'fixture-reviewer')
        labels['status'] = 'human_assistant_reconciled_development_only'
        labels['reconciliation'] = {'independently_adjudicated': False, 'guided_unsupported_case_ids': ['o']}
        for case_id, family, kind, categories in [('s', 'f1', 'single_intent', ['ACCOUNT']),
                                                 ('m', 'f2', 'multiple_intents', ['ACCOUNT', 'PAYMENT']),
                                                 ('c', 'f3', 'insufficient_context', []),
                                                 ('o', 'f4', 'unsupported', [])]:
            labels['records'].append({'case_id': case_id, 'family_id': family, 'kind': kind,
                                      'categories': categories, 'note': '', 'reviewed_at_utc': 'fixture'})
        path = root / 'review.json'
        path.write_text(json.dumps(labels))
        return cases, path, labels

    def test_conversion_preserves_single_labels_and_separates_nonrouting_cases(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cases, review_path, labels = self.fixture(root)
            review, loaded = load_reconciled(review_path, cases)
            output = root / 'probes.csv'
            write_probes(output, review, loaded)
            with output.open() as handle:
                rows = {r['case_id']: r for r in csv.DictReader(handle)}
            self.assertEqual(rows['s']['expected_category'], 'ACCOUNT')
            self.assertEqual(rows['m']['expected_category'], 'REVIEW')
            self.assertEqual(rows['c']['expected_category'], 'REVIEW')
            self.assertEqual(rows['o']['expected_category'], 'UNSUPPORTED')
            self.assertEqual(rows['m']['slice'], 'multiple_intents')
            self.assertEqual(rows['c']['slice'], 'insufficient_context')

    def test_incomplete_review_and_unreconciled_status_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            cases, path, labels = self.fixture(Path(directory))
            incomplete = copy.deepcopy(labels)
            incomplete['records'].pop()
            path.write_text(json.dumps(incomplete))
            with self.assertRaisesRegex(ValueError, 'All pilot'):
                load_reconciled(path, cases)
            labels['status'] = 'human_annotation_pilot_not_adjudicated'
            path.write_text(json.dumps(labels))
            with self.assertRaisesRegex(ValueError, 'reconciled'):
                load_reconciled(path, cases)

    def test_changed_encoder_recipe_is_rejected(self):
        prior = json.loads(FROZEN_REPORT_PATH.read_text())
        prior['encoder']['revision'] = 'different'
        with self.assertRaisesRegex(ValueError, 'recipe'):
            frozen_thresholds(prior)

    def test_invalid_frozen_threshold_fails_before_model_loading(self):
        thresholds = {'word': {'category_only': True}, 'semantic': {'category_only': .9, 'with_scope': .5}}
        with patch('support_ticket_ai.semantic_experiment.TicketPredictor') as load:
            with self.assertRaisesRegex(ValueError, 'threshold'):
                run_experiment(Path('absent'), Path('absent'), Path('absent'), frozen_thresholds=thresholds)
            load.assert_not_called()

    def test_end_to_end_never_reselects_cutoff_or_changes_input_review(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            prepared, model, _ = fixtures.FeatureComparisonTests().fixture(root)
            cases, review, labels = self.fixture(root)
            prior = json.loads(FROZEN_REPORT_PATH.read_text())
            prior['preparation_manifest_sha256'] = hashlib.sha256((prepared / 'manifest.json').read_bytes()).hexdigest()
            prior_path = root / 'frozen.json'
            prior_path.write_text(json.dumps(prior))
            before = review.read_bytes()
            challenge = root / 'challenge.csv'
            challenge.write_text('case_id,split,text,expected_category\ns1,selection,password account help,ACCOUNT\ns2,selection,write a story,UNSUPPORTED\na1,audit,payment help please,PAYMENT\na2,audit,explain rain,UNSUPPORTED\n')
            def runner(*args, **kwargs):
                return run_experiment(*args, **kwargs, challenge_path=challenge, encoder_factory=lambda _: semantic_fixtures.FakeEncoder())
            with patch('support_ticket_ai.evaluate_review.run_experiment', side_effect=runner), \
                    patch('support_ticket_ai.semantic_experiment.select_threshold', side_effect=AssertionError('Cutoff tuning forbidden')):
                result = evaluate_review(model, prepared, review, root / 'cache', cases, prior_path)
            self.assertFalse(result['threshold_selection_performed'])
            self.assertFalse(result['pilot_used_for_fitting'])
            self.assertEqual(result['intent_type_counts']['multiple_intents'], 1)
            self.assertEqual(result['guided_unsupported_rows'], 1)
            self.assertEqual(result['frozen_thresholds'], frozen_thresholds(prior))
            for model_result in result['models'].values():
                for policy in model_result['policies'].values():
                    self.assertEqual(policy['metrics']['supported_rows'], 1)
                    self.assertEqual(policy['metrics']['ambiguous_rows'], 2)
                    self.assertEqual(policy['by_intent_type']['insufficient_context']['rows'], 1)
            self.assertEqual(review.read_bytes(), before)
