"""Diagnose a frozen model and cutoff on provisional authored stress probes."""

import argparse
from collections import Counter
import csv
import hashlib
import json
import math
from pathlib import Path
import sys

import numpy as np

from .resources import data_path

from .abstain import summarize
from .data import load_tickets
from .predict import MAX_TEXT_LENGTH, TicketPredictor
from .prepare import normalize

PROBES_PATH = data_path('robustness_probes.csv')


def fingerprint(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_probes(path: Path, categories: set[str]) -> list[dict]:
    with path.open(encoding='utf-8-sig', newline='') as handle:
        reader = csv.DictReader(handle, strict=True)
        headers = reader.fieldnames or []
        if len(headers) != 5 or set(headers) != {'case_id', 'slice', 'text', 'expected_category', 'label_status'}:
            raise ValueError('Unexpected probe schema.')
        rows = list(reader)
    if not rows:
        raise ValueError('Probe set is empty.')
    ids, texts = set(), set()
    for row in rows:
        if None in row or any(value is None or not value.strip() for value in row.values()):
            raise ValueError('Blank or malformed probe fields.')
        row.update({key: value.strip() for key, value in row.items()})
        if len(row['text']) > MAX_TEXT_LENGTH:
            raise ValueError('Probe exceeds the API character limit.')
        if row['expected_category'] not in categories | {'UNSUPPORTED', 'REVIEW'}:
            raise ValueError('Unknown expected category.')
        if row['label_status'] not in {'provisional', 'reviewed'}:
            raise ValueError('Unknown label status.')
        if row['case_id'] in ids or normalize(row['text']) in texts:
            raise ValueError('Duplicate probe ID or normalized text.')
        ids.add(row['case_id'])
        texts.add(normalize(row['text']))
    return rows


def diagnostic_metrics(rows: list[dict], threshold: float | None) -> dict:
    # REVIEW has no unique routing target; do not score it as a classifier error.
    metrics = summarize([row for row in rows if row['expected_category'] != 'REVIEW'], threshold)
    ambiguous = [row for row in rows if row['expected_category'] == 'REVIEW']
    withheld = sum(threshold is not None and row['score'] < threshold for row in ambiguous)
    metrics.update({'ambiguous_rows': len(ambiguous), 'ambiguous_withheld_rows': withheld,
                    'ambiguous_withheld_fraction': withheld / len(ambiguous) if ambiguous else None})
    return metrics


def check_training_overlap(prepared_dir: Path, metadata: dict, rows: list[dict], categories: set[str]) -> dict:
    manifest_path = prepared_dir / 'manifest.json'
    if fingerprint(manifest_path) != metadata['preparation_manifest_sha256']:
        raise ValueError('Preparation manifest does not match this model.')
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    train_path = prepared_dir / 'train.csv'
    if fingerprint(train_path) != manifest['split_sha256']['train']:
        raise ValueError('Training CSV checksum mismatch.')
    train = load_tickets(train_path, categories=frozenset(categories))
    normalized = {normalize(ticket.text) for ticket in train}
    matches = [row['case_id'] for row in rows if normalize(row['text']) in normalized]
    return {'training_sha256': fingerprint(train_path), 'exact_overlap_case_ids': matches,
            'exact_overlap_rows': len(matches),
            'method': 'NFKC + casefold + whitespace collapse; near-template overlap not measured'}


def evaluate(model_dir: Path, prepared_dir: Path, probes_path: Path = PROBES_PATH,
             threshold: float = .7) -> dict:
    if type(threshold) not in (int, float) or not math.isfinite(threshold) or not 0 < threshold <= 1:
        raise ValueError('Threshold must be finite and in (0, 1].')
    predictor = TicketPredictor(model_dir)
    categories = set(predictor.model.classes_)
    rows = load_probes(probes_path, categories)
    overlap = check_training_overlap(prepared_dir, predictor.metadata, rows, categories)
    if overlap['exact_overlap_rows']:
        raise ValueError('Probes duplicate normalized training requests; remove or rewrite before evaluation.')
    probabilities = predictor.model.predict_proba([row['text'] for row in rows])
    for row, scores in zip(rows, probabilities):
        top = int(np.argmax(scores))
        row.update(top_category=str(predictor.model.classes_[top]), score=float(scores[top]))
    return {
        'experiment': 'provisional_authored_robustness_diagnostics',
        'test_evaluated': False, 'model_retrained': False, 'policy_installed': False,
        'threshold_selection_performed': False, 'frozen_diagnostic_threshold': threshold,
        'installed_policy_threshold': predictor.abstention_threshold,
        'model_sha256': predictor.metadata['model_sha256'], 'training_versions': predictor.metadata['versions'],
        'probes_sha256': fingerprint(probes_path), 'training_overlap': overlap,
        'label_status_counts': dict(Counter(row['label_status'] for row in rows)),
        'forced_suggestion_baseline': diagnostic_metrics(rows, None),
        'frozen_cutoff': diagnostic_metrics(rows, threshold),
        'by_slice': {name: diagnostic_metrics([row for row in rows if row['slice'] == name], threshold)
                     for name in sorted({row['slice'] for row in rows})},
        'by_category': {name: diagnostic_metrics([row for row in rows if row['expected_category'] == name], threshold)
                        for name in sorted(categories)},
        'reviewed_only': diagnostic_metrics([row for row in rows if row['label_status'] == 'reviewed'], threshold),
        'cases': [{**row, 'decision': 'suggestion' if row['score'] >= threshold else 'abstain'} for row in rows],
        'limitations': [
            'Authored examples and provisional labels are development diagnostics, not independent evidence.',
            'REVIEW rows have no unique target; withholding is reported separately from category accuracy.',
            'No threshold search, retraining, or live policy change is performed.',
            'Repeated intents are correlated; row counts are not independent sample sizes.',
            'Exact training overlap is checked; semantic and template overlap remain possible.',
            'Once inspected, these probes are development data and cannot become a final test set.',
            'The reviewed flag records a workflow state; it cannot establish reviewer independence.',
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('model_dir', type=Path)
    parser.add_argument('prepared_dir', type=Path, help='Matching prepared directory; reads only manifest and train.csv')
    parser.add_argument('output', type=Path, help='New JSON report; existing reports are preserved')
    parser.add_argument('--probes', type=Path, default=PROBES_PATH)
    parser.add_argument('--threshold', type=float, default=.7, help='Frozen diagnostic cutoff, not a tuning search')
    args = parser.parse_args()
    try:
        if args.output.exists():
            raise ValueError('Report already exists; choose a new filename.')
        report = evaluate(args.model_dir, args.prepared_dir, args.probes, args.threshold)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open('x', encoding='utf-8') as handle:
            json.dump(report, handle, indent=2)
            handle.write('\n')
    except (OSError, ValueError, KeyError, UnicodeError, csv.Error) as error:
        print(f'Error: {error}', file=sys.stderr)
        return 1
    print(json.dumps({key: report[key] for key in ('label_status_counts', 'forced_suggestion_baseline',
                                                 'frozen_cutoff', 'test_evaluated', 'policy_installed')}, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
