"""Compare fixed word and character features offline; never read the held-out test."""

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
from sklearn.pipeline import Pipeline

from .data import load_tickets
from .predict import TicketPredictor
from .prepare import normalize
from .robustness import (PROBES_PATH, check_training_overlap, diagnostic_metrics,
                         fingerprint, load_probes)
from .train import evaluate

CHARACTER_CONFIG = {'analyzer': 'char_wb', 'ngram_range': [3, 5], 'max_features': 50000,
                    'min_df': 2, 'sublinear_tf': True}
CUTOFF = .7


def build_character_model(seed: int = 42) -> Pipeline:
    config = {**CHARACTER_CONFIG, 'ngram_range': tuple(CHARACTER_CONFIG['ngram_range'])}
    return Pipeline([('tfidf', TfidfVectorizer(**config)),
                     ('classifier', LogisticRegression(C=1.0, max_iter=1000, random_state=seed))])


def score_probes(model, probes: list[dict]) -> dict:
    rows = []
    for probe, scores in zip(probes, model.predict_proba([row['text'] for row in probes])):
        index = int(np.argmax(scores))
        rows.append({**probe, 'top_category': str(model.classes_[index]), 'score': float(scores[index])})
    return {
        'forced_suggestions': diagnostic_metrics(rows, None),
        'fixed_cutoff': diagnostic_metrics(rows, CUTOFF),
        'by_slice': {name: {'forced_suggestions': diagnostic_metrics([r for r in rows if r['slice'] == name], None),
                            'fixed_cutoff': diagnostic_metrics([r for r in rows if r['slice'] == name], CUTOFF)}
                     for name in sorted({row['slice'] for row in rows})},
        'by_category': {name: diagnostic_metrics([r for r in rows if r['expected_category'] == name], CUTOFF)
                        for name in sorted(model.classes_)},
        'cases': [{**row, 'decision': 'suggestion' if row['score'] >= CUTOFF else 'abstain'} for row in rows],
    }


def compare(model_dir: Path, prepared_dir: Path, probes_path: Path = PROBES_PATH) -> dict:
    baseline = TicketPredictor(model_dir)
    categories = set(baseline.model.classes_)
    probes = load_probes(probes_path, categories)
    overlap = check_training_overlap(prepared_dir, baseline.metadata, probes, categories)
    if overlap['exact_overlap_rows']:
        raise ValueError('Probes overlap normalized training requests.')
    manifest = json.loads((prepared_dir / 'manifest.json').read_text(encoding='utf-8'))
    records = {}
    # These two explicit paths are the only split files opened. No test access.
    for split in ('train', 'validation'):
        path = prepared_dir / f'{split}.csv'
        if fingerprint(path) != manifest['split_sha256'][split]:
            raise ValueError(f'Checksum mismatch: {split}.')
        records[split] = load_tickets(path, categories=frozenset(categories))
        if {row.category for row in records[split]} != categories:
            raise ValueError(f'Missing model categories in {split}.')
    train, validation = records['train'], records['validation']
    if ({row.ticket_id for row in train} & {row.ticket_id for row in validation} or
            {normalize(row.text) for row in train} & {normalize(row.text) for row in validation}):
        raise ValueError('Training/validation overlap.')
    character = build_character_model(manifest['seed'])
    with warnings.catch_warnings():
        warnings.simplefilter('error', ConvergenceWarning)
        character.fit([row.text for row in train], [row.category for row in train])
    results = {}
    for name, model in [('word', baseline.model), ('character', character)]:
        results[name] = {
            'vocabulary_size': len(model.named_steps['tfidf'].vocabulary_),
            'validation': evaluate([row.category for row in validation],
                                   model.predict([row.text for row in validation]), sorted(categories)),
            'probes': score_probes(model, probes),
        }
    return {
        'experiment': 'fixed_word_vs_character_development_comparison',
        'test_evaluated': False, 'live_model_changed': False, 'policy_installed': False,
        'candidate_bundle_exported': False, 'threshold_selection_performed': False,
        'diagnostic_cutoff': CUTOFF,
        'baseline_model_sha256': baseline.metadata['model_sha256'],
        'preparation_manifest_sha256': fingerprint(prepared_dir / 'manifest.json'),
        'probes_sha256': fingerprint(probes_path), 'training_overlap': overlap,
        'baseline_training_versions': baseline.metadata['versions'],
        'versions': {'python': platform.python_version(), 'scikit-learn': sklearn.__version__,
                     'numpy': np.__version__, 'scipy': scipy.__version__, 'joblib': joblib.__version__},
        'seed': manifest['seed'], 'training_rows': len(train), 'validation_rows': len(validation),
        'label_status_counts': dict(Counter(row['label_status'] for row in probes)),
        'word_configuration': baseline.metadata['configuration'],
        'character_configuration': {**CHARACTER_CONFIG, 'C': 1.0, 'max_iter': 1000,
                                    'class_weight': None, 'solver': 'lbfgs'},
        'models': results,
        'limitations': [
            'Exploratory comparison on previously inspected, provisional authored probes.',
            'Source validation is synthetic and has known template overlap.',
            'One fixed character configuration and seed; no model selected for deployment.',
            'Raw scores differ across models; a shared numerical cutoff is not matched risk or calibration.',
            'Neither classifier learns an UNSUPPORTED category or a separate scope decision.',
            'No statistical significance or production reliability claim is established.',
            'Three label rules were discussed with the user after showing answers; this is not independent review.',
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('model_dir', type=Path)
    parser.add_argument('prepared_dir', type=Path)
    parser.add_argument('output', type=Path, help='New JSON report, never overwritten')
    parser.add_argument('--probes', type=Path, default=PROBES_PATH)
    args = parser.parse_args()
    try:
        if args.output.exists():
            raise ValueError('Report already exists; choose a new filename.')
        report = compare(args.model_dir, args.prepared_dir, args.probes)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open('x', encoding='utf-8') as handle:
            json.dump(report, handle, indent=2)
            handle.write('\n')
    except (OSError, ValueError, KeyError, UnicodeError, csv.Error, ConvergenceWarning) as error:
        print(f'Error: {error}', file=sys.stderr)
        return 1
    for name, result in report['models'].items():
        print(json.dumps({'model': name, 'validation_macro_f1': result['validation']['macro_f1'],
                          'forced_suggestions': result['probes']['forced_suggestions'],
                          'fixed_cutoff': result['probes']['fixed_cutoff']}, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
