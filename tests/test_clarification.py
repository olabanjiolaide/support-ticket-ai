import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from support_ticket_ai.clarification import (CONTRAST_PATH, PROTOCOL_PATH, apply_clarification,
                                              inspect_context, main, run_experiment)


class ClarificationTests(unittest.TestCase):
    def test_author_written_contrasts_are_regression_checks(self):
        for case in json.loads(CONTRAST_PATH.read_text(encoding='utf-8')):
            with self.subTest(case=case['case_id']):
                self.assertEqual(inspect_context(case['text'])['clarification_proposed'],
                                 case['expected_clarification'])

    def test_invalid_inputs_fail_before_rules(self):
        for value in (None, 123, '', '  ', 'x' * 2001):
            with self.subTest(value=str(value)[:20]), self.assertRaises(ValueError):
                inspect_context(value)

    def test_never_reverse_an_existing_abstention_or_mutate_input(self):
        original = {'decision': 'abstain', 'suggested_category': None,
                    'requires_human_review': True, 'review_reason': 'scope gate'}
        saved = copy.deepcopy(original)
        for text in ('It does not work.', 'Send my invoice.'):
            result = apply_clarification(text, original)
            self.assertEqual(result['prediction'], saved)
            self.assertFalse(result['newly_withheld'])
            self.assertEqual(original, saved)

    def test_generic_failure_withholds_but_preserves_original_score(self):
        original = {'decision': 'suggestion', 'suggested_category': 'ACCOUNT',
                    'model_top_category': 'ACCOUNT', 'uncalibrated_probability': .52}
        result = apply_clarification('It does not work.', original)
        self.assertTrue(result['newly_withheld'])
        self.assertEqual(result['prediction']['decision'], 'abstain')
        self.assertIsNone(result['prediction']['suggested_category'])
        self.assertEqual(result['prediction']['uncalibrated_probability'], .52)
        self.assertTrue(result['prediction']['requires_human_review'])
        self.assertEqual(original['decision'], 'suggestion')

    def test_tampered_source_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'untrusted.json'
            path.write_text('{}')
            with self.assertRaisesRegex(ValueError, 'frozen development protocol'):
                run_experiment(path)

    def test_cli_preserves_existing_report_and_removes_failed_partial(self):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory) / 'report.json'
            out.write_text('existing')
            with patch('sys.argv', ['clarification', 'missing.json', str(out)]):
                self.assertEqual(main(), 1)
            self.assertEqual(out.read_text(), 'existing')
            out.unlink()
            with patch('sys.argv', ['clarification', 'missing.json', str(out)]):
                self.assertEqual(main(), 1)
            self.assertFalse(out.exists())


if __name__ == '__main__':
    unittest.main()
