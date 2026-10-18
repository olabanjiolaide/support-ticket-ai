"""Measure nearest-training similarity for validation; never read the test split."""

import argparse
import hashlib
import json
from pathlib import Path
import sys

import numpy as np
from sklearn.metrics.pairwise import cosine_similarity

from .data import load_tickets
from .predict import TicketPredictor
from .prepare import normalize


def summarize_similarity(train_vectors, validation_vectors, batch_size: int = 128) -> dict:
    """Bound dense allocation by batch_size * training rows, not all pairs."""
    if batch_size < 1 or train_vectors.shape[0] < 1 or validation_vectors.shape[0] < 1:
        raise ValueError("Nonempty splits and a positive batch size are required.")
    scores = []
    for start in range(0, validation_vectors.shape[0], batch_size):
        similarities = cosine_similarity(validation_vectors[start:start + batch_size], train_vectors)
        scores.extend(np.clip(similarities.max(axis=1), 0, 1).tolist())
    values = np.asarray(scores)
    return {
        "validation_rows": len(scores),
        "nearest_training_cosine_mean": float(values.mean()),
        "nearest_training_cosine_quantiles": {
            str(q): float(np.quantile(values, q)) for q in (0.5, 0.9, 0.95, 0.99)
        },
        "thresholds": {
            str(threshold): {"count": int((values >= threshold).sum()),
                             "fraction": float((values >= threshold).mean())}
            for threshold in (0.8, 0.9, 0.95, 0.99)
        },
    }


def audit(data_dir: Path, model_dir: Path) -> dict:
    manifest_bytes = (data_dir / "manifest.json").read_bytes()
    manifest = json.loads(manifest_bytes)
    predictor = TicketPredictor(model_dir)
    if hashlib.sha256(manifest_bytes).hexdigest() != predictor.metadata["preparation_manifest_sha256"]:
        raise ValueError("Preparation manifest does not match the model run.")
    records = {}
    for name in ("train", "validation"):
        path = data_dir / f"{name}.csv"
        if hashlib.sha256(path.read_bytes()).hexdigest() != manifest["split_sha256"][name]:
            raise ValueError(f"Checksum mismatch: {name}.")
        records[name] = load_tickets(path, categories=frozenset(manifest["audit"]["categories"]))
    vectorizer = predictor.model.named_steps["tfidf"]
    train = vectorizer.transform([r.text for r in records["train"]])
    validation = vectorizer.transform([r.text for r in records["validation"]])
    summary = summarize_similarity(train, validation)
    summary.update({
        "evaluation_split": "validation",
        "test_evaluated": False,
        "space": "Training-fitted word TF-IDF from the baseline pipeline",
        "source_revision": manifest["source_revision"],
        "preparation_manifest_sha256": predictor.metadata["preparation_manifest_sha256"],
        "model_sha256": predictor.metadata["model_sha256"],
        "normalized_exact_overlap": len(
            {normalize(r.text) for r in records["train"]} &
            {normalize(r.text) for r in records["validation"]}),
        "limitations": ["Cosine similarity is a diagnostic, not a template-family independence test.",
                        "Shared words may reflect legitimate category signals or repeated templates.",
                        "Similarity thresholds are descriptive; not used for routing or tuning."],
    })
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("data_dir", type=Path)
    parser.add_argument("model_dir", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    try:
        if args.output.exists():
            raise ValueError("Output already exists; choose a new report filename.")
        report = audit(args.data_dir, args.model_dir)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x", encoding="utf-8") as handle:
            json.dump(report, handle, indent=2)
            handle.write("\n")
    except (OSError, ValueError, KeyError, UnicodeError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
