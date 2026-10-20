import json
from pathlib import Path
import tempfile
import unittest

from support_ticket_ai.abstain import CHALLENGE_PATH, install_policy, load_challenge, summarize


class AbstentionEvaluationTests(unittest.TestCase):
    def test_challenge_partitions_are_explicit_and_unique(self):
        categories = {"ACCOUNT", "CANCEL", "CONTACT", "DELIVERY", "FEEDBACK", "INVOICE", "ORDER",
                      "PAYMENT", "REFUND", "SHIPPING", "SUBSCRIPTION"}
        rows = load_challenge(CHALLENGE_PATH, categories)
        self.assertEqual(len(rows), 60)
        self.assertEqual(sum(row["split"] == "selection" for row in rows), 34)
        self.assertEqual(sum(row["split"] == "audit" for row in rows), 23)
        self.assertEqual(sum(row["split"] == "regression" for row in rows), 3)
        for split in ("selection", "audit"):
            self.assertEqual({row["expected_category"] for row in rows if row["split"] == split},
                             categories | {"UNSUPPORTED"})

    def test_metrics_count_withheld_correct_cases_and_unsupported_suggestions(self):
        rows = [{"expected_category": "ACCOUNT", "top_category": "ACCOUNT", "score": .8},
                {"expected_category": "PAYMENT", "top_category": "PAYMENT", "score": .3},
                {"expected_category": "UNSUPPORTED", "top_category": "ACCOUNT", "score": .4}]
        baseline, selective = summarize(rows, None), summarize(rows, .7)
        self.assertEqual(baseline["supported_coverage"], 1)
        self.assertEqual(baseline["unsupported_suggestions"], 1)
        self.assertEqual(selective["supported_coverage"], .5)
        self.assertEqual(selective["withheld_correct_supported_rows"], 1)
        self.assertEqual(selective["unsupported_rejection"], 1)

    def test_no_selected_supported_rows_has_undefined_accuracy(self):
        metrics = summarize([{"expected_category": "ACCOUNT", "top_category": "ACCOUNT", "score": .2}], .7)
        self.assertIsNone(metrics["selected_supported_accuracy"])
        self.assertIsNone(metrics["unsupported_rejection"])

    def test_failed_audit_and_wrong_model_do_not_install(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "validation_metrics.json").write_text(json.dumps({"model_sha256": "expected"}))
            with self.assertRaisesRegex(ValueError, "audit"):
                install_policy(root, {"eligible_for_experimental_installation": False})
            with self.assertRaisesRegex(ValueError, "match"):
                install_policy(root, {"eligible_for_experimental_installation": True, "model_sha256": "wrong"})
            self.assertFalse((root / "abstention_policy.json").exists())

    def test_install_is_bound_to_model_and_never_overwrites_existing_policy(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "validation_metrics.json").write_text(json.dumps({"model_sha256": "expected"}))
            report = {"eligible_for_experimental_installation": True, "model_sha256": "expected",
                      "selected_threshold": .7, "challenge_sha256": "fixture"}
            path = install_policy(root, report)
            before = path.read_bytes()
            self.assertEqual(json.loads(before)["threshold"], .7)
            with self.assertRaises(FileExistsError):
                install_policy(root, report)
            self.assertEqual(path.read_bytes(), before)

    def test_duplicate_challenge_text_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "challenge.csv"
            path.write_text("case_id,split,text,expected_category\none,selection,hello,ACCOUNT\ntwo,audit, HELLO ,ACCOUNT\n")
            with self.assertRaisesRegex(ValueError, "Duplicate"):
                load_challenge(path, {"ACCOUNT"})
