"""Audit solver stopping tolerance after the failed duplicate-feature control."""

import argparse
import hashlib
import json
from pathlib import Path
import sys
import warnings

import numpy as np
from scipy.special import expit
from sklearn.exceptions import ConvergenceWarning
from sklearn.linear_model import LogisticRegression
from sklearn.multiclass import OneVsRestClassifier
from sklearn.preprocessing import MultiLabelBinarizer

from .multilabel_baseline import load_development, measure, threshold_predictions
from .resources import data_path
from .semantic_experiment import ENCODER_ID, ENCODER_REVISION, encode, load_encoder
from .semantic_multilabel import dependency_versions, source_fingerprints

PROTOCOL_PATH = data_path('segment_optimizer_protocol.json')


def validate_protocol(protocol, manifest):
    if (not isinstance(protocol, dict) or type(protocol.get('schema_version')) is not int or
            protocol['schema_version'] != 1 or protocol.get('experiment') != 'segment-optimizer-audit-v1' or
            protocol.get('taxonomy_id') != manifest['taxonomy_id'] or
            protocol.get('encoder_id') != ENCODER_ID or protocol.get('encoder_revision') != ENCODER_REVISION or
            protocol.get('representations') != ['whole', 'whole_duplicate'] or
            protocol.get('tolerances') != [1e-4, 1e-8] or protocol.get('C') != 10. or
            protocol.get('class_weight', 'missing') is not None or protocol.get('threshold') != .5 or
            type(protocol.get('max_iter')) is not int or protocol['max_iter'] != 5000 or
            type(protocol.get('random_state')) is not int or protocol['random_state'] != 42):
        raise ValueError('Protocol differs from the fixed numerical audit.')
    expected = {name: manifest['files_sha256'][name] for name in ('train.jsonl', 'selection.jsonl')}
    if protocol.get('development_input_sha256') != expected:
        raise ValueError('Protocol input fingerprints differ from prepared development data.')


def duplicate_features(values):
    values = np.asarray(values, dtype=np.float64)
    return np.concatenate([values, values], axis=1) / np.sqrt(2)


def transformed_probabilities(heads, duplicated):
    # This transforms a fitted model exactly; no second optimization occurs here.
    coefficients = np.concatenate([estimator.coef_ for estimator in heads.estimators_])
    weights = np.concatenate([coefficients, coefficients], axis=1) / np.sqrt(2)
    intercepts = np.array([estimator.intercept_[0] for estimator in heads.estimators_])
    return expit(duplicated @ weights.T + intercepts)


def discrepancies(first, second):
    return {'max_absolute_score_difference': float(np.max(np.abs(first - second))),
            'rows_with_different_predicted_sets': int(np.any(threshold_predictions(first) !=
                                                            threshold_predictions(second), axis=1).sum())}


def run(directory: Path, cache_dir: Path, protocol_path: Path = PROTOCOL_PATH, *, encoder_factory=None):
    manifest, partitions = load_development(directory)
    raw = protocol_path.read_bytes()
    protocol = json.loads(raw)
    validate_protocol(protocol, manifest)
    encoder = (encoder_factory or load_encoder)(cache_dir)
    fingerprints = source_fingerprints(cache_dir) if encoder_factory is None else None
    features = {}
    for split in ('train', 'selection'):
        print(f'Numerical audit: encoding {split}: {len(partitions[split])}', file=sys.stderr, flush=True)
        values = encode(encoder, [row['text'] for row in partitions[split]]).astype(np.float64)
        features[split] = {'whole': values, 'whole_duplicate': duplicate_features(values)}
    binarizer = MultiLabelBinarizer(classes=manifest['label_vocabulary'])
    train_targets = binarizer.fit_transform([row['labels'] for row in partitions['train']])
    expected = binarizer.transform([row['labels'] for row in partitions['selection']])
    pairs = []
    for tolerance in protocol['tolerances']:
        results, probabilities, whole_model = [], {}, None
        for name in protocol['representations']:
            print(f'Numerical audit: fitting {name}, tol={tolerance}', file=sys.stderr, flush=True)
            heads = OneVsRestClassifier(LogisticRegression(C=10., tol=tolerance, max_iter=5000,
                                                          random_state=42), n_jobs=1)
            with warnings.catch_warnings():
                warnings.simplefilter('error', ConvergenceWarning)
                heads.fit(features['train'][name], train_targets)
            probabilities[name] = heads.predict_proba(features['selection'][name])
            iterations = [int(head.n_iter_.max()) for head in heads.estimators_]
            results.append({'representation': name, 'all_heads_converged': True,
                            'maximum_iterations': max(iterations), 'median_iterations': float(np.median(iterations)),
                            'selection': measure(expected, threshold_predictions(probabilities[name]))})
            if name == 'whole':
                whole_model = heads
        transformed = transformed_probabilities(whole_model, features['selection']['whole_duplicate'])
        pairs.append({'tolerance': tolerance, 'fits': results,
                      'independent_fit_difference': discrepancies(probabilities['whole'], probabilities['whole_duplicate']),
                      'exact_coefficient_transform_difference': discrepancies(probabilities['whole'], transformed)})
    return {'schema_version': 1, 'experiment': protocol['experiment'], 'protocol': protocol,
            'protocol_sha256': hashlib.sha256(raw).hexdigest(), 'versions': dependency_versions(),
            'dataset': manifest['dataset'], 'taxonomy_id': manifest['taxonomy_id'],
            'source_revision': manifest['source_revision'], 'train_rows': len(partitions['train']),
            'selection_rows': len(partitions['selection']), 'label_count': len(binarizer.classes_),
            'encoder': {'id': ENCODER_ID, 'revision': ENCODER_REVISION, 'frozen': True,
                        'source_file_sha256': fingerprints,
                        'implementation': 'injected_test_double' if encoder_factory else 'pinned_sentence_transformer'},
            'tolerance_pairs': pairs, 'model_selection_performed': False,
            'calibration_read': False, 'test_evaluated': False, 'test_payload_decoded': False,
            'threshold_tuned': False, 'model_exported': False, 'live_model_changed': False,
            'limitations': [
                'Diagnostic follow-up fixed after observing duplicate-control disagreement; not an independent predictive evaluation.',
                'Maximum-iteration cap is 5000 at both tolerances; actual iteration counts are recorded.',
                'Exact parameter transformation tests the feature construction without a second optimization.',
                'This audit does not refit or validate the segment-pooling candidates at tighter tolerance.',
                'Accuracy is reported descriptively, not used to choose a tolerance or promote a live model.',
            ]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('benchmark_dir', type=Path)
    parser.add_argument('--cache-dir', type=Path, default=Path('artifacts/encoder-cache'))
    parser.add_argument('--protocol', type=Path, default=PROTOCOL_PATH)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error('Output already exists; choose a fresh experiment file.')
    try:
        report = run(args.benchmark_dir, args.cache_dir, args.protocol)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open('x', encoding='utf-8', newline='\n') as handle:
            handle.write(json.dumps(report, indent=2, allow_nan=False) + '\n')
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(f'Segment numerical audit failed: {error}', file=sys.stderr)
        return 1
    print(json.dumps({'differences': [{'tolerance': pair['tolerance'],
                    'independent': pair['independent_fit_difference'],
                    'exact_transform': pair['exact_coefficient_transform_difference']}
                    for pair in report['tolerance_pairs']], 'test_evaluated': False}, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
