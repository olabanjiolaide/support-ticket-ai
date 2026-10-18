import csv
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest

import joblib

from support_ticket_ai.prepare import prepare
from support_ticket_ai.train import build_model, run_training


class TrainingTests(unittest.TestCase):
    def make_data(self, root):
        handle = io.StringIO(newline="")
        writer = csv.writer(handle)
        writer.writerow(["instruction", "category"])
        for category, word in [("ACCOUNT", "password"), ("PAYMENT", "invoice")]:
            for number in range(10):
                writer.writerow([f"{word} request number {number}", category])
        source = root / "source.csv"
        source.write_text(handle.getvalue(), encoding="utf-8")
        license_file = root / "license.txt"
        license_file.write_text("Synthetic test fixture", encoding="utf-8")
        data = root / "prepared"
        prepare(source, data, "a" * 40, license_file)
        return data

    def test_validation_terms_do_not_enter_training_vocabulary(self):
        model = build_model()
        model.fit(["password reset", "password login", "invoice card", "invoice refund"],
                  ["ACCOUNT", "ACCOUNT", "PAYMENT", "PAYMENT"])
        model.predict(["neverobservedvalidationword"])
        self.assertNotIn("neverobservedvalidationword", model.named_steps["tfidf"].vocabulary_)

    def test_training_without_test_file_and_model_roundtrip(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            data = self.make_data(root)
            (data / "test.csv").unlink()  # Training must not depend on test access.
            output = root / "run"
            report = run_training(data, output)
            self.assertFalse(report["test_evaluated"])
            self.assertEqual(report["evaluation_split"], "validation")
            self.assertEqual(len(report["tfidf_logistic_regression"]["confusion_matrix_labels"]), 2)
            model = joblib.load(output / "model.joblib")
            self.assertEqual(model.predict(["password reset"])[0], "ACCOUNT")
            with self.assertRaisesRegex(ValueError, "already exists"):
                run_training(data, output)

    def test_modified_split_fails_checksum(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            data = self.make_data(root)
            with (data / "train.csv").open("a") as handle:
                handle.write("unexpected,data,ACCOUNT\n")
            with self.assertRaisesRegex(ValueError, "Checksum mismatch"):
                run_training(data, root / "run")

    def test_overlap_rejected_even_with_updated_checksum(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            data = self.make_data(root)
            path = data / "validation.csv"
            path.write_bytes((data / "train.csv").read_bytes())
            manifest_path = data / "manifest.json"
            manifest = json.loads(manifest_path.read_text())
            manifest["split_sha256"]["validation"] = hashlib.sha256(path.read_bytes()).hexdigest()
            manifest_path.write_text(json.dumps(manifest))
            with self.assertRaisesRegex(ValueError, "overlap"):
                run_training(data, root / "run")


if __name__ == "__main__":
    unittest.main()
