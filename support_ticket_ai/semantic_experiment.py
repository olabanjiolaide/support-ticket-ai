"""Compare frozen sentence embeddings with the word baseline, offline only."""

import argparse
from collections import Counter
import csv
from importlib.metadata import version
import json
from pathlib import Path
import platform
import sys
from time import perf_counter
import warnings

import numpy as np
from sklearn.exceptions import ConvergenceWarning
from sklearn.linear_model import LogisticRegression

from .abstain import CHALLENGE_PATH, CRITERIA, THRESHOLDS, load_challenge, meets_criteria
from .data import load_tickets
from .predict import TicketPredictor
from .prepare import normalize
from .robustness import PROBES_PATH, check_training_overlap, diagnostic_metrics, fingerprint, load_probes
from .scope_experiment import NEGATIVES_PATH, reject_negative_overlap
from .train import evaluate

ENCODER_ID = 'sentence-transformers/all-MiniLM-L6-v2'
ENCODER_REVISION = '1110a243fdf4706b3f48f1d95db1a4f5529b4d41'
DIMENSIONS = 384
SCOPE_CUTOFF = .5


def load_encoder(cache_dir: Path):
    try:
        import torch
        from sentence_transformers import SentenceTransformer
    except ImportError as error:
        raise ValueError('Install optional requirements-semantic.txt before running this experiment.') from error
    torch.set_num_threads(2)
    encoder = SentenceTransformer(ENCODER_ID, revision=ENCODER_REVISION, device='cpu',
                                  trust_remote_code=False, model_kwargs={'use_safetensors': True},
                                  cache_folder=str(cache_dir))
    encoder.max_seq_length = 256
    encoder.eval()
    for parameter in encoder.parameters():
        parameter.requires_grad_(False)
    return encoder


def encode(encoder, texts: list[str]) -> np.ndarray:
    values = np.asarray(encoder.encode(texts, batch_size=64, normalize_embeddings=True,
                                      convert_to_numpy=True, show_progress_bar=False))
    if values.shape != (len(texts), DIMENSIONS) or not np.isfinite(values).all():
        raise ValueError('Encoder returned invalid or unexpected embeddings.')
    if not np.allclose(np.linalg.norm(values, axis=1), 1, atol=1e-4):
        raise ValueError('Expected unit-normalized sentence embeddings.')
    return values


def scored_rows(model, features, probes: list[dict], scope_scores=None) -> list[dict]:
    rows = []
    for index, (probe, probabilities) in enumerate(zip(probes, model.predict_proba(features))):
        top = int(np.argmax(probabilities))
        row = {**probe, 'top_category': str(model.classes_[top]), 'score': float(probabilities[top])}
        if scope_scores is not None:
            row['scope_score'] = float(scope_scores[index])
        rows.append(row)
    return rows


def apply_scope(rows: list[dict]) -> list[dict]:
    # For counting acceptance only; retain original, separate scores in report cases.
    return [{**row, 'score': row['score'] if row['scope_score'] >= SCOPE_CUTOFF else 0.0} for row in rows]


def select_threshold(rows: list[dict]) -> dict:
    candidates = [diagnostic_metrics(rows, threshold) for threshold in THRESHOLDS]
    eligible = [candidate for candidate in candidates if meets_criteria(candidate)]
    selected = max(eligible, key=lambda m: (m['supported_coverage'], -m['threshold'])) if eligible else None
    return {'candidates': candidates, 'selected_threshold': selected['threshold'] if selected else None}


def summarize_policy(rows: list[dict], threshold: float | None) -> dict:
    # None means selection failed, never silently fall back to forced suggestions.
    if threshold is None:
        return {'policy_selected': False, 'metrics': None, 'by_slice': {}}
    return {'policy_selected': True, 'metrics': diagnostic_metrics(rows, threshold),
            'by_slice': {name: diagnostic_metrics([r for r in rows if r['slice'] == name], threshold)
                         for name in sorted({r['slice'] for r in rows if 'slice' in r})}}


def latency(function, texts: list[str]) -> dict:
    function(texts[0])  # Warm-up excluded; model download/load is excluded too.
    times = []
    for text in texts[:20]:
        start = perf_counter()
        function(text)
        times.append((perf_counter() - start) * 1000)
    return {'requests': len(times), 'median_ms': float(np.median(times)),
            'p95_ms': float(np.percentile(times, 95)), 'batch_size': 1,
            'includes': 'local feature extraction/encoding and category predict_proba; no HTTP or scope head'}


def run_experiment(model_dir: Path, prepared_dir: Path, cache_dir: Path,
                   probes_path: Path = PROBES_PATH, challenge_path: Path = CHALLENGE_PATH,
                   negatives_path: Path = NEGATIVES_PATH, *, encoder_factory=None) -> dict:
    baseline = TicketPredictor(model_dir)
    categories = set(baseline.model.classes_)
    probes = load_probes(probes_path, categories)
    challenge = load_challenge(challenge_path, categories)
    negatives = load_probes(negatives_path, categories)
    reject_negative_overlap(negatives, probes + challenge)
    overlap = check_training_overlap(prepared_dir, baseline.metadata, probes + negatives, categories)
    if overlap['exact_overlap_rows']:
        raise ValueError('Development data overlaps normalized training text.')
    challenge_overlap = check_training_overlap(prepared_dir, baseline.metadata, challenge, categories)
    excluded_ids = set(challenge_overlap['exact_overlap_case_ids'])
    challenge = [row for row in challenge if row['case_id'] not in excluded_ids]
    for split in ('selection', 'audit'):
        labels = {row['expected_category'] for row in challenge if row['split'] == split}
        if 'UNSUPPORTED' not in labels or not labels.intersection(categories):
            raise ValueError('Training-overlap exclusion leaves an invalid challenge partition.')
    manifest = json.loads((prepared_dir / 'manifest.json').read_text(encoding='utf-8'))
    records = {}
    for split in ('train', 'validation'):
        path = prepared_dir / f'{split}.csv'
        if fingerprint(path) != manifest['split_sha256'][split]:
            raise ValueError(f'Checksum mismatch: {split}.')
        records[split] = load_tickets(path, categories=frozenset(categories))
        if {row.category for row in records[split]} != categories:
            raise ValueError(f'Missing category in {split}.')
    train, validation = records['train'], records['validation']
    if ({r.ticket_id for r in train} & {r.ticket_id for r in validation} or
            {normalize(r.text) for r in train} & {normalize(r.text) for r in validation}):
        raise ValueError('Training/validation overlap.')
    start = perf_counter()
    encoder = (encoder_factory or load_encoder)(cache_dir)
    load_seconds = perf_counter() - start
    texts = {'train': [r.text for r in train], 'validation': [r.text for r in validation],
             'probes': [r['text'] for r in probes], 'challenge': [r['text'] for r in challenge],
             'negatives': [r['text'] for r in negatives]}
    embeddings, encode_seconds = {}, {}
    for name, values in texts.items():
        if encoder_factory is None:
            print(f'Encoding {name}: {len(values)} texts', file=sys.stderr, flush=True)
        start = perf_counter()
        embeddings[name] = encode(encoder, values)
        encode_seconds[name] = perf_counter() - start
    category = LogisticRegression(C=1.0, max_iter=1000, random_state=manifest['seed'])
    scope = LogisticRegression(C=1.0, max_iter=1000, random_state=manifest['seed'], class_weight='balanced')
    with warnings.catch_warnings():
        warnings.simplefilter('error', ConvergenceWarning)
        category.fit(embeddings['train'], [r.category for r in train])
        scope.fit(np.concatenate([embeddings['train'], embeddings['negatives']]),
                  ['SUPPORTED'] * len(train) + ['UNSUPPORTED'] * len(negatives))
    support_index = list(scope.classes_).index('SUPPORTED')
    results = {}
    for name, model in [('word', baseline.model), ('semantic', category)]:
        probe_features = texts['probes'] if name == 'word' else embeddings['probes']
        challenge_features = texts['challenge'] if name == 'word' else embeddings['challenge']
        val_features = texts['validation'] if name == 'word' else embeddings['validation']
        probe_rows = scored_rows(model, probe_features, probes,
                                 scope.predict_proba(embeddings['probes'])[:, support_index] if name == 'semantic' else None)
        challenge_rows = scored_rows(model, challenge_features, challenge,
                                     scope.predict_proba(embeddings['challenge'])[:, support_index] if name == 'semantic' else None)
        variants = [('category_only', probe_rows, challenge_rows)]
        if name == 'semantic':
            variants.append(('with_scope', apply_scope(probe_rows), apply_scope(challenge_rows)))
        policies = {}
        for policy_name, p_rows, c_rows in variants:
            selection = select_threshold([r for r in c_rows if r['split'] == 'selection'])
            threshold = selection['selected_threshold']
            policies[policy_name] = {'selection': selection,
                                    'previously_inspected_audit': summarize_policy([r for r in c_rows if r['split'] == 'audit'], threshold),
                                    'broader_development_probes': summarize_policy(p_rows, threshold)}
        predict_one = (lambda text: model.predict_proba([text])) if name == 'word' else (lambda text: model.predict_proba(encode(encoder, [text])))
        results[name] = {
            'validation': evaluate([r.category for r in validation], model.predict(val_features), sorted(categories)),
            'forced_supported_probe_metrics': diagnostic_metrics(probe_rows, None),
            'fixed_070_probe_diagnostic': diagnostic_metrics(probe_rows, .7),
            'policies': policies, 'probe_cases': probe_rows, 'challenge_cases': challenge_rows,
            'latency': latency(predict_one, texts['probes']),
        }
    packages = ['scikit-learn', 'numpy', 'scipy', 'joblib']
    if encoder_factory is None:
        packages += ['sentence-transformers', 'transformers', 'torch', 'huggingface-hub', 'tokenizers', 'safetensors']
    return {
        'experiment': 'frozen_sentence_embeddings_category_and_scope',
        'test_evaluated': False, 'live_model_changed': False, 'candidate_bundle_exported': False,
        'encoder_fine_tuned': False, 'policy_installed': False,
        'encoder': {'id': ENCODER_ID, 'revision': ENCODER_REVISION, 'dimensions': DIMENSIONS,
                    'normalize_embeddings': True, 'max_sequence_length_wordpieces': 256,
                    'device': 'cpu', 'torch_threads': 2, 'batch_size': 64,
                    'test_double_used': encoder_factory is not None},
        'seed': manifest['seed'], 'category_head': {'C': 1.0, 'max_iter': 1000, 'class_weight': None},
        'scope_head': {'C': 1.0, 'max_iter': 1000, 'class_weight': 'balanced', 'scope_cutoff': SCOPE_CUTOFF},
        'training_counts': {'supported': len(train), 'unsupported': len(negatives)},
        'selection_criteria': CRITERIA, 'candidate_category_thresholds': THRESHOLDS,
        'threshold_selection_partition': 'existing_challenge_selection_only',
        'probe_label_status_counts': dict(Counter(r['label_status'] for r in probes)),
        'baseline_model_sha256': baseline.metadata['model_sha256'],
        'preparation_manifest_sha256': fingerprint(prepared_dir / 'manifest.json'),
        'probes_sha256': fingerprint(probes_path), 'challenge_sha256': fingerprint(challenge_path),
        'negatives_sha256': fingerprint(negatives_path), 'training_overlap': overlap,
        'challenge_training_overlap_before_exclusion': challenge_overlap,
        'excluded_challenge_case_ids': sorted(excluded_ids),
        'retained_challenge_partition_counts': dict(Counter(r['split'] for r in challenge)),
        'versions': {'python': platform.python_version(), **{p: version(p) for p in packages}},
        'timing': {'encoder_load_seconds': load_seconds, 'encoding_seconds_by_partition': encode_seconds,
                   'platform': platform.platform(), 'processor': platform.processor()},
        'models': results,
        'limitations': [
            'Previously inspected authored development data with provisional labels, not independent evaluation.',
            'Negative examples target known failure families; semantic/template overlap can inflate scope results.',
            'Threshold selection excludes audit/regression/probe rows and exact training duplicates; the existing audit is previously inspected.',
            'No eligible cutoff means no policy selected; do not lower criteria after inspecting results.',
            'A fixed 0.70 comparison is diagnostic only; model scores are not calibrated or matched risk.',
            'Frozen pretrained embeddings do not establish task understanding, scope reliability, or multi-intent handling.',
            'Inputs beyond 256 wordpieces are truncated; token truncation counts are not measured.',
            'Pretraining overlap with downstream data has not been independently audited.',
            'CPU timing is a small sequential warm local measurement, not HTTP/load/concurrency performance.',
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('model_dir', type=Path)
    parser.add_argument('prepared_dir', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--cache-dir', type=Path, default=Path('artifacts/encoder-cache'))
    args = parser.parse_args()
    try:
        if args.output.exists():
            raise ValueError('Report already exists; choose a new filename.')
        report = run_experiment(args.model_dir, args.prepared_dir, args.cache_dir)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open('x', encoding='utf-8') as handle:
            json.dump(report, handle, indent=2)
            handle.write('\n')
    except (OSError, ValueError, KeyError, UnicodeError, csv.Error, ConvergenceWarning) as error:
        print(f'Error: {error}', file=sys.stderr)
        return 1
    print(json.dumps({name: {
        'validation_macro_f1': model['validation']['macro_f1'],
        'forced_supported_accuracy': model['forced_supported_probe_metrics']['selected_supported_accuracy'],
        'policies': {policy: {'selected_threshold': result['selection']['selected_threshold'],
                             'broader_probe_metrics': result['broader_development_probes']['metrics']}
                     for policy, result in model['policies'].items()},
        'latency': model['latency'],
    } for name, model in report['models'].items()}, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
