from pathlib import Path
import tempfile
import unittest

import numpy as np
from scipy.sparse import csr_matrix

from support_ticket_ai.audit_overlap import audit, summarize_similarity
from support_ticket_ai.prepare import prepare
from support_ticket_ai.train import run_training


class OverlapTests(unittest.TestCase):
    def test_identical_and_orthogonal_vectors(self):
        summary = summarize_similarity(csr_matrix([[1., 0., 0.]]),
                                       csr_matrix([[1., 0., 0.], [0., 1., 0.]]))
        self.assertEqual(summary["thresholds"]["0.99"]["count"], 1)
        self.assertEqual(summary["nearest_training_cosine_mean"], 0.5)

    def test_batching_does_not_change_result(self):
        vectors = csr_matrix(np.eye(3))
        self.assertEqual(summarize_similarity(vectors, vectors, 1),
                         summarize_similarity(vectors, vectors, 3))

    def test_empty_vectors_or_invalid_batch_rejected(self):
        with self.assertRaises(ValueError):
            summarize_similarity(csr_matrix((0, 3)), csr_matrix(np.eye(3)))
        with self.assertRaises(ValueError):
            summarize_similarity(csr_matrix(np.eye(3)), csr_matrix(np.eye(3)), 0)

    def test_audit_does_not_access_test_data(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.csv"
            source.write_text("instruction,category\n" + "".join(
                f"{word} request {i},{label}\n"
                for label, word in [("ACCOUNT", "password"), ("PAYMENT", "invoice")]
                for i in range(10)))
            license_file = root / "license.txt"
            license_file.write_text("Synthetic fixture")
            data, model = root / "data", root / "model"
            prepare(source, data, "a" * 40, license_file)
            (data / "test.csv").unlink()
            run_training(data, model)
            summary = audit(data, model)
            self.assertFalse(summary["test_evaluated"])
            self.assertEqual(summary["normalized_exact_overlap"], 0)
            self.assertGreater(summary["validation_rows"], 0)
