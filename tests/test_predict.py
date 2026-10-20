import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import joblib
import sklearn
import numpy as np

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

    def write_policy(self, **overrides):
        policy = {"policy_version": 1, "kind": "experimental_max_probability",
                  "model_sha256": self.metadata["model_sha256"], "threshold": 0.7,
                  "human_review_required": True}
        policy.update(overrides)
        (self.root / "abstention_policy.json").write_text(json.dumps(policy))

    def test_prediction_is_serializable_and_always_reviewed(self):
        predictor = TicketPredictor(self.root)
        result = predictor.predict("password reset")
        self.assertEqual(result["suggested_category"], "ACCOUNT")
        self.assertEqual(result["decision"], "suggestion")
        self.assertIsNone(result["abstention_threshold"])
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

    def test_optional_policy_abstains_below_threshold_and_keeps_review(self):
        self.write_policy()
        predictor = TicketPredictor(self.root)
        with patch.object(predictor.model, "predict_proba", return_value=np.array([[0.31, 0.69]])):
            result = predictor.predict("payment question")
        self.assertEqual(result["decision"], "abstain")
        self.assertIsNone(result["suggested_category"])
        self.assertEqual(result["model_top_category"], "PAYMENT")
        self.assertTrue(result["requires_human_review"])

    def test_optional_policy_accepts_equal_threshold(self):
        self.write_policy()
        predictor = TicketPredictor(self.root)
        with patch.object(predictor.model, "predict_proba", return_value=np.array([[0.3, 0.7]])):
            result = predictor.predict("payment question")
        self.assertEqual(result["decision"], "suggestion")
        self.assertEqual(result["suggested_category"], "PAYMENT")
        self.assertTrue(result["requires_human_review"])

    def test_invalid_or_mismatched_policy_rejected_before_model_loading(self):
        for overrides in ({"threshold": True}, {"threshold": -1}, {"threshold": 1.1},
                          {"threshold": "0.7"}, {"threshold": float("nan")},
                          {"model_sha256": "wrong"}, {"human_review_required": False},
                          {"policy_version": 2}, {"kind": "other"}):
            self.write_policy(**overrides)
            with self.subTest(overrides=overrides), patch("support_ticket_ai.predict.joblib.load") as loader:
                with self.assertRaises(ValueError):
                    TicketPredictor(self.root)
                loader.assert_not_called()

    def test_version_mismatch_rejected_before_deserialization(self):
        self.metadata["versions"]["scikit-learn"] = "0.0.0"
        self.write_metadata()
        with patch("support_ticket_ai.predict.joblib.load") as loader:
            with self.assertRaisesRegex(ValueError, "version"):
                TicketPredictor(self.root)
            loader.assert_not_called()
