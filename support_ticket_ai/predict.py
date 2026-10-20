"""Suggest a ticket category using a trusted, locally trained model bundle."""

import argparse
import hashlib
import json
import math
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
        self.abstention_threshold = None
        policy_path = model_dir / "abstention_policy.json"
        if policy_path.exists():
            policy = json.loads(policy_path.read_text(encoding="utf-8"))
            if not isinstance(policy, dict):
                raise ValueError("Invalid abstention policy.")
            threshold = policy.get("threshold")
            if (type(policy.get("policy_version")) is not int or policy["policy_version"] != 1 or
                    policy.get("kind") != "experimental_max_probability" or
                    policy.get("model_sha256") != self.metadata["model_sha256"] or
                    policy.get("human_review_required") is not True or
                    type(threshold) not in (int, float) or not math.isfinite(threshold) or not 0 < threshold <= 1):
                raise ValueError("Invalid abstention policy or model fingerprint mismatch.")
            self.abstention_threshold = float(threshold)
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
        category = str(self.model.classes_[index])
        score = float(probabilities[index])
        abstain = self.abstention_threshold is not None and score < self.abstention_threshold
        reason = ("The experimental score rule withheld the suggestion. Choose a category manually."
                  if abstain else "The experimental score rule passed. Confirm the category manually."
                  if self.abstention_threshold is not None else
                  "Calibration and unsupported-request detection are not established.")
        return {
            "suggested_category": None if abstain else category,
            "model_top_category": category,
            "decision": "abstain" if abstain else "suggestion",
            "abstention_threshold": self.abstention_threshold,
            "uncalibrated_probability": score,
            "requires_human_review": True,
            "review_reason": reason,
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
