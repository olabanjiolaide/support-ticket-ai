"""Compare frozen sentence embeddings with the fixed public multilabel baseline."""

import argparse
import hashlib
from importlib.metadata import PackageNotFoundError, version
import json
from pathlib import Path
import sys
import warnings

import numpy as np
from sklearn.exceptions import ConvergenceWarning
from sklearn.linear_model import LogisticRegression
from sklearn.multiclass import OneVsRestClassifier
from sklearn.preprocessing import MultiLabelBinarizer

from .multilabel_baseline import load_development, measure, run as run_word, threshold_predictions
from .semantic_experiment import DIMENSIONS, ENCODER_ID, ENCODER_REVISION, encode, load_encoder


def dependency_versions():
    values = {}
    for name in ('scikit-learn', 'numpy', 'scipy', 'torch', 'sentence-transformers', 'transformers'):
        try:
            values[name] = version(name)
        except PackageNotFoundError:
            values[name] = None
    return values


def source_fingerprints(cache_dir):
    snapshot = cache_dir / ('models--' + ENCODER_ID.replace('/', '--')) / 'snapshots' / ENCODER_REVISION
    # Standard HF cache files, including tokenizer/config and safetensors; no pickle loading.
    names = ['model.safetensors', 'tokenizer.json', 'tokenizer_config.json', 'config.json',
             'modules.json', '1_Pooling/config.json', 'sentence_bert_config.json']
    return {name: hashlib.sha256((snapshot / name).read_bytes()).hexdigest() for name in names}


def run(directory: Path, cache_dir: Path, *, encoder_factory=None):
    manifest, partitions = load_development(directory)
    # Recompute the same frozen word recipe instead of trusting a supplied score file.
    word = run_word(directory)
    encoder = (encoder_factory or load_encoder)(cache_dir)
    fingerprints = source_fingerprints(cache_dir) if encoder_factory is None else None
    features, truncation = {}, {}
    for split in ('train', 'selection'):
        texts = [row['text'] for row in partitions[split]]
        print(f'Encoding {split}: {len(texts)} requests', file=sys.stderr, flush=True)
        lengths = encoder.tokenizer(texts, truncation=False, padding=False,
                                    return_length=True, verbose=False)['length']
        truncation[split] = {'rows_over_256_tokens': sum(int(n > 256) for n in lengths),
                             'maximum_untruncated_tokens': int(max(lengths))}
        features[split] = encode(encoder, texts)
    binarizer = MultiLabelBinarizer(classes=manifest['label_vocabulary'])
    expected_train = binarizer.fit_transform([row['labels'] for row in partitions['train']])
    expected = binarizer.transform([row['labels'] for row in partitions['selection']])
    heads = OneVsRestClassifier(LogisticRegression(C=1.0, max_iter=1000, random_state=42), n_jobs=1)
    with warnings.catch_warnings():
        warnings.simplefilter('error', ConvergenceWarning)
        heads.fit(features['train'], expected_train)
    predicted = threshold_predictions(heads.predict_proba(features['selection']))
    metrics = measure(expected, predicted)
    return {
        'schema_version': 1, 'experiment': 'frozen-minilm-multilabel-fixed-v1',
        'dataset': manifest['dataset'], 'taxonomy_id': manifest['taxonomy_id'],
        'source_revision': manifest['source_revision'],
        'development_input_sha256': word['development_input_sha256'],
        'versions': dependency_versions(),
        'encoder': {'id': ENCODER_ID, 'revision': ENCODER_REVISION, 'dimensions': DIMENSIONS,
                    'frozen': True, 'normalized': True, 'max_sequence_length': 256,
                    'device': 'cpu', 'batch_size': 64, 'source_file_sha256': fingerprints,
                    'implementation': 'injected_test_double' if encoder_factory else 'pinned_sentence_transformer',
                    'truncation_audit': truncation},
        'recipe': {'classifier': 'independent one-vs-rest logistic-regression heads',
                   'C': 1.0, 'max_iter': 1000, 'random_state': 42, 'threshold': 0.5,
                   'threshold_tuned': False, 'encoder_fine_tuned': False, 'all_heads_converged': True},
        'train_rows': len(partitions['train']), 'selection_rows': len(expected),
        'label_count': len(binarizer.classes_),
        'semantic_selection': metrics, 'word_baseline': word,
        'semantic_minus_word': {key: metrics[key] - word['selection'][key] for key in (
            'exact_set_accuracy', 'micro_f1', 'macro_f1', 'micro_precision', 'micro_recall',
            'hamming_loss', 'empty_prediction_fraction')},
        'calibration_read': False, 'test_payload_decoded': False, 'test_evaluated': False,
        'model_exported': False, 'live_model_changed': False,
        'limitations': word['limitations'] + [
            'Frozen pretrained-encoder training-source overlap with this public benchmark is unknown.',
            'The same C and 0.5 threshold are a controlled first comparison, not equally optimized feature-specific recipes.',
            'A whole-message embedding can lose separate intent details; this experiment does not localize requests.',
            'This is one deterministic development comparison, without repeated-seed or independent final-test evidence.',
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('benchmark_dir', type=Path)
    parser.add_argument('--cache-dir', type=Path, default=Path('artifacts/encoder-cache'))
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error('Output already exists; choose a fresh experiment file.')
    try:
        report = run(args.benchmark_dir, args.cache_dir)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open('x', encoding='utf-8', newline='\n') as handle:
            handle.write(json.dumps(report, indent=2, allow_nan=False) + '\n')
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(f'Semantic multilabel experiment failed: {error}', file=sys.stderr)
        return 1
    print(json.dumps({'semantic_selection': report['semantic_selection'],
                      'semantic_minus_word': report['semantic_minus_word'], 'test_evaluated': False}, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
