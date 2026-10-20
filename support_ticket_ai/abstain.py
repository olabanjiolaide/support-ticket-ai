"""Evaluate an experimental score-based abstention rule on authored development cases."""

import argparse
from collections import Counter
import csv
import hashlib
import json
from pathlib import Path
import sys

import numpy as np

from .predict import MAX_TEXT_LENGTH, TicketPredictor
from .prepare import normalize

CHALLENGE_PATH = Path(__file__).resolve().parents[1] / "data/development_challenge.csv"
THRESHOLDS = (0.5, 0.6, 0.7, 0.8, 0.85, 0.9, 0.95, 0.98, 0.99)
CRITERIA = {"minimum_supported_coverage": 0.25, "minimum_selected_supported_accuracy": 0.90,
            "minimum_unsupported_rejection": 0.90}


def load_challenge(path: Path, categories: set[str]) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle, strict=True)
        headers = reader.fieldnames or []
        if len(headers) != 4 or set(headers) != {"case_id", "split", "text", "expected_category"}:
            raise ValueError("Challenge columns do not match the required schema.")
        rows = list(reader)
    ids, texts = set(), set()
    for row in rows:
        if None in row or any(value is None or not value.strip() for value in row.values()):
            raise ValueError("Challenge contains blank or malformed fields.")
        for key in row:
            row[key] = row[key].strip()
        if len(row["text"]) > MAX_TEXT_LENGTH:
            raise ValueError("Challenge text exceeds the API character limit.")
        if row["split"] not in {"selection", "audit", "regression"}:
            raise ValueError("Unknown challenge partition.")
        if row["expected_category"] not in categories | {"UNSUPPORTED"}:
            raise ValueError("Challenge category is absent from this model.")
        normalized = normalize(row["text"])
        if row["case_id"] in ids or normalized in texts:
            raise ValueError("Duplicate challenge ID or normalized text.")
        ids.add(row["case_id"])
        texts.add(normalized)
    for split in ("selection", "audit"):
        labels = {row["expected_category"] for row in rows if row["split"] == split}
        if "UNSUPPORTED" not in labels or not labels.intersection(categories):
            raise ValueError("Selection and audit each require supported and unsupported cases.")
    return rows


def summarize(rows: list[dict], threshold: float | None) -> dict:
    """None is the forced-suggestion baseline, not an abstain-all rule."""
    supported = [row for row in rows if row["expected_category"] != "UNSUPPORTED"]
    unsupported = [row for row in rows if row["expected_category"] == "UNSUPPORTED"]
    selected = [row for row in supported if threshold is None or row["score"] >= threshold]
    rejected_unsupported = [row for row in unsupported if threshold is not None and row["score"] < threshold]
    correct = sum(row["top_category"] == row["expected_category"] for row in selected)
    return {
        "threshold": threshold,
        "supported_rows": len(supported), "unsupported_rows": len(unsupported),
        "selected_supported_rows": len(selected),
        "supported_coverage": len(selected) / len(supported) if supported else None,
        "selected_supported_accuracy": correct / len(selected) if selected else None,
        "selected_supported_errors": len(selected) - correct,
        "withheld_supported_rows": len(supported) - len(selected),
        "withheld_correct_supported_rows": sum(row["top_category"] == row["expected_category"] and
                                                 threshold is not None and row["score"] < threshold for row in supported),
        "unsupported_rejected_rows": len(rejected_unsupported),
        "unsupported_rejection": len(rejected_unsupported) / len(unsupported) if unsupported else None,
        "unsupported_suggestions": len(unsupported) - len(rejected_unsupported),
    }


def meets_criteria(metrics: dict) -> bool:
    return (metrics["supported_coverage"] is not None and metrics["selected_supported_accuracy"] is not None and
            metrics["unsupported_rejection"] is not None and
            metrics["supported_coverage"] >= CRITERIA["minimum_supported_coverage"] and
            metrics["selected_supported_accuracy"] >= CRITERIA["minimum_selected_supported_accuracy"] and
            metrics["unsupported_rejection"] >= CRITERIA["minimum_unsupported_rejection"])


def evaluate_challenge(model_dir: Path, challenge_path: Path = CHALLENGE_PATH) -> dict:
    predictor = TicketPredictor(model_dir)
    rows = load_challenge(challenge_path, set(predictor.model.classes_))
    probabilities = predictor.model.predict_proba([row["text"] for row in rows])
    for row, scores in zip(rows, probabilities):
        index = int(np.argmax(scores))
        row["top_category"] = str(predictor.model.classes_[index])
        row["score"] = float(scores[index])
    parts = {name: [row for row in rows if row["split"] == name] for name in ("selection", "audit", "regression")}
    candidates = [summarize(parts["selection"], threshold) for threshold in THRESHOLDS]
    eligible = [candidate for candidate in candidates if meets_criteria(candidate)]
    selected = max(eligible, key=lambda candidate: (candidate["supported_coverage"], -candidate["threshold"])) if eligible else None
    threshold = selected["threshold"] if selected else None
    audit = summarize(parts["audit"], threshold) if threshold is not None else None
    return {
        "experiment": "authored_development_challenge_score_abstention",
        "test_evaluated": False, "model_retrained": False,
        "model_sha256": predictor.metadata["model_sha256"],
        "training_versions": predictor.metadata["versions"],
        "challenge_sha256": hashlib.sha256(challenge_path.read_bytes()).hexdigest(),
        "partition_counts": dict(Counter(row["split"] for row in rows)),
        "criteria_declared_before_evaluation": CRITERIA,
        "selection_candidates": candidates,
        "selected_threshold": threshold,
        "audit_forced_suggestion_baseline": summarize(parts["audit"], None),
        "audit_selected_policy": audit,
        "eligible_for_experimental_installation": audit is not None and meets_criteria(audit),
        "cases": [{**row, "candidate_decision": "abstain" if threshold is not None and row["score"] < threshold
                   else "suggestion" if threshold is not None else "no_policy_selected"} for row in rows],
        "limitations": ["Small author-written development set with nonindependent labels; not a representative benchmark.",
                        "Score-based abstention is not a trained unsupported-request detector.",
                        "Selection uses only selection rows; audit is checked without retuning; regression rows do not select thresholds.",
                        "Minimum empirical criteria are not statistical guarantees of reliability.",
                        "Every live request requires human review, including those passing the rule."],
    }


def install_policy(model_dir: Path, report: dict) -> Path:
    if not report["eligible_for_experimental_installation"]:
        raise ValueError("Development audit did not meet the declared criteria; no policy was installed.")
    metadata = json.loads((model_dir / "validation_metrics.json").read_text(encoding="utf-8"))
    if metadata["model_sha256"] != report["model_sha256"]:
        raise ValueError("Policy report does not match this model bundle.")
    policy = {"policy_version": 1, "kind": "experimental_max_probability",
              "model_sha256": report["model_sha256"], "threshold": report["selected_threshold"],
              "challenge_sha256": report["challenge_sha256"], "human_review_required": True}
    path = model_dir / "abstention_policy.json"
    with path.open("x", encoding="utf-8") as handle:
        json.dump(policy, handle, indent=2)
        handle.write("\n")
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("model_dir", type=Path)
    parser.add_argument("output", type=Path, help="New experiment JSON report")
    parser.add_argument("--install-policy", action="store_true", help="Install only if the separate audit meets criteria")
    args = parser.parse_args()
    try:
        if args.output.exists():
            raise ValueError("Report already exists; choose a new report filename.")
        if args.install_policy and (args.model_dir / "abstention_policy.json").exists():
            raise ValueError("A policy already exists; preserve it and use a separately versioned model directory.")
        report = evaluate_challenge(args.model_dir)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x", encoding="utf-8") as handle:
            json.dump(report, handle, indent=2)
            handle.write("\n")
        if args.install_policy:
            path = install_policy(args.model_dir, report)
            print(f"Installed experimental policy: {path}")
    except (OSError, ValueError, KeyError, UnicodeError, csv.Error) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    print(json.dumps({"selected_threshold": report["selected_threshold"],
                      "audit": report["audit_selected_policy"],
                      "eligible_for_experimental_installation": report["eligible_for_experimental_installation"],
                      "test_evaluated": False}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
