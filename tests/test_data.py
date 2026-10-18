from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from support_ticket_ai.data import load_tickets

ROOT = Path(__file__).resolve().parents[1]
HEADER = "ticket_id,text,category\n"


class DataTests(unittest.TestCase):
    def load(self, content):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "tickets.csv"
            path.write_text(content, encoding="utf-8")
            return load_tickets(path)

    def test_valid_bom_quoted_comma_and_whitespace(self):
        tickets = self.load('\ufeff' + HEADER + ' one ," Charged twice, please help ", billing \n')
        self.assertEqual(tickets[0].ticket_id, "one")
        self.assertEqual(tickets[0].text, "Charged twice, please help")
        self.assertEqual(tickets[0].category, "billing")

    def test_duplicate_ids_rejected_after_trimming(self):
        with self.assertRaisesRegex(ValueError, "duplicate ticket_id"):
            self.load(HEADER + "one,hello,billing\n one ,help,account\n")

    def test_invalid_records_rejected(self):
        cases = {
            "missing column": "ticket_id,text\none,hello\n",
            "duplicate column": "ticket_id,text,category,text\none,hi,billing,hi\n",
            "empty file": "",
            "header only": HEADER,
            "blank field": HEADER + "one,   ,billing\n",
            "unknown label": HEADER + "one,hello,payments\n",
            "missing field": HEADER + "one,hello\n",
            "extra field": HEADER + "one,hello,billing,extra\n",
            "unclosed quote": HEADER + 'one,"hello,billing\n',
        }
        for name, content in cases.items():
            with self.subTest(name=name), self.assertRaises(ValueError):
                self.load(content)

    def test_extra_named_column_allowed(self):
        tickets = self.load("ticket_id,text,category,source\none,hello,billing,demo\n")
        self.assertEqual(len(tickets), 1)

    def test_sample_has_four_tickets_per_category(self):
        tickets = load_tickets(ROOT / "data/sample_tickets.csv")
        for category in ("billing", "account", "technical"):
            self.assertEqual(sum(t.category == category for t in tickets), 4)

    def test_cli_success(self):
        result = subprocess.run(
            [sys.executable, "-m", "support_ticket_ai", "data/sample_tickets.csv"],
            cwd=ROOT, text=True, capture_output=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Validated 12 tickets", result.stdout)
        self.assertIn("billing: 4", result.stdout)

    def test_cli_missing_file_fails_cleanly(self):
        with tempfile.TemporaryDirectory() as directory:
            missing = str(Path(directory) / "missing.csv")
            result = subprocess.run(
                [sys.executable, "-m", "support_ticket_ai", missing],
                cwd=ROOT, text=True, capture_output=True,
            )
        self.assertEqual(result.returncode, 1)
        self.assertIn("Error:", result.stderr)
        self.assertNotIn("Traceback", result.stderr)


if __name__ == "__main__":
    unittest.main()
