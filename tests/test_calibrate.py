from pathlib import Path
import tempfile
import unittest

import numpy as np

from support_ticket_ai.calibrate import (
    fit_temperature, partition_validation, probability_metrics, rule_metrics,
    run_experiment, scale_probabilities, select_threshold,
)
from support_ticket_ai.data import Ticket
from support_ticket_ai.prepare import prepare
from support_ticket_ai.train import run_training


class CalibrationTests(unittest.TestCase):
    def test_temperature_identity_normalization_and_class_order(self):
        values = np.array([[0.6, 0.3, 0.1], [0.1, 0.2, 0.7]])
        np.testing.assert_allclose(scale_probabilities(values, 1), values)
        for temperature in (0.1, 0.5, 2, 10):
            scaled = scale_probabilities(values, temperature)
            np.testing.assert_allclose(scaled.sum(axis=1), 1)
            np.testing.assert_array_equal(scaled.argmax(axis=1), values.argmax(axis=1))

    def test_invalid_temperature_and_probability_inputs_rejected(self):
        for temperature in (0, -1, np.nan, np.inf):
            with self.subTest(temperature=temperature), self.assertRaises(ValueError):
                scale_probabilities([[0.5, 0.5]], temperature)
        for values in ([], [[1]], [[0.1, 0.1]], [[-0.1, 1.1]], [[np.nan, 0.5]]):
            with self.subTest(values=values), self.assertRaises(ValueError):
                scale_probabilities(values, 1)

    def test_fit_improves_likelihood_on_underconfident_fixture(self):
        probabilities = np.array([[0.6, 0.4], [0.4, 0.6]] * 10)
        targets = np.array([0, 1] * 10)
        temperature = fit_temperature(probabilities, targets)
        self.assertGreaterEqual(temperature, 0.05)
        self.assertLessEqual(temperature, 10)
        before = probability_metrics(probabilities, targets)
        after = probability_metrics(scale_probabilities(probabilities, temperature), targets)
        self.assertLess(after["negative_log_likelihood"], before["negative_log_likelihood"])

    def test_metrics_known_values_and_bin_accounting(self):
        report = probability_metrics([[0.8, 0.2], [0.4, 0.6]], np.array([0, 0]))
        self.assertEqual(report["accuracy"], 0.5)
        self.assertAlmostEqual(report["multiclass_brier_sum_over_classes"], 0.4)
        self.assertEqual(sum(row["count"] for row in report["reliability_bins"]), 2)
        self.assertTrue(np.isfinite(report["negative_log_likelihood"]))

    def test_threshold_selection_and_no_eligible_candidate(self):
        probabilities = np.array([[0.99, 0.01], [0.01, 0.99], [0.6, 0.4]])
        targets = np.array([0, 1, 1])
        selected = select_threshold(probabilities, targets, minimum_count=2, target_accuracy=1)
        self.assertEqual(selected["selected_threshold"], 0.7)
        none = select_threshold(probabilities, targets, minimum_count=4)
        self.assertIsNone(none["selected_threshold"])
        metrics = rule_metrics(probabilities, targets, None)
        self.assertEqual(metrics["coverage"], 0)
        self.assertIsNone(metrics["selected_accuracy"])

    def test_disjoint_order_independent_partitions(self):
        tickets = [Ticket(f"{label}-{i}", f"{label} request {i}", label)
                   for label in ("ACCOUNT", "PAYMENT") for i in range(10)]
        parts = partition_validation(tickets)
        self.assertEqual(parts, partition_validation(list(reversed(tickets))))
        seen = set()
        for rows in parts.values():
            ids = {row.ticket_id for row in rows}
            self.assertTrue(seen.isdisjoint(ids))
            seen.update(ids)
            self.assertEqual({row.category for row in rows}, {"ACCOUNT", "PAYMENT"})
        self.assertEqual(len(seen), len(tickets))

    def test_duplicate_validation_content_rejected(self):
        with self.assertRaisesRegex(ValueError, "Duplicate normalized"):
            partition_validation([Ticket("1", "same", "ACCOUNT"), Ticket("2", " SAME ", "PAYMENT")])

    def test_experiment_never_requires_test_file(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, license_file = root / "source.csv", root / "license.txt"
            source.write_text("instruction,category\n" + "".join(
                f"{word} request {i},{label}\n"
                for label, word in [("ACCOUNT", "password"), ("PAYMENT", "invoice")]
                for i in range(30)))
            license_file.write_text("Synthetic fixture")
            data, model, output = root / "data", root / "model", root / "calibration.json"
            prepare(source, data, "a" * 40, license_file)
            (data / "test.csv").unlink()
            run_training(data, model)
            report = run_experiment(data, model, output)
            self.assertFalse(report["test_evaluated"])
            self.assertFalse(report["api_behavior_changed"])
            self.assertTrue(report["all_live_predictions_require_review"])
            with self.assertRaisesRegex(ValueError, "already exists"):
                run_experiment(data, model, output)
