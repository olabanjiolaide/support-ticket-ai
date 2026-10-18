"""Download pinned source data, prepare splits, and train a local demo bundle."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile
import urllib.error
import urllib.request

from .predict import TicketPredictor
from .prepare import prepare
from .train import run_training

REVISION = "72ea2203180d14a416b579c657033ecd21e59a11"
BASE_URL = f"https://raw.githubusercontent.com/bitext/customer-support-llm-chatbot-training-dataset/{REVISION}/"
SOURCE_FILES = {
    "data/Bitext_Sample_Customer_Support_Training_Dataset_27K_responses-v11.csv": (
        "bitext.csv", "6f81102b0100b97b8468eb04368033a23206bf1fde9d53500d5806ec1001a434"),
    "LICENSE.txt": ("LICENSE.txt", "f6054388eae4947a769ca2020c54e6d394eb01c41d58db55bb6cfd24ce71cdd8"),
}
MAX_DOWNLOAD_BYTES = 32 * 1024 * 1024


def download_verified(url: str, destination: Path, expected_sha256: str) -> None:
    """Verify bytes before publishing a file; never replace an existing file."""
    if destination.exists():
        raise ValueError("Download destination already exists.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=destination.parent) as staging:
        temporary = Path(staging) / "download"
        checksum, total = hashlib.sha256(), 0
        with urllib.request.urlopen(url, timeout=30) as response, temporary.open("wb") as output:
            while chunk := response.read(1024 * 1024):
                total += len(chunk)
                if total > MAX_DOWNLOAD_BYTES:
                    raise ValueError("Download exceeded the size limit.")
                checksum.update(chunk)
                output.write(chunk)
        if checksum.hexdigest() != expected_sha256:
            raise ValueError("Downloaded source checksum mismatch.")
        # Exclusive creation protects existing user files, including on races.
        with destination.open("xb") as output, temporary.open("rb") as source:
            shutil.copyfileobj(source, output)


def build_demo(output: Path) -> dict:
    """Build a new version directory; leave partial runs for inspection on error."""
    if output.exists():
        raise ValueError("Demo directory already exists; choose a fresh version directory.")
    output.mkdir(parents=True)
    source = output / "source"
    source.mkdir()
    for upstream_path, (local_name, checksum) in SOURCE_FILES.items():
        download_verified(BASE_URL + upstream_path, source / local_name, checksum)
    provenance = {
        "downloaded_at_utc": datetime.now(timezone.utc).isoformat(),
        "revision": REVISION,
        "files": [{"url": BASE_URL + path, "local_name": name, "sha256": checksum}
                  for path, (name, checksum) in SOURCE_FILES.items()],
    }
    (source / "source_provenance.json").write_text(json.dumps(provenance, indent=2) + "\n", encoding="utf-8")
    manifest = prepare(source / "bitext.csv", output / "prepared", REVISION, source / "LICENSE.txt")
    report = run_training(output / "prepared", output / "model")
    probe = TicketPredictor(output / "model").predict("I cannot reset my password.")
    summary = {
        "status": "complete",
        "source_revision": REVISION,
        "retained_rows": manifest["audit"]["retained_rows"],
        "validation_macro_f1": report["tfidf_logistic_regression"]["macro_f1"],
        "test_evaluated": False,
        "smoke_prediction": probe,
        "limitations": "Synthetic validation source; uncalibrated suggestions require human review.",
    }
    (output / "demo_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path, help="New directory, preferably under artifacts/")
    args = parser.parse_args()
    try:
        summary = build_demo(args.output)
    except (OSError, ValueError, KeyError, UnicodeError, urllib.error.URLError) as error:
        print(f"Error: {error}", file=sys.stderr)
        print("An incomplete output directory may remain. Inspect it and choose a fresh path to retry.", file=sys.stderr)
        return 1
    print(json.dumps(summary, indent=2))
    print(f"Next: python -m support_ticket_ai.serve --model-dir {args.output / 'model'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
