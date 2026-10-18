import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from support_ticket_ai.demo import build_demo, download_verified
from support_ticket_ai.serve import main as serve_main


class DemoTests(unittest.TestCase):
    def test_verified_download_and_bad_checksum(self):
        payload = b"source bytes"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch("support_ticket_ai.demo.urllib.request.urlopen", return_value=io.BytesIO(payload)):
                download_verified("https://example.invalid/source", root / "valid", hashlib.sha256(payload).hexdigest())
            self.assertEqual((root / "valid").read_bytes(), payload)
            with patch("support_ticket_ai.demo.urllib.request.urlopen", return_value=io.BytesIO(payload)):
                with self.assertRaisesRegex(ValueError, "checksum"):
                    download_verified("https://example.invalid/source", root / "invalid", "0" * 64)
            self.assertFalse((root / "invalid").exists())

    def test_existing_download_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "existing"
            path.write_text("keep")
            with patch("support_ticket_ai.demo.urllib.request.urlopen") as network:
                with self.assertRaisesRegex(ValueError, "exists"):
                    download_verified("https://example.invalid/source", path, "0" * 64)
                network.assert_not_called()
            self.assertEqual(path.read_text(), "keep")

    def test_oversized_download_not_published(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "source"
            with patch("support_ticket_ai.demo.MAX_DOWNLOAD_BYTES", 3):
                with patch("support_ticket_ai.demo.urllib.request.urlopen", return_value=io.BytesIO(b"too large")):
                    with self.assertRaisesRegex(ValueError, "size limit"):
                        download_verified("https://example.invalid/source", path, "0" * 64)
            self.assertFalse(path.exists())

    def test_pipeline_with_mocked_downloads_and_real_training(self):
        raw = ("instruction,category\n" + "".join(
            f"{word} request {number},{label}\n"
            for label, word in [("ACCOUNT", "password"), ("PAYMENT", "invoice")]
            for number in range(10))).encode()
        license_bytes = b"Synthetic fixture license"
        files = {"data.csv": ("bitext.csv", hashlib.sha256(raw).hexdigest()),
                 "LICENSE.txt": ("LICENSE.txt", hashlib.sha256(license_bytes).hexdigest())}

        def response(url, timeout):
            return io.BytesIO(raw if url.endswith("data.csv") else license_bytes)

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "demo"
            with patch("support_ticket_ai.demo.SOURCE_FILES", files):
                with patch("support_ticket_ai.demo.urllib.request.urlopen", side_effect=response):
                    summary = build_demo(output)
            self.assertEqual(summary["status"], "complete")
            self.assertFalse(summary["test_evaluated"])
            self.assertTrue(summary["smoke_prediction"]["requires_human_review"])
            self.assertEqual(json.loads((output / "demo_summary.json").read_text()), summary)
            self.assertTrue((output / "source/source_provenance.json").exists())
            with self.assertRaisesRegex(ValueError, "already exists"):
                build_demo(output)

    def test_serve_command_binds_to_loopback(self):
        with patch("sys.argv", ["serve", "--model-dir", "trusted-model", "--port", "8123"]):
            with patch("support_ticket_ai.serve.uvicorn.run") as run:
                serve_main()
        self.assertEqual(run.call_args.kwargs, {"host": "127.0.0.1", "port": 8123})
