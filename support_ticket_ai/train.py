"""Fit a fixed baseline using train and validation files only; never read test.csv."""

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import platform
import shutil
import sys
import tempfile
import warnings

import joblib
import numpy
import scipy
import sklearn
from sklearn.dummy import DummyClassifier
from sklearn.exceptions import ConvergenceWarning
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix, f1_score
from sklearn.pipeline import Pipeline

from .data import load_tickets
from .prepare import normalize


def build_model(seed: int = 42) -> Pipeline:
    return Pipeline([
        ("tfidf", TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True,
                                  max_features=50000, min_df=1)),
        ("classifier", LogisticRegression(C=1.0, max_iter=1000, random_state=seed)),
    ])


def evaluate(targets, predictions, categories) -> dict:
    return {
        "accuracy": accuracy_score(targets, predictions),
        "macro_f1": f1_score(targets, predictions, labels=categories, average="macro", zero_division=0),
        "per_class": classification_report(targets, predictions, labels=categories,
                                            output_dict=True, zero_division=0),
        "confusion_matrix_labels": categories,
        "confusion_matrix_rows_true_columns_predicted": confusion_matrix(
            targets, predictions, labels=categories).tolist(),
    }


def run_training(data_dir: Path, output: Path) -> dict:
    if output.exists():
        raise ValueError("Output already exists; choose a new run directory.")
    manifest_bytes = (data_dir / "manifest.json").read_bytes()
    manifest = json.loads(manifest_bytes)
    categories = manifest["audit"]["categories"]
    if len(categories) < 2 or len(set(categories)) != len(categories):
        raise ValueError("Manifest must define at least two distinct categories.")
    records = {}
    # Intentionally no test data loading in this command.
    for name in ("train", "validation"):
        path = data_dir / f"{name}.csv"
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual != manifest["split_sha256"][name]:
            raise ValueError(f"Checksum mismatch: {name}.")
        records[name] = load_tickets(path, categories=frozenset(categories))
        if {r.category for r in records[name]} != set(categories):
            raise ValueError(f"Missing category in {name}.")
    train, validation = records["train"], records["validation"]
    if {r.ticket_id for r in train} & {r.ticket_id for r in validation}:
        raise ValueError("Ticket ID overlap between train and validation.")
    if {normalize(r.text) for r in train} & {normalize(r.text) for r in validation}:
        raise ValueError("Normalized text overlap between train and validation.")
    texts, targets = [r.text for r in train], [r.category for r in train]
    val_texts, val_targets = [r.text for r in validation], [r.category for r in validation]
    model = build_model(manifest["seed"])
    with warnings.catch_warnings():
        warnings.simplefilter("error", ConvergenceWarning)
        model.fit(texts, targets)
    majority = DummyClassifier(strategy="most_frequent").fit(texts, targets)
    report = {
        "evaluation_split": "validation",
        "test_evaluated": False,
        "source_revision": manifest["source_revision"],
        "source_sha256": manifest["source_sha256"],
        "preparation_manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
        "seed": manifest["seed"],
        "training_counts": dict(sorted(Counter(targets).items())),
        "validation_counts": dict(sorted(Counter(val_targets).items())),
        "versions": {"python": platform.python_version(), "scikit-learn": sklearn.__version__,
                     "numpy": numpy.__version__, "scipy": scipy.__version__, "joblib": joblib.__version__},
        "configuration": {"ngram_range": [1, 2], "max_features": 50000, "min_df": 1,
                          "sublinear_tf": True, "C": 1.0, "max_iter": 1000,
                          "class_weight": None, "solver": "lbfgs"},
        "vocabulary_size": len(model.named_steps["tfidf"].vocabulary_),
        "majority": evaluate(val_targets, majority.predict(val_texts), categories),
        "tfidf_logistic_regression": evaluate(val_targets, model.predict(val_texts), categories),
        "limitations": ["Synthetic source; no production reliability claim.",
                        "Normalized exact deduplication does not remove template/paraphrase overlap.",
                        "Single seed, fixed configuration; probabilities not calibrated."],
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=output.parent) as staging:
        stage = Path(staging)
        joblib.dump(model, stage / "model.joblib")
        report["model_sha256"] = hashlib.sha256((stage / "model.joblib").read_bytes()).hexdigest()
        (stage / "validation_metrics.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        output.mkdir()
        try:
            for path in stage.iterdir():
                shutil.copyfile(path, output / path.name)
        except OSError:
            shutil.rmtree(output)
            raise
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("data_dir", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    try:
        report = run_training(args.data_dir, args.output)
    except (OSError, ValueError, KeyError, UnicodeError, ConvergenceWarning) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    for name in ("majority", "tfidf_logistic_regression"):
        print(f"{name}: validation macro-F1={report[name]['macro_f1']:.4f}; accuracy={report[name]['accuracy']:.4f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
