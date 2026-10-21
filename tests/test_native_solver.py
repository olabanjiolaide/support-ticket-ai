import copy
import unittest

import numpy as np

from support_ticket_ai.native_solver import CachedEncoder, counts, eligibility


class NativeSolverTests(unittest.TestCase):
    def metrics(self):
        return {p: {'supported_accepted': 52, 'correct_accepted': 49,
                    'incorrect_accepted': 3, 'unsupported_suggestions': 0,
                    'review_suggestions': 3} for p in ('original', 'guarded')}

    def test_parity_and_unfaithful_control_do_not_qualify(self):
        baseline = self.metrics()
        self.assertFalse(eligibility(baseline, baseline, True))
        improved = copy.deepcopy(baseline)
        improved['guarded']['review_suggestions'] -= 1
        self.assertTrue(eligibility(baseline, improved, True))
        self.assertFalse(eligibility(baseline, improved, False))

    def test_each_regression_blocks_an_improvement_elsewhere(self):
        for policy in ('original', 'guarded'):
            for key, delta in [('supported_accepted', -1), ('correct_accepted', -1),
                               ('incorrect_accepted', 1), ('unsupported_suggestions', 1),
                               ('review_suggestions', 1)]:
                with self.subTest(policy=policy, key=key):
                    baseline = self.metrics()
                    improved = copy.deepcopy(baseline)
                    other = 'guarded' if policy == 'original' else 'original'
                    improved[other]['review_suggestions'] -= 1
                    improved[policy][key] += delta
                    self.assertFalse(eligibility(baseline, improved, True))

    def test_review_and_unsupported_are_separate_from_supported_accuracy(self):
        rows = [{'expected_category': label, 'original': {'decision': decision, 'model_top_category': top}}
                for label, decision, top in [('PAYMENT', 'suggestion', 'PAYMENT'),
                                             ('ORDER', 'suggestion', 'INVOICE'),
                                             ('ORDER', 'abstain', 'ORDER'),
                                             ('UNSUPPORTED', 'suggestion', 'ORDER'),
                                             ('REVIEW', 'suggestion', 'ORDER')]]
        self.assertEqual(counts(rows, 'original'),
                         {'supported': 3, 'supported_accepted': 2, 'correct_accepted': 1,
                          'incorrect_accepted': 1, 'forced_supported_correct': 2,
                          'unsupported_suggestions': 1, 'review_suggestions': 1})

    def test_shared_cache_encodes_each_distinct_text_only_once(self):
        class Encoder:
            tokenizer = None
            calls = []

            def encode(self, texts, **kwargs):
                self.calls.append(texts)
                return np.asarray([[len(text), 1] for text in texts])

        encoder = Encoder()
        cached = CachedEncoder(encoder)
        first = cached.encode(['first', 'first', 'next'])
        second = cached.encode(['next', 'new', 'first'])
        self.assertEqual(encoder.calls, [['first', 'next'], ['new']])
        np.testing.assert_array_equal(first[0], second[2])
        np.testing.assert_array_equal(first[2], second[0])


if __name__ == '__main__':
    unittest.main()
