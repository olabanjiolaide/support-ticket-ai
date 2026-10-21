"""Fit an offline binary scope gate using authored negative training examples."""

import argparse
from collections import Counter
import csv
import json
from pathlib import Path
import platform
import sys
import warnings

import joblib
import numpy as np
import scipy
import sklearn
from sklearn.exceptions import ConvergenceWarning
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import FeatureUnion, Pipeline

from .resources import data_path

from .data import load_tickets
from .predict import TicketPredictor
from .prepare import normalize
from .robustness import (PROBES_PATH, check_training_overlap, diagnostic_metrics,
                         fingerprint, load_probes)

NEGATIVES_PATH = data_path('scope_training_negatives.csv')
CATEGORY_CUTOFF = .7
SCOPE_CUTOFF = .5
FEATURE_CONFIG = {'word_ngram_range': [1, 2], 'character_analyzer': 'char_wb',
                  'character_ngram_range': [3, 5], 'max_features_per_branch': 20000,
                  'min_df': 1, 'sublinear_tf': True, 'class_weight': 'balanced',
                  'C': 1.0, 'max_iter': 1000, 'solver': 'lbfgs'}


def build_scope_model(seed: int = 42) -> Pipeline:
    features = FeatureUnion([
        ('word', TfidfVectorizer(ngram_range=(1, 2), max_features=20000, sublinear_tf=True)),
        ('character', TfidfVectorizer(analyzer='char_wb', ngram_range=(3, 5),
                                    max_features=20000, sublinear_tf=True)),
    ])
    return Pipeline([('features', features),
                     ('classifier', LogisticRegression(C=1.0, max_iter=1000,
                                                       class_weight='balanced', random_state=seed))])


def reject_negative_overlap(negatives: list[dict], probes: list[dict]) -> None:
    if not negatives or any(row['expected_category'] != 'UNSUPPORTED' for row in negatives):
        raise ValueError('Scope training negatives must all be UNSUPPORTED.')
    if {normalize(row['text']) for row in negatives} & {normalize(row['text']) for row in probes}:
        raise ValueError('Scope training negatives overlap evaluation probes.')


def policy_metrics(rows: list[dict], mode: str) -> dict:
    # Reuse count definitions with a binary acceptance indicator. Keep original
    # category and scope scores in report cases, rather than invent a joint probability.
    metrics = diagnostic_metrics([{**row, 'score': float(row[mode])} for row in rows], .5)
    metrics.pop('threshold')
    return metrics


def score_policies(category_model, scope_model, probes: list[dict]) -> dict:
    texts = [row['text'] for row in probes]
    category_scores = category_model.predict_proba(texts)
    scope_scores = scope_model.predict_proba(texts)
    support_index = list(scope_model.classes_).index('SUPPORTED')
    rows = []
    for probe, scores, binary in zip(probes, category_scores, scope_scores):
        index = int(np.argmax(scores))
        category_passes = float(scores[index]) >= CATEGORY_CUTOFF
        scope_passes = float(binary[support_index]) >= SCOPE_CUTOFF
        rows.append({**probe, 'top_category': str(category_model.classes_[index]),
                     'category_score': float(scores[index]), 'scope_score': float(binary[support_index]),
                     'category_cutoff_only': category_passes, 'scope_gate_only': scope_passes,
                     'combined': category_passes and scope_passes})
    modes = ('category_cutoff_only', 'scope_gate_only', 'combined')
    return {'policies': {mode: policy_metrics(rows, mode) for mode in modes},
            'by_slice': {name: {mode: policy_metrics([r for r in rows if r['slice'] == name], mode)
                               for mode in modes} for name in sorted({r['slice'] for r in rows})},
            'by_category': {name: {mode: policy_metrics([r for r in rows if r['expected_category'] == name], mode)
                                  for mode in modes} for name in sorted(category_model.classes_)},
            'cases': rows}


def run_experiment(model_dir: Path, prepared_dir: Path, probes_path: Path = PROBES_PATH,
                   negatives_path: Path = NEGATIVES_PATH) -> dict:
    baseline = TicketPredictor(model_dir)
    categories = set(baseline.model.classes_)
    probes = load_probes(probes_path, categories)
    negatives = load_probes(negatives_path, categories)
    reject_negative_overlap(negatives, probes)
    overlap = check_training_overlap(prepared_dir, baseline.metadata, probes + negatives, categories)
    if overlap['exact_overlap_rows']:
        raise ValueError('Authored data overlaps normalized support training text.')
    manifest = json.loads((prepared_dir / 'manifest.json').read_text(encoding='utf-8'))
    # Only the matching manifest and train.csv are read; no source validation/test.
    supported = load_tickets(prepared_dir / 'train.csv', categories=frozenset(categories))
    if {row.category for row in supported} != categories:
        raise ValueError('Missing support categories in training data.')
    texts = [row.text for row in supported] + [row['text'] for row in negatives]
    targets = ['SUPPORTED'] * len(supported) + ['UNSUPPORTED'] * len(negatives)
    scope = build_scope_model(manifest['seed'])
    with warnings.catch_warnings():
        warnings.simplefilter('error', ConvergenceWarning)
        scope.fit(texts, targets)
    results = score_policies(baseline.model, scope, probes)
    return {
        'experiment': 'authored_negative_binary_scope_gate',
        'test_evaluated': False, 'source_validation_evaluated': False,
        'live_model_changed': False, 'policy_installed': False, 'candidate_bundle_exported': False,
        'threshold_selection_performed': False,
        'category_cutoff': CATEGORY_CUTOFF, 'scope_cutoff': SCOPE_CUTOFF,
        'category_model': 'existing_word_baseline', 'baseline_model_sha256': baseline.metadata['model_sha256'],
        'preparation_manifest_sha256': fingerprint(prepared_dir / 'manifest.json'),
        'probes_sha256': fingerprint(probes_path), 'negatives_sha256': fingerprint(negatives_path),
        'training_overlap': overlap, 'negative_probe_exact_overlap_rows': 0,
        'seed': manifest['seed'], 'configuration': FEATURE_CONFIG,
        'training_counts': {'SUPPORTED': len(supported), 'UNSUPPORTED': len(negatives)},
        'probe_label_status_counts': dict(Counter(r['label_status'] for r in probes)),
        'negative_label_status_counts': dict(Counter(r['label_status'] for r in negatives)),
        'versions': {'python': platform.python_version(), 'scikit-learn': sklearn.__version__,
                     'numpy': np.__version__, 'scipy': scipy.__version__, 'joblib': joblib.__version__},
        **results,
        'limitations': [
            'Authored provisional negatives reflect previously inspected development failure families.',
            'Probe texts are not fitted directly, but semantic/template similarity can inflate results.',
            'Only normalized exact overlaps are checked; this is not a family-disjoint independent audit.',
            'Tiny authored negative class does not represent the universe of unsupported tasks.',
            'Balanced class weights do not make probabilities calibrated or reflect real traffic prevalence.',
            'Scope accepts/rejects tasks; it does not resolve multiple supported intents or guarantee correct routing.',
            'Category classifier is the word baseline; character-candidate gains are not combined here.',
            'All outputs still require human review. No production reliability claim is established.',
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('model_dir', type=Path)
    parser.add_argument('prepared_dir', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--probes', type=Path, default=PROBES_PATH)
    parser.add_argument('--negatives', type=Path, default=NEGATIVES_PATH)
    args = parser.parse_args()
    try:
        if args.output.exists():
            raise ValueError('Report already exists; choose a new filename.')
        report = run_experiment(args.model_dir, args.prepared_dir, args.probes, args.negatives)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open('x', encoding='utf-8') as handle:
            json.dump(report, handle, indent=2)
            handle.write('\n')
    except (OSError, ValueError, KeyError, UnicodeError, csv.Error, ConvergenceWarning) as error:
        print(f'Error: {error}', file=sys.stderr)
        return 1
    print(json.dumps(report['policies'], indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
