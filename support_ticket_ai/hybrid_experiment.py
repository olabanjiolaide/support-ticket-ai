"""Offline spelling pilot: frozen sentence embeddings plus character n-grams."""

import argparse
import csv
import hashlib
from importlib.metadata import version
import json
from pathlib import Path
import platform
import sys
from time import perf_counter
import warnings

import numpy as np
from scipy import sparse
from sklearn.exceptions import ConvergenceWarning
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import normalize

from .compare_features import CHARACTER_CONFIG
from .finetune_experiment import load_inputs
from .robustness import PROBES_PATH, diagnostic_metrics, fingerprint
from .scope_experiment import NEGATIVES_PATH
from .semantic_experiment import (DIMENSIONS, ENCODER_ID, ENCODER_REVISION,
                                  apply_scope, encode, load_encoder, scored_rows)
from .train import evaluate

CATEGORY_CUTOFF = .5
SCOPE_CUTOFF = .5


def combine_features(embeddings: np.ndarray, characters):
    """Equal normalized blocks; keep the joint matrix sparse and unit length."""
    if (embeddings.ndim != 2 or embeddings.shape[1] != DIMENSIONS or
            embeddings.shape[0] != characters.shape[0] or not np.isfinite(embeddings).all() or
            not np.isfinite(characters.data).all()):
        raise ValueError('Invalid or misaligned hybrid features.')
    return normalize(sparse.hstack([sparse.csr_matrix(embeddings), characters], format='csr'),
                     norm='l2', copy=False)


def summarize(model, validation_features, validation, probe_features, probes, scope_scores, categories):
    rows = scored_rows(model, probe_features, probes, scope_scores)
    supported = [r for r in rows if r['expected_category'] in categories]
    return {
        'synthetic_validation': evaluate([r.category for r in validation],
                                          model.predict(validation_features), categories),
        'development_supported_forced': evaluate([r['expected_category'] for r in supported],
                                                [r['top_category'] for r in supported], categories) if supported else None,
        'development_category_cutoff': diagnostic_metrics(rows, CATEGORY_CUTOFF),
        'development_with_scope': diagnostic_metrics(apply_scope(rows), CATEGORY_CUTOFF),
        'development_by_slice': {
            name: {'forced': diagnostic_metrics([r for r in rows if r['slice'] == name], None),
                   'with_scope': diagnostic_metrics(apply_scope([r for r in rows if r['slice'] == name]), CATEGORY_CUTOFF)}
            for name in sorted({r['slice'] for r in rows})},
        'cases': [{**r, 'accepted_with_scope': r['score'] >= CATEGORY_CUTOFF and
                  r['scope_score'] >= SCOPE_CUTOFF} for r in rows],
    }


def run_experiment(prepared_dir: Path, cache_dir: Path, *, probes_path=PROBES_PATH,
                   negatives_path=NEGATIVES_PATH, encoder_factory=None) -> dict:
    manifest, categories, train, validation, probes, negatives = load_inputs(
        prepared_dir, probes_path, negatives_path)
    seed = manifest['seed']
    texts = {'train': [r.text for r in train], 'validation': [r.text for r in validation],
             'probes': [r['text'] for r in probes], 'negatives': [r['text'] for r in negatives]}
    encoder = (encoder_factory or load_encoder)(cache_dir)
    start = perf_counter()
    embeddings = {}
    for name, values in texts.items():
        print(f'Encoding {name}: {len(values)}', flush=True)
        embeddings[name] = encode(encoder, values)
    encoding_seconds = perf_counter() - start
    config = {**CHARACTER_CONFIG, 'ngram_range': tuple(CHARACTER_CONFIG['ngram_range'])}
    vectorizer = TfidfVectorizer(**config)
    # No validation/probe/negative request can contribute vocabulary or IDF.
    characters = {'train': vectorizer.fit_transform(texts['train'])}
    for name in ('validation', 'probes'):
        characters[name] = vectorizer.transform(texts[name])
    joint = {name: combine_features(embeddings[name], characters[name])
             for name in ('train', 'validation', 'probes')}
    category = LogisticRegression(C=1.0, max_iter=1000, random_state=seed)
    hybrid = LogisticRegression(C=1.0, max_iter=1000, random_state=seed)
    scope = LogisticRegression(C=1.0, max_iter=1000, random_state=seed, class_weight='balanced')
    print('Fitting category heads and shared semantic scope head', flush=True)
    start = perf_counter()
    with warnings.catch_warnings():
        warnings.simplefilter('error', ConvergenceWarning)
        targets = [r.category for r in train]
        category.fit(embeddings['train'], targets)
        hybrid.fit(joint['train'], targets)
        scope.fit(np.concatenate([embeddings['train'], embeddings['negatives']]),
                  ['SUPPORTED'] * len(train) + ['UNSUPPORTED'] * len(negatives))
    fit_seconds = perf_counter() - start
    scope_scores = scope.predict_proba(embeddings['probes'])[:, list(scope.classes_).index('SUPPORTED')]
    results = {}
    for name, head, features in [('semantic', category, embeddings), ('hybrid', hybrid, joint)]:
        results[name] = summarize(head, features['validation'], validation, features['probes'],
                                   probes, scope_scores, categories)
    vocabulary_json = json.dumps(sorted(vectorizer.vocabulary_), ensure_ascii=False, separators=(',', ':'))
    packages = ('scikit-learn', 'numpy', 'scipy', 'joblib')
    if encoder_factory is None:
        packages += ('torch', 'sentence-transformers', 'transformers', 'huggingface-hub', 'tokenizers', 'safetensors')
    return {
        'experiment': 'frozen_semantic_plus_character_spelling_pilot',
        'test_evaluated': False, 'encoder_fine_tuned': False, 'live_model_changed': False,
        'candidate_bundle_exported': False, 'threshold_selection_performed': False,
        'test_double_used': encoder_factory is not None,
        'encoder': {'id': ENCODER_ID, 'revision': ENCODER_REVISION, 'dimensions': DIMENSIONS,
                    'max_sequence_length_wordpieces': 256, 'device': 'cpu'},
        'configuration': {'seed': seed, 'characters': CHARACTER_CONFIG,
                          'combination': 'Unit-length semantic and character blocks, concatenated then L2-normalized',
                          'category_head': {'C': 1, 'max_iter': 1000},
                          'scope_head': {'C': 1, 'max_iter': 1000, 'class_weight': 'balanced',
                                         'shared_between_candidates': True, 'features': 'frozen semantic only'},
                          'category_cutoff': CATEGORY_CUTOFF, 'scope_cutoff': SCOPE_CUTOFF},
        'character_vocabulary_size': len(vectorizer.vocabulary_),
        'character_vocabulary_sha256': hashlib.sha256(vocabulary_json.encode()).hexdigest(),
        'hybrid_dimensions': joint['train'].shape[1],
        'input_sha256': {'manifest': fingerprint(prepared_dir / 'manifest.json'),
                        'train': fingerprint(prepared_dir / 'train.csv'),
                        'validation': fingerprint(prepared_dir / 'validation.csv'),
                        'probes': fingerprint(probes_path), 'negatives': fingerprint(negatives_path)},
        'source_revision': manifest['source_revision'],
        'partition_counts': {name: len(values) for name, values in texts.items()},
        'timing_seconds': {'encoding': encoding_seconds, 'fit_all_heads': fit_seconds},
        'versions': {'python': platform.python_version(), **{p: version(p) for p in packages}},
        'models': results,
        'limitations': [
            'One fixed spelling-feature recipe, not a parameter sweep or a selected serving model.',
            'Existing authored stress cases have provisional labels and were previously inspected; development diagnostics only.',
            'Synthetic validation may share templates with train; exact text and ID separation does not remove template leakage.',
            'Shared scope scores isolate category-feature changes; this does not improve the scope detector itself.',
            'Character vocabulary and IDF fit train only. No manual-review labels are read. Test CSV is never opened.',
            'Equal numeric uncalibrated cutoffs need not mean equal risk or coverage.',
            'No spelling correction or text rewriting occurs; original request intent is preserved at input.',
            'Multiple-intent detection is not trained by concatenating features.',
            'Encoder inputs truncate at 256 wordpieces; live truncation guards and HTTP latency are not reproduced.',
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('prepared_dir', type=Path)
    parser.add_argument('output', type=Path, help='New JSON report; no serving bundle is exported')
    parser.add_argument('--cache-dir', type=Path, default=Path('artifacts/encoder-cache'))
    args = parser.parse_args()
    try:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open('x', encoding='utf-8') as handle:
            try:
                report = run_experiment(args.prepared_dir, args.cache_dir)
                json.dump(report, handle, indent=2, allow_nan=False)
                handle.write('\n')
            except BaseException:
                handle.close()
                args.output.unlink(missing_ok=True)
                raise
    except (OSError, ValueError, KeyError, ImportError, UnicodeError, csv.Error, ConvergenceWarning) as error:
        print(f'Error: {error}', file=sys.stderr)
        return 1
    print(json.dumps({name: {'supported_macro_f1': result['development_supported_forced']['macro_f1']
                            if result['development_supported_forced'] else None,
                            'with_scope': result['development_with_scope']}
                      for name, result in report['models'].items()}, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
