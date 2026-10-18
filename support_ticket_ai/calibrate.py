"""Offline calibration and review-threshold simulation on development data."""

import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import platform
import sys

import numpy as np
import scipy
import sklearn
from scipy.optimize import minimize_scalar
from scipy.special import logsumexp, softmax

from .data import load_tickets
from .predict import TicketPredictor
from .prepare import normalize

THRESHOLDS = (0.5, 0.6, 0.7, 0.8, 0.9, 0.95, 0.98, 0.99)


def validate_probabilities(probabilities) -> np.ndarray:
    values = np.asarray(probabilities, dtype=float)
    if (values.ndim != 2 or not values.shape[0] or values.shape[1] < 2 or
            not np.isfinite(values).all() or (values < 0).any() or (values > 1).any() or
            not np.allclose(values.sum(axis=1), 1)):
        raise ValueError("Expected a nonempty matrix of finite class probabilities.")
    return values


def check_targets(targets, probabilities) -> np.ndarray:
    targets = np.asarray(targets)
    if (targets.shape != (len(probabilities),) or not np.issubdtype(targets.dtype, np.integer) or
            (targets < 0).any() or (targets >= probabilities.shape[1]).any()):
        raise ValueError("Expected one valid integer class index per row.")
    return targets


def scale_probabilities(probabilities, temperature: float) -> np.ndarray:
    values = validate_probabilities(probabilities)
    if not np.isfinite(temperature) or temperature <= 0:
        raise ValueError("Temperature must be positive and finite.")
    return softmax(np.log(np.clip(values, 1e-15, 1)) / temperature, axis=1)


def fit_temperature(probabilities, targets) -> float:
    values = validate_probabilities(probabilities)
    targets = check_targets(targets, values)
    logits = np.log(np.clip(values, 1e-15, 1))

    def objective(log_temperature):
        scaled = logits / np.exp(log_temperature)
        return float(np.mean(logsumexp(scaled, axis=1) - scaled[np.arange(len(targets)), targets]))

    result = minimize_scalar(objective, bounds=(np.log(0.05), np.log(10)), method="bounded")
    if not result.success:
        raise ValueError("Temperature optimization failed.")
    return float(np.exp(result.x))


def probability_metrics(probabilities, targets, bins: int = 15) -> dict:
    values = validate_probabilities(probabilities)
    targets = check_targets(targets, values)
    if bins < 1:
        raise ValueError("Bin count must be positive.")
    confidence = values.max(axis=1)
    correct = values.argmax(axis=1) == targets
    memberships = np.minimum((confidence * bins).astype(int), bins - 1)
    reliability, ece = [], 0.0
    for index in range(bins):
        mask = memberships == index
        count = int(mask.sum())
        mean_confidence = float(confidence[mask].mean()) if count else None
        accuracy = float(correct[mask].mean()) if count else None
        if count:
            ece += count / len(values) * abs(mean_confidence - accuracy)
        reliability.append({"lower": index / bins, "upper": (index + 1) / bins,
                            "count": count, "mean_confidence": mean_confidence, "accuracy": accuracy})
    one_hot = np.eye(values.shape[1])[targets]
    return {
        "rows": len(values),
        "accuracy": float(correct.mean()),
        "negative_log_likelihood": float(-np.log(np.clip(values[np.arange(len(targets)), targets], 1e-15, 1)).mean()),
        "multiclass_brier_sum_over_classes": float(((values - one_hot) ** 2).sum(axis=1).mean()),
        "top_label_ece_15_bins" if bins == 15 else "top_label_ece": float(ece),
        "reliability_bins": reliability,
    }


def rule_metrics(probabilities, targets, threshold: float | None) -> dict:
    values = validate_probabilities(probabilities)
    targets = check_targets(targets, values)
    if threshold is not None and (not np.isfinite(threshold) or not 0 <= threshold <= 1):
        raise ValueError("Threshold must be in [0, 1].")
    selected = np.zeros(len(values), dtype=bool) if threshold is None else values.max(axis=1) >= threshold
    correct = values.argmax(axis=1) == targets
    count = int(selected.sum())
    return {"threshold": threshold, "selected_rows": count,
            "coverage": float(selected.mean()), "review_fraction": float(1 - selected.mean()),
            "selected_accuracy": float(correct[selected].mean()) if count else None,
            "selected_errors": int((~correct & selected).sum())}


def select_threshold(probabilities, targets, minimum_count: int = 50, target_accuracy: float = 0.99) -> dict:
    if minimum_count < 1 or not 0 < target_accuracy <= 1:
        raise ValueError("Invalid threshold-selection criteria.")
    candidates = [rule_metrics(probabilities, targets, threshold) for threshold in THRESHOLDS]
    eligible = [row for row in candidates if row["selected_rows"] >= minimum_count and
                row["selected_accuracy"] >= target_accuracy]
    selected = max(eligible, key=lambda row: (row["coverage"], -row["threshold"])) if eligible else None
    return {"minimum_count": minimum_count, "target_empirical_accuracy": target_accuracy,
            "selected_threshold": selected["threshold"] if selected else None, "candidates": candidates}


def partition_validation(tickets, seed: int = 73) -> dict:
    by_category = defaultdict(list)
    if len({ticket.ticket_id for ticket in tickets}) != len(tickets):
        raise ValueError("Duplicate validation IDs.")
    if len({normalize(ticket.text) for ticket in tickets}) != len(tickets):
        raise ValueError("Duplicate normalized validation texts.")
    for ticket in tickets:
        by_category[ticket.category].append(ticket)
    parts = {"calibration_fit": [], "threshold_selection": [], "development_audit": []}
    if len(by_category) < 2:
        raise ValueError("At least two validation categories are required.")
    for category in sorted(by_category):
        rows = sorted(by_category[category], key=lambda row: hashlib.sha256(f"{seed}:{row.ticket_id}".encode()).hexdigest())
        if len(rows) < 3:
            raise ValueError("Each validation category needs at least three unique rows.")
        fit_count = max(1, min(len(rows) - 2, round(len(rows) * 0.4)))
        select_count = max(1, min(len(rows) - fit_count - 1, round(len(rows) * 0.3)))
        parts["calibration_fit"].extend(rows[:fit_count])
        parts["threshold_selection"].extend(rows[fit_count:fit_count + select_count])
        parts["development_audit"].extend(rows[fit_count + select_count:])
    return parts


def run_experiment(data_dir: Path, model_dir: Path, output: Path) -> dict:
    if output.exists():
        raise ValueError("Output already exists; choose a new experiment report.")
    manifest_bytes = (data_dir / "manifest.json").read_bytes()
    manifest = json.loads(manifest_bytes)
    predictor = TicketPredictor(model_dir)
    manifest_sha = hashlib.sha256(manifest_bytes).hexdigest()
    if manifest_sha != predictor.metadata["preparation_manifest_sha256"]:
        raise ValueError("Preparation manifest does not match the model.")
    path = data_dir / "validation.csv"
    if hashlib.sha256(path.read_bytes()).hexdigest() != manifest["split_sha256"]["validation"]:
        raise ValueError("Validation checksum mismatch.")
    tickets = load_tickets(path, categories=frozenset(manifest["audit"]["categories"]))
    parts = partition_validation(tickets)
    class_indices = {label: index for index, label in enumerate(predictor.model.classes_)}
    predictions, targets = {}, {}
    for name, rows in parts.items():
        predictions[name] = predictor.model.predict_proba([row.text for row in rows])
        targets[name] = np.asarray([class_indices[row.category] for row in rows])
    temperature = fit_temperature(predictions["calibration_fit"], targets["calibration_fit"])
    scaled = {name: scale_probabilities(values, temperature) for name, values in predictions.items()}
    selection = select_threshold(scaled["threshold_selection"], targets["threshold_selection"])
    probe_text = "I was charged twice for my subscription."
    probe_raw = predictor.model.predict_proba([probe_text])
    probe_scaled = scale_probabilities(probe_raw, temperature)
    threshold = selection["selected_threshold"]
    report = {
        "experiment": "offline_temperature_scaling_and_review_simulation",
        "test_evaluated": False,
        "api_behavior_changed": False,
        "all_live_predictions_require_review": True,
        "source_revision": manifest["source_revision"],
        "preparation_manifest_sha256": manifest_sha,
        "model_sha256": predictor.metadata["model_sha256"],
        "partition_seed": 73,
        "versions": {"python": platform.python_version(), "numpy": np.__version__,
                     "scipy": scipy.__version__, "scikit-learn": sklearn.__version__},
        "partition_policy": "Per-class SHA-256 ordering; approximately 40/30/30 of validation",
        "parts": {name: {"rows": len(rows), "sorted_ids_sha256": hashlib.sha256(
            "\n".join(sorted(row.ticket_id for row in rows)).encode()).hexdigest()}
            for name, rows in parts.items()},
        "temperature": temperature,
        "temperature_bounds": [0.05, 10],
        "temperature_fit_objective": "Multiclass negative log likelihood on calibration_fit only",
        "selection": selection,
        "manual_counterexample": {
            "text": probe_text,
            "author_assigned_expected_category": "PAYMENT",
            "suggested_category": str(predictor.model.classes_[probe_raw.argmax()]),
            "uncalibrated_score": float(probe_raw.max()),
            "temperature_scaled_score": float(probe_scaled.max()),
            "passes_simulated_threshold": bool(threshold is not None and probe_scaled.max() >= threshold),
            "status": "Illustrative author-written probe, not an independent benchmark sample.",
        },
        "development_audit": {
            "uncalibrated": probability_metrics(predictions["development_audit"], targets["development_audit"]),
            "temperature_scaled": probability_metrics(scaled["development_audit"], targets["development_audit"]),
            "frozen_threshold_simulation": rule_metrics(scaled["development_audit"], targets["development_audit"],
                                                        selection["selected_threshold"]),
        },
        "limitations": ["Exploratory development analysis on previously inspected validation data; not a new held-out test.",
                        "Synthetic source and possible template overlap limit generalization claims.",
                        "Empirical selection accuracy is not a statistical guarantee or a deployment authorization.",
                        "Temperature scaling preserves the predicted class; it cannot fix classification errors or detect unsupported requests.",
                        "API and CLI still return uncalibrated scores and require human review."],
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2)
        handle.write("\n")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("data_dir", type=Path)
    parser.add_argument("model_dir", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    try:
        report = run_experiment(args.data_dir, args.model_dir, args.output)
    except (OSError, ValueError, KeyError, UnicodeError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    print(json.dumps({"temperature": report["temperature"], "parts": report["parts"],
                      "development_audit": report["development_audit"]["frozen_threshold_simulation"],
                      "test_evaluated": False, "api_behavior_changed": False}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
