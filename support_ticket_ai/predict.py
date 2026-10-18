"""Suggest a ticket category using a trusted, locally trained model bundle."""

import argparse
import hashlib
import json
from pathlib import Path
import sys

import joblib
import sklearn
from sklearn.pipeline import Pipeline

MAX_TEXT_LENGTH = 2000


class TicketPredictor:
    """Load once and reuse. Only load bundles you created or otherwise trust.

    A checksum detects inconsistent files; it does not authenticate their author.
    Joblib can execute code during loading, so never accept uploaded bundles.
    """

    def __init__(self, model_dir: Path):
        self.metadata = json.loads((model_dir / "validation_metrics.json").read_text(encoding="utf-8"))
        if self.metadata["versions"]["scikit-learn"] != sklearn.__version__:
            raise ValueError("Model requires the recorded scikit-learn version.")
        path = model_dir / "model.joblib"
        if hashlib.sha256(path.read_bytes()).hexdigest() != self.metadata["model_sha256"]:
            raise ValueError("Model checksum mismatch.")
        self.model = joblib.load(path)
        if not isinstance(self.model, Pipeline) or not hasattr(self.model, "predict_proba"):
            raise ValueError("Bundle does not contain a probability-capable pipeline.")

    def predict(self, text: str) -> dict:
        if not isinstance(text, str) or not text.strip():
            raise ValueError("Ticket text must be a nonempty string.")
        if len(text) > MAX_TEXT_LENGTH:
            raise ValueError(f"Ticket text cannot exceed {MAX_TEXT_LENGTH} characters.")
        probabilities = self.model.predict_proba([text.strip()])[0]
        index = int(probabilities.argmax())
        return {
            "suggested_category": str(self.model.classes_[index]),
            "uncalibrated_probability": float(probabilities[index]),
            "requires_human_review": True,
            "review_reason": "Calibration and unsupported-request detection are not established.",
            "model_sha256": self.metadata["model_sha256"],
        }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("model_dir", type=Path, help="Trusted model bundle directory")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--text")
    source.add_argument("--stdin", action="store_true", help="Read ticket text from standard input")
    args = parser.parse_args()
    try:
        text = sys.stdin.read(MAX_TEXT_LENGTH + 1) if args.stdin else args.text
        result = TicketPredictor(args.model_dir).predict(text)
    except (OSError, ValueError, KeyError, UnicodeError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
