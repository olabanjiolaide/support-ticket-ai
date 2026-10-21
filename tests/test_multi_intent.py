import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import test_compare_features as fixtures
from support_ticket_ai.multi_intent import guarded_prediction, inspect_requests
from support_ticket_ai.multi_intent_experiment import main, run_experiment
from support_ticket_ai.robustness import fingerprint


def prediction(category='INVOICE', *, accepted=True, truncated=False):
    return {'decision': 'suggestion' if accepted else 'abstain',
            'suggested_category': category if accepted else None, 'model_top_category': category,
            'uncalibrated_probability': .9, 'scope_score': .8, 'input_truncated': truncated,
            'requires_human_review': True, 'review_reason': 'original', 'model_sha256': 'test'}


class MultiIntentTests(unittest.TestCase):
    def test_different_accepted_requests_trigger_and_preserve_fragment_evidence(self):
        predict = Mock(side_effect=[prediction('INVOICE'), prediction('ORDER')])
        result = inspect_requests('I want my invoice, and I also want to cancel my order.', predict)
        self.assertTrue(result['review_triggered'])
        self.assertEqual([call.args[0] for call in predict.call_args_list],
                         ['I want my invoice', 'I also want to cancel my order'])
        self.assertEqual(result['routing_categories_considered'], ['INVOICE', 'ORDER'])

    def test_context_plus_one_request_does_not_call_clause_model(self):
        for text in ('My purchase arrived broken and I want a refund.',
                     'Your colleague was helpful and I want that praise recorded.',
                     'I need to change my account name and email.',
                     'I want the invoice and tax breakdown.',
                     'I cannot log in and my checkout payment was rejected.'):
            predict = Mock()
            self.assertFalse(inspect_requests(text, predict)['review_triggered'])
            predict.assert_not_called()

    def test_same_category_actions_are_not_different_routing_intents(self):
        predict = Mock(side_effect=[prediction('ACCOUNT'), prediction('ACCOUNT')])
        result = inspect_requests('Change my account email and reset my password.', predict)
        self.assertFalse(result['review_triggered'])
        self.assertEqual(len(result['fragments']), 2)

    def test_human_agent_preference_does_not_create_extra_routing_category(self):
        predict = Mock(side_effect=[prediction('REFUND'), prediction('CONTACT')])
        result = inspect_requests('I need my refund and please find a human support agent.', predict)
        self.assertFalse(result['review_triggered'])
        self.assertEqual(result['accepted_categories'], ['CONTACT', 'REFUND'])
        self.assertEqual(result['routing_categories_considered'], ['REFUND'])

    def test_negated_and_conditional_requests_do_not_trigger(self):
        for text in ("Please send my invoice and don't cancel my order.",
                     'I do not want a refund and please update my address.',
                     'Please send my invoice or cancel my order.',
                     'Please send my invoice and cancel my order if it has not shipped.',
                     'Please send my invoice rather than cancel my order.'):
            predict = Mock()
            self.assertFalse(inspect_requests(text, predict)['review_triggered'])
            predict.assert_not_called()

    def test_abstained_or_truncated_fragment_cannot_supply_second_category(self):
        for second in (prediction('ORDER', accepted=False), prediction('ORDER', truncated=True)):
            result = inspect_requests('Send my invoice and cancel my order.',
                                      Mock(side_effect=[prediction('INVOICE'), second]))
            self.assertFalse(result['review_triggered'])

    def test_bound_and_input_validation(self):
        predict = Mock()
        result = inspect_requests(' and '.join(['Send my invoice'] * 5), predict)
        self.assertEqual(result['status'], 'too_many_segments_skipped')
        predict.assert_not_called()
        for text in ('', ' ', None, 'a' * 2001):
            with self.assertRaises(ValueError):
                inspect_requests(text, predict)

    def test_wrapper_preserves_existing_abstention_and_only_changes_routing_fields(self):
        original = prediction('INVOICE')
        predictor = Mock()
        predictor.predict.side_effect = [original, prediction('INVOICE'), prediction('ORDER')]
        result = guarded_prediction('Send my invoice and cancel my order.', predictor)
        self.assertEqual(result['guarded']['decision'], 'abstain')
        self.assertIsNone(result['guarded']['suggested_category'])
        self.assertEqual(result['guarded']['model_top_category'], original['model_top_category'])
        self.assertEqual(result['guarded']['uncalibrated_probability'], original['uncalibrated_probability'])
        self.assertEqual(original['decision'], 'suggestion')
        predictor = Mock()
        predictor.predict.return_value = prediction(accepted=False)
        result = guarded_prediction('Send my invoice and cancel my order.', predictor)
        self.assertEqual(result['guarded'], result['original'])
        self.assertEqual(predictor.predict.call_count, 1)

    def fixture(self, root):
        prepared, _, probes = fixtures.FeatureComparisonTests().fixture(root)
        (prepared / 'validation.csv').unlink()
        model = root / 'semantic'
        model.mkdir()
        (model / 'semantic_model.json').write_text(json.dumps({
            'training_sha256': fingerprint(prepared / 'train.csv'),
            'categories': ['ACCOUNT', 'PAYMENT'], 'model_sha256': 'test',
            'category_threshold': .5, 'scope_threshold': .5, 'versions': {},
        }))
        return prepared, model, probes

    def test_experiment_without_validation_test_or_review_files_and_no_model_mutation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            prepared, model, probes = self.fixture(root)
            before = {p.name: p.read_bytes() for p in model.iterdir()}
            predictor = Mock()
            predictor.predict.return_value = prediction('ACCOUNT')
            report = run_experiment(model, prepared, probes_path=probes, predictor_factory=lambda p: predictor)
            self.assertTrue(report['test_double_used'])
            for field in ('test_evaluated', 'validation_evaluated', 'model_retrained',
                          'live_model_changed', 'policy_installed', 'threshold_selection_performed'):
                self.assertFalse(report[field])
            self.assertEqual(before, {p.name: p.read_bytes() for p in model.iterdir()})
            self.assertEqual(report['models']['guarded']['development']['ambiguous_rows'], 1)
            self.assertEqual(report['newly_withheld_case_ids'], [])

    def test_training_mismatch_rejected_before_encoder_load(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            prepared, model, probes = self.fixture(root)
            (prepared / 'train.csv').write_text('changed')
            with patch('support_ticket_ai.multi_intent_experiment.SemanticPredictor') as load:
                with self.assertRaisesRegex(ValueError, 'does not match'):
                    run_experiment(model, prepared, probes_path=probes)
                load.assert_not_called()

    def test_report_not_overwritten_and_failed_run_cleans_up(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'report.json'
            path.write_text('original')
            with patch('sys.argv', ['multi', 'absent', 'absent', str(path)]), \
                    patch('support_ticket_ai.multi_intent_experiment.run_experiment') as run:
                self.assertEqual(main(), 1)
                run.assert_not_called()
            self.assertEqual(path.read_text(), 'original')
            path.unlink()
            with patch('sys.argv', ['multi', 'absent', 'absent', str(path)]), \
                    patch('support_ticket_ai.multi_intent_experiment.run_experiment', side_effect=ValueError('failed')):
                self.assertEqual(main(), 1)
            self.assertFalse(path.exists())
