import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from support_ticket_ai.problem_statements import (CONTRAST_PATH, apply_problem_check,
                                                 inspect_problems, main, run_experiment)


class ProblemStatementTests(unittest.TestCase):
    def test_authored_positive_and_negative_contrasts(self):
        for case in json.loads(CONTRAST_PATH.read_text(encoding='utf-8')):
            with self.subTest(case=case['case_id']):
                outcome = inspect_problems(case['text'])
                self.assertEqual(outcome['multiple_problem_hypothesis'], case['expected_multiple_problem'])

    def test_evidence_offsets_recover_original_text(self):
        for case in json.loads(CONTRAST_PATH.read_text(encoding='utf-8')):
            text = '  ' + case['text'] + '  '
            outcome = inspect_problems(text)
            for span in outcome['evidence']:
                self.assertEqual(text[span['start']:span['end']], span['text'])
                self.assertLess(span['start'], span['end'])
            if outcome['multiple_problem_hypothesis']:
                self.assertEqual({e['category_hint'] for e in outcome['evidence']}, {'ACCOUNT', 'PAYMENT'})

    def test_invalid_text_and_decisions_are_rejected(self):
        for value in (None, 1, '', '  ', 'x' * 2001):
            with self.subTest(value=str(value)[:20]), self.assertRaises(ValueError):
                inspect_problems(value)
        with self.assertRaises(ValueError):
            apply_problem_check('My payment failed.', {'decision': 'unknown'})

    def test_only_suggestion_is_withheld_and_original_is_not_mutated(self):
        original = {'decision': 'suggestion', 'suggested_category': 'PAYMENT',
                    'model_top_category': 'PAYMENT', 'uncalibrated_probability': .766,
                    'model_sha256': 'reference', 'review_reason': 'original reason'}
        saved = copy.deepcopy(original)
        outcome = apply_problem_check('I cannot log in and my payment failed.', original)
        self.assertTrue(outcome['newly_withheld'])
        self.assertIsNone(outcome['prediction']['suggested_category'])
        self.assertTrue(outcome['prediction']['requires_human_review'])
        for key in ('model_top_category', 'uncalibrated_probability', 'model_sha256'):
            self.assertEqual(outcome['prediction'][key], original[key])
        self.assertEqual(original, saved)
        self.assertEqual(apply_problem_check('My payment failed.', original)['prediction'], saved)

    def test_prior_abstentions_remain_intact(self):
        original = {'decision': 'abstain', 'suggested_category': None,
                    'requires_human_review': True, 'review_reason': 'scope withheld'}
        for text in ('I cannot log in and my payment failed.', 'My payment failed.'):
            outcome = apply_problem_check(text, original)
            self.assertEqual(outcome['prediction'], original)
            self.assertFalse(outcome['newly_withheld'])

    def test_modified_source_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'source.json'
            path.write_text('{}')
            with self.assertRaisesRegex(ValueError, 'frozen development protocol'):
                run_experiment(path)

    def test_cli_preserves_existing_report_and_cleans_failed_output(self):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory) / 'report.json'
            out.write_text('existing')
            with patch('sys.argv', ['problem_statements', 'missing.json', str(out)]):
                self.assertEqual(main(), 1)
            self.assertEqual(out.read_text(), 'existing')
            out.unlink()
            with patch('sys.argv', ['problem_statements', 'missing.json', str(out)]):
                self.assertEqual(main(), 1)
            self.assertFalse(out.exists())


if __name__ == '__main__':
    unittest.main()
