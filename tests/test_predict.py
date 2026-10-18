import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import joblib
import sklearn

from support_ticket_ai.predict import MAX_TEXT_LENGTH, TicketPredictor
from support_ticket_ai.train import build_model


class PredictionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        model = build_model()
        model.fit(["password reset", "password login", "invoice card", "invoice refund"],
                  ["ACCOUNT", "ACCOUNT", "PAYMENT", "PAYMENT"])
        joblib.dump(model, self.root / "model.joblib")
        self.metadata = {
            "versions": {"scikit-learn": sklearn.__version__},
            "model_sha256": hashlib.sha256((self.root / "model.joblib").read_bytes()).hexdigest(),
        }
        self.write_metadata()

    def write_metadata(self):
        (self.root / "validation_metrics.json").write_text(json.dumps(self.metadata))

    def test_prediction_is_serializable_and_always_reviewed(self):
        predictor = TicketPredictor(self.root)
        result = predictor.predict("password reset")
        self.assertEqual(result["suggested_category"], "ACCOUNT")
        self.assertTrue(result["requires_human_review"])
        self.assertGreaterEqual(result["uncalibrated_probability"], 0)
        self.assertLessEqual(result["uncalibrated_probability"], 1)
        self.assertNotIn("text", result)
        json.dumps(result)

    def test_blank_nonstring_and_oversized_input_rejected(self):
        predictor = TicketPredictor(self.root)
        for text in ("", "  ", None, 15, "x" * (MAX_TEXT_LENGTH + 1)):
            with self.subTest(text_type=type(text).__name__), self.assertRaises(ValueError):
                predictor.predict(text)

    def test_unrelated_request_still_requires_human_review(self):
        result = TicketPredictor(self.root).predict("Write a recipe for banana bread")
        self.assertTrue(result["requires_human_review"])

    def test_corrupt_model_rejected_before_deserialization(self):
        (self.root / "model.joblib").write_bytes(b"corrupt model")
        with patch("support_ticket_ai.predict.joblib.load") as loader:
            with self.assertRaisesRegex(ValueError, "checksum"):
                TicketPredictor(self.root)
            loader.assert_not_called()

    def test_version_mismatch_rejected_before_deserialization(self):
        self.metadata["versions"]["scikit-learn"] = "0.0.0"
        self.write_metadata()
        with patch("support_ticket_ai.predict.joblib.load") as loader:
            with self.assertRaisesRegex(ValueError, "version"):
                TicketPredictor(self.root)
            loader.assert_not_called()
