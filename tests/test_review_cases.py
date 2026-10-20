import csv
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from support_ticket_ai.review_cases import (CASES_PATH, load_cases, main, new_review,
                                           review_session, validate_label, validate_progress)


class ReviewCasesTests(unittest.TestCase):
    def fixture(self, root):
        cases_path = root / 'cases.csv'
        cases_path.write_text('case_id,family_id,text\na,f1,Customer request one\nb,f2,Customer request two\nc,f3,Unclear request\n')
        cases = load_cases(cases_path)
        progress = new_review(cases_path, 'reviewer')
        output = root / 'review.json'
        output.write_text(json.dumps(progress))
        return cases_path, cases, progress, output

    def test_unlabeled_shipped_pilot_is_unique_and_family_grouped(self):
        cases = load_cases(CASES_PATH)
        self.assertEqual(len(cases), 40)
        self.assertEqual(len({row['family_id'] for row in cases}), 20)
        self.assertEqual(set(cases[0]), {'case_id', 'family_id', 'text'})

    def test_label_cardinality_and_vocabulary_are_enforced(self):
        validate_label('single_intent', ['INVOICE'])
        validate_label('multiple_intents', ['ORDER', 'INVOICE'])
        validate_label('insufficient_context', [])
        validate_label('unsupported', [])
        for kind, labels in [('single_intent', []), ('single_intent', ['ORDER', 'INVOICE']),
                             ('multiple_intents', ['ORDER']), ('multiple_intents', ['ORDER', 'ORDER']),
                             ('unsupported', ['ACCOUNT']), ('insufficient_context', ['ACCOUNT']),
                             ('single_intent', ['MISSING'])]:
            with self.assertRaises(ValueError):
                validate_label(kind, labels)

    def test_answers_save_after_each_case_limit_and_resume_skips_completed(self):
        with tempfile.TemporaryDirectory() as directory:
            source, cases, progress, output = self.fixture(Path(directory))
            answers = iter(['1', 'INVOICE', 'document request'])
            count = review_session(cases, progress, output, 1, input_fn=lambda prompt: next(answers), print_fn=lambda message: None)
            self.assertEqual(count, 1)
            saved = json.loads(output.read_text())
            validate_progress(saved, source, 'reviewer', cases)
            self.assertEqual(saved['records'][0]['case_id'], 'a')
            answers = iter(['2', 'invoice, order', '', '3', 'context missing'])
            review_session(cases, saved, output, 2, input_fn=lambda prompt: next(answers), print_fn=lambda message: None)
            final = json.loads(output.read_text())
            self.assertEqual([r['case_id'] for r in final['records']], ['a', 'b', 'c'])
            self.assertEqual(final['records'][1]['categories'], ['INVOICE', 'ORDER'])
            self.assertEqual(final['records'][2]['kind'], 'insufficient_context')

    def test_quit_skip_and_interruption_do_not_create_labels(self):
        with tempfile.TemporaryDirectory() as directory:
            source, cases, progress, output = self.fixture(Path(directory))
            before = output.read_bytes()
            answers = iter(['s', 'q'])
            review_session(cases, progress, output, 5, input_fn=lambda prompt: next(answers), print_fn=lambda message: None)
            self.assertEqual(output.read_bytes(), before)
            def interrupted(prompt):
                raise KeyboardInterrupt
            review_session(cases, progress, output, 5, input_fn=interrupted, print_fn=lambda message: None)
            self.assertEqual(progress['records'], [])

    def test_changed_collection_and_reviewer_block_resume(self):
        with tempfile.TemporaryDirectory() as directory:
            source, cases, progress, output = self.fixture(Path(directory))
            with self.assertRaisesRegex(ValueError, 'match'):
                validate_progress(progress, source, 'different-reviewer', cases)
            source.write_text(source.read_text() + 'd,f4,New case\n')
            with self.assertRaisesRegex(ValueError, 'match'):
                validate_progress(progress, source, 'reviewer', cases)

    def test_existing_session_is_not_overwritten_without_resume(self):
        with tempfile.TemporaryDirectory() as directory:
            source, cases, progress, output = self.fixture(Path(directory))
            before = output.read_bytes()
            with patch('sys.argv', ['review_cases', str(output), '--cases', str(source), '--reviewer', 'reviewer']):
                self.assertEqual(main(), 1)
            self.assertEqual(output.read_bytes(), before)

    def test_failed_atomic_replace_preserves_previous_file_and_no_label_in_memory(self):
        with tempfile.TemporaryDirectory() as directory:
            source, cases, progress, output = self.fixture(Path(directory))
            before = output.read_bytes()
            answers = iter(['4', 'unrelated'])
            with patch('support_ticket_ai.review_cases.os.replace', side_effect=OSError('fixture disk error')):
                with self.assertRaises(OSError):
                    review_session(cases, progress, output, 1, input_fn=lambda prompt: next(answers), print_fn=lambda message: None)
            self.assertEqual(output.read_bytes(), before)
            self.assertEqual(progress['records'], [])
            self.assertEqual(list(Path(directory).glob('review-*.tmp')), [])
