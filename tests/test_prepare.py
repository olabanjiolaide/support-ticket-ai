import csv
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest

from support_ticket_ai.data import load_tickets
from support_ticket_ai.prepare import build_splits, normalize, prepare


def source_bytes(rows):
    handle = io.StringIO(newline="")
    writer = csv.writer(handle)
    writer.writerow(["instruction", "category", "response"])
    writer.writerows((text, label, "Excluded answer") for text, label in rows)
    return handle.getvalue().encode("utf-8")


def examples():
    return [(f"Request {label} {number}", label)
            for label in ("ACCOUNT", "PAYMENT") for number in range(20)]


class PrepareTests(unittest.TestCase):
    def test_case_unicode_and_whitespace_normalization(self):
        self.assertEqual(normalize("  ＢＩＬＬ\t Help "), "bill help")

    def test_deduplication_conflicts_and_split_isolation(self):
        rows = examples() + [(" request account 0 ", "ACCOUNT"),
                             ("Conflicting request", "ACCOUNT"),
                             ("CONFLICTING REQUEST", "PAYMENT")]
        splits, audit = build_splits(source_bytes(rows))
        self.assertEqual(audit["duplicate_rows_removed"], 1)
        self.assertEqual(audit["conflicting_rows_quarantined"], 2)
        self.assertEqual(audit["retained_rows"], 40)
        seen = set()
        for records in splits.values():
            keys = {normalize(r["text"]) for r in records}
            self.assertTrue(seen.isdisjoint(keys))
            seen.update(keys)
            self.assertEqual({r["category"] for r in records}, {"ACCOUNT", "PAYMENT"})
            self.assertTrue(all(set(r) == {"ticket_id", "text", "category"} for r in records))
        self.assertEqual(len(splits["train"]), 28)
        self.assertEqual(len(splits["validation"]), 6)
        self.assertEqual(len(splits["test"]), 6)

    def test_source_order_does_not_change_splits(self):
        rows = examples()
        self.assertEqual(build_splits(source_bytes(rows))[0],
                         build_splits(source_bytes(list(reversed(rows))))[0])

    def test_seed_changes_assignments(self):
        raw = source_bytes(examples())
        self.assertNotEqual(build_splits(raw, 1)[0], build_splits(raw, 2)[0])

    def test_rare_or_fully_conflicting_class_is_rejected(self):
        cases = [examples() + [("only example", "RARE")],
                 examples() + [("conflict", "RARE"), ("conflict", "ACCOUNT")]]
        for rows in cases:
            with self.subTest(rows=rows[-2:]), self.assertRaisesRegex(ValueError, "at least three"):
                build_splits(source_bytes(rows))

    def test_malformed_or_empty_input_rejected(self):
        cases = [b"", b"text,label\nx,y\n", b"instruction,category\n ,ACCOUNT\n",
                 b"instruction,category\nx,ACCOUNT,extra\n",
                 b"instruction,category\nx\n"]
        for raw in cases:
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                build_splits(raw)

    def test_manifest_checksums_license_and_loader_integration(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.csv"
            source.write_bytes(source_bytes(examples()))
            license_file = root / "license.txt"
            license_file.write_text("Test fixture license only", encoding="utf-8")
            output = root / "v1"
            manifest = prepare(source, output, "a" * 40, license_file)
            self.assertEqual(json.loads((output / "manifest.json").read_text()), manifest)
            self.assertEqual((output / "DATA_LICENSE.txt").read_bytes(), license_file.read_bytes())
            for name in ("train", "validation", "test"):
                path = output / f"{name}.csv"
                self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),
                                 manifest["split_sha256"][name])
                tickets = load_tickets(path, categories=frozenset(manifest["audit"]["categories"]))
                self.assertTrue(tickets)
            with self.assertRaisesRegex(ValueError, "already exists"):
                prepare(source, output, "a" * 40, license_file)

    def test_revision_and_license_required_before_output(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, license_file, output = root / "source.csv", root / "license.txt", root / "v1"
            source.write_bytes(source_bytes(examples()))
            license_file.write_text("")
            with self.assertRaisesRegex(ValueError, "revision"):
                prepare(source, output, "main", license_file)
            with self.assertRaisesRegex(ValueError, "nonempty"):
                prepare(source, output, "a" * 40, license_file)
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
