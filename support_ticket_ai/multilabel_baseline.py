"""Offline, fixed-recipe multilabel baseline on train and selection only."""

import argparse
import hashlib
from importlib.metadata import version
import json
from pathlib import Path
import sys

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, f1_score, hamming_loss, precision_score, recall_score
from sklearn.multiclass import OneVsRestClassifier
from sklearn.preprocessing import MultiLabelBinarizer

from .prepare import normalize


def load_development(directory: Path):
    """Read only manifest, train and selection; verify integrity before fitting."""
    manifest = json.loads((directory / 'manifest.json').read_text(encoding='utf-8'))
    if manifest.get('schema_version') != 1 or manifest.get('taxonomy_id') != 'blendbanking77-v1':
        raise ValueError('Expected prepared BlendBanking77 taxonomy/version.')
    vocabulary = manifest['label_vocabulary']
    if (not isinstance(vocabulary, list) or len(vocabulary) < 2 or
            any(not isinstance(label, str) or not label for label in vocabulary) or
            vocabulary != sorted(set(vocabulary))):
        raise ValueError('Invalid native label vocabulary.')
    partitions = {}
    ids, groups = set(), set()
    for name in ('train', 'selection'):
        filename = f'{name}.jsonl'
        raw = (directory / filename).read_bytes()
        if hashlib.sha256(raw).hexdigest() != manifest['files_sha256'][filename]:
            raise ValueError(f'Checksum mismatch: {filename}.')
        rows = [json.loads(line) for line in raw.splitlines()]
        if not rows or len(rows) != manifest['partition_counts'][name]:
            raise ValueError('Unexpected development row count.')
        for row in rows:
            text, labels, case_id = row['text'], row['labels'], row['case_id']
            if (not isinstance(text, str) or not text.strip() or not isinstance(case_id, str) or
                    not case_id or not isinstance(labels, list) or not labels or
                    any(not isinstance(label, str) or label not in vocabulary for label in labels) or
                    labels != sorted(set(labels))):
                raise ValueError('Invalid development record.')
            group = hashlib.sha256(normalize(text).encode()).hexdigest()
            if group != row['text_group_sha256'] or group in groups or case_id in ids:
                raise ValueError('Duplicate, overlapping, or invalid development identity/text group.')
            groups.add(group)
            ids.add(case_id)
        partitions[name] = rows
    if {label for row in partitions['train'] for label in row['labels']} != set(vocabulary):
        raise ValueError('Training vocabulary is incomplete.')
    return manifest, partitions


def threshold_predictions(probabilities):
    """Independent binary decisions; do not force a single label or nonempty set."""
    return (np.asarray(probabilities) >= 0.5).astype(np.int8)


def measure(expected, predicted):
    cardinality = expected.sum(axis=1)
    return {
        'rows': len(expected),
        'exact_set_accuracy': float(accuracy_score(expected, predicted)),
        'micro_f1': float(f1_score(expected, predicted, average='micro', zero_division=0)),
        'macro_f1': float(f1_score(expected, predicted, average='macro', zero_division=0)),
        'micro_precision': float(precision_score(expected, predicted, average='micro', zero_division=0)),
        'micro_recall': float(recall_score(expected, predicted, average='micro', zero_division=0)),
        'hamming_loss': float(hamming_loss(expected, predicted)),
        'mean_predicted_labels': float(predicted.sum(axis=1).mean()),
        'empty_prediction_fraction': float((predicted.sum(axis=1) == 0).mean()),
        'by_true_label_count': {
            str(int(count)): {
                'rows': int((cardinality == count).sum()),
                'exact_set_accuracy': float(accuracy_score(expected[cardinality == count], predicted[cardinality == count])),
                'micro_f1': float(f1_score(expected[cardinality == count], predicted[cardinality == count], average='micro', zero_division=0)),
            } for count in sorted(set(cardinality))
        },
    }


def run(directory: Path) -> dict:
    manifest, partitions = load_development(directory)
    train, selection = partitions['train'], partitions['selection']
    binarizer = MultiLabelBinarizer(classes=manifest['label_vocabulary'])
    expected_train = binarizer.fit_transform([row['labels'] for row in train])
    expected = binarizer.transform([row['labels'] for row in selection])
    vectorizer = TfidfVectorizer(ngram_range=(1, 2), min_df=2, max_features=50000, sublinear_tf=True)
    features = vectorizer.fit_transform([row['text'] for row in train])
    classifier = OneVsRestClassifier(LogisticRegression(C=1.0, max_iter=1000, random_state=42), n_jobs=1)
    classifier.fit(features, expected_train)
    predicted = threshold_predictions(classifier.predict_proba(vectorizer.transform([row['text'] for row in selection])))
    # A train-only comparator always predicts the single most frequent label.
    comparator = np.zeros_like(expected)
    most_frequent = int(expected_train.sum(axis=0).argmax())
    comparator[:, most_frequent] = 1
    return {
        'schema_version': 1, 'experiment': 'tfidf-ovr-fixed-v1',
        'dataset': manifest['dataset'], 'taxonomy_id': manifest['taxonomy_id'],
        'source_revision': manifest['source_revision'],
        'development_input_sha256': {name: manifest['files_sha256'][name] for name in ('train.jsonl', 'selection.jsonl')},
        'versions': {name: version(name) for name in ('scikit-learn', 'numpy', 'scipy')},
        'recipe': {'features': 'word TF-IDF', 'ngram_range': [1, 2], 'min_df': 2,
                   'max_features': 50000, 'sublinear_tf': True, 'classifier': '77 independent logistic-regression heads',
                   'C': 1.0, 'max_iter': 1000, 'random_state': 42, 'threshold': 0.5,
                   'threshold_tuned': False, 'actual_vocabulary_size': len(vectorizer.vocabulary_),
                   'all_heads_converged': all(int(head.n_iter_.max()) < 1000 for head in classifier.estimators_)},
        'train_rows': len(train), 'selection_rows': len(selection), 'label_count': len(binarizer.classes_),
        'selection': measure(expected, predicted),
        'most_frequent_single_label': {'label': str(binarizer.classes_[most_frequent]), 'selection': measure(expected, comparator)},
        'calibration_read': False, 'test_payload_decoded': False, 'test_evaluated': False,
        'model_exported': False, 'live_model_changed': False,
        'limitations': [
            'Selection is development data, not an independent final test.',
            'Publisher blended labels are not independently adjudicated; component/template overlap is unknown.',
            'Fixed 0.5 decisions are uncalibrated and provide no reliability or out-of-scope guarantee.',
            'Native banking labels do not establish accuracy on the app taxonomy or action spans, conditions, negation and relations.',
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('benchmark_dir', type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists():
        parser.error('Output already exists; choose a fresh experiment file.')
    try:
        report = run(args.benchmark_dir)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open('x', encoding='utf-8', newline='\n') as handle:
            handle.write(json.dumps(report, indent=2, allow_nan=False) + '\n')
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(f'Multilabel experiment failed: {error}', file=sys.stderr)
        return 1
    print(json.dumps({'selection': report['selection'], 'test_evaluated': False}, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
