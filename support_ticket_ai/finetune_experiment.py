"""Offline CPU pilot: compare a frozen encoder with one train-only adaptation run."""

import argparse
from collections import Counter
import csv
import hashlib
from importlib.metadata import version
import json
from pathlib import Path
import platform
import random
import sys
from time import perf_counter
import warnings

import numpy as np
from sklearn.exceptions import ConvergenceWarning
from sklearn.linear_model import LogisticRegression

from .data import load_tickets
from .prepare import normalize
from .robustness import PROBES_PATH, diagnostic_metrics, fingerprint, load_probes
from .scope_experiment import NEGATIVES_PATH
from .semantic_experiment import (DIMENSIONS, ENCODER_ID, ENCODER_REVISION,
                                  apply_scope, encode, load_encoder, scored_rows)
from .train import evaluate

# One declared recipe, not a sweep selected using the inspected probes.
RECIPE = {'seed': 42, 'per_class': 128, 'epochs': 1, 'batch_size': 16,
          'encoder_learning_rate': 2e-5, 'temporary_head_learning_rate': 1e-3,
          'weight_decay': .01, 'gradient_clip_norm': 1.0, 'logit_scale': 20.0,
          'category_cutoff': .5, 'scope_cutoff': .5}


def training_subset(records, per_class: int, seed: int):
    """Stable balanced cap from train only, independent of CSV row ordering."""
    if type(per_class) is not int or per_class < 1:
        raise ValueError('per_class must be a positive integer.')
    selected = []
    for label in sorted({r.category for r in records}):
        candidates = [r for r in records if r.category == label]
        candidates.sort(key=lambda r: hashlib.sha256(
            f'{seed}\0{r.ticket_id}\0{normalize(r.text)}'.encode()).hexdigest())
        selected.extend(candidates[:per_class])
    return selected


def load_inputs(prepared_dir: Path, probes_path: Path, negatives_path: Path):
    manifest = json.loads((prepared_dir / 'manifest.json').read_text(encoding='utf-8'))
    categories = sorted(manifest['audit']['categories'])
    if len(categories) < 2 or len(set(categories)) != len(categories):
        raise ValueError('Manifest requires distinct categories.')
    records = {}
    # test.csv is deliberately never opened, checked, or hashed.
    for split in ('train', 'validation'):
        path = prepared_dir / f'{split}.csv'
        if fingerprint(path) != manifest['split_sha256'][split]:
            raise ValueError(f'Checksum mismatch: {split}.')
        records[split] = load_tickets(path, categories=frozenset(categories))
        if {r.category for r in records[split]} != set(categories):
            raise ValueError(f'Missing category in {split}.')
    train, validation = records['train'], records['validation']
    if ({r.ticket_id for r in train} & {r.ticket_id for r in validation} or
            {normalize(r.text) for r in train} & {normalize(r.text) for r in validation}):
        raise ValueError('Training/validation overlap.')
    probes = load_probes(probes_path, set(categories))
    negatives = load_probes(negatives_path, set(categories))
    if any(r['expected_category'] != 'UNSUPPORTED' for r in negatives):
        raise ValueError('Scope training negatives must all be UNSUPPORTED.')
    partitions = {
        'train': {normalize(r.text) for r in train},
        'validation': {normalize(r.text) for r in validation},
        'probes': {normalize(r['text']) for r in probes},
        'negatives': {normalize(r['text']) for r in negatives},
    }
    names = list(partitions)
    for index, first in enumerate(names):
        for second in names[index + 1:]:
            if partitions[first] & partitions[second]:
                raise ValueError(f'Normalized text overlap: {first}/{second}.')
    return manifest, categories, train, validation, probes, negatives


def encoder_fingerprint(encoder) -> str:
    """Hash actual parameter/buffer contents, not timestamps or checkpoint metadata."""
    digest = hashlib.sha256()
    for name, tensor in sorted(encoder.state_dict().items()):
        array = tensor.detach().cpu().contiguous().numpy()
        digest.update(name.encode() + b'\0' + str(array.dtype).encode() + b'\0')
        digest.update(str(array.shape).encode() + b'\0' + array.tobytes())
    return digest.hexdigest()


def fine_tune_encoder(encoder, records, categories: list[str], recipe: dict) -> dict:
    # Import only for this optional experiment; core API/tests need no Torch.
    import torch
    from torch import nn

    random.seed(recipe['seed'])
    np.random.seed(recipe['seed'])
    torch.manual_seed(recipe['seed'])
    torch.set_num_threads(2)
    previous_determinism = torch.are_deterministic_algorithms_enabled()
    torch.use_deterministic_algorithms(True)
    encoder.to('cpu')
    parameters = list(encoder.parameters())
    for parameter in parameters:
        parameter.requires_grad_(True)
    head = nn.Linear(DIMENSIONS, len(categories))
    optimizer = torch.optim.AdamW([
        {'params': parameters, 'lr': recipe['encoder_learning_rate']},
        {'params': head.parameters(), 'lr': recipe['temporary_head_learning_rate']},
    ], weight_decay=recipe['weight_decay'])
    labels = {label: i for i, label in enumerate(categories)}
    generator = torch.Generator().manual_seed(recipe['seed'])
    losses, steps = [], 0
    start = perf_counter()
    try:
        encoder.train()
        head.train()
        for epoch in range(recipe['epochs']):
            total, count = 0.0, 0
            order = torch.randperm(len(records), generator=generator).tolist()
            for offset in range(0, len(order), recipe['batch_size']):
                batch = [records[i] for i in order[offset:offset + recipe['batch_size']]]
                features = {key: value.to('cpu') for key, value in
                            encoder.tokenize([r.text for r in batch]).items()}
                optimizer.zero_grad(set_to_none=True)
                # encode() disables autograd; use the differentiable forward pass.
                embeddings = encoder(features)['sentence_embedding']
                embeddings = nn.functional.normalize(embeddings, dim=1)
                logits = head(embeddings) * recipe['logit_scale']
                targets = torch.tensor([labels[r.category] for r in batch], dtype=torch.long)
                loss = nn.functional.cross_entropy(logits, targets)
                if not torch.isfinite(loss):
                    raise ValueError('Nonfinite fine-tuning loss.')
                loss.backward()
                nn.utils.clip_grad_norm_(parameters + list(head.parameters()),
                                         recipe['gradient_clip_norm'], error_if_nonfinite=True)
                optimizer.step()
                total += float(loss.detach()) * len(batch)
                count += len(batch)
                steps += 1
                if steps % 20 == 0:
                    print(f'Fine-tuning step {steps}; training loss {total / count:.4f}', flush=True)
            losses.append(total / count)
    finally:
        encoder.eval()
        for parameter in parameters:
            parameter.requires_grad_(False)
        torch.use_deterministic_algorithms(previous_determinism)
    return {'epoch_mean_training_cross_entropy': losses, 'optimizer_steps': steps,
            'seconds': perf_counter() - start, 'temporary_head_discarded': True,
            'trainable_encoder_parameters': sum(p.numel() for p in parameters)}


def evaluate_encoder(encoder, train, validation, probes, negatives, categories, recipe):
    texts = {'train': [r.text for r in train], 'validation': [r.text for r in validation],
             'probes': [r['text'] for r in probes], 'negatives': [r['text'] for r in negatives]}
    embeddings = {}
    for name, values in texts.items():
        print(f'Encoding {name}: {len(values)}', flush=True)
        embeddings[name] = encode(encoder, values)
    category = LogisticRegression(C=1.0, max_iter=1000, random_state=recipe['seed'])
    scope = LogisticRegression(C=1.0, max_iter=1000, random_state=recipe['seed'], class_weight='balanced')
    with warnings.catch_warnings():
        warnings.simplefilter('error', ConvergenceWarning)
        category.fit(embeddings['train'], [r.category for r in train])
        scope.fit(np.concatenate([embeddings['train'], embeddings['negatives']]),
                  ['SUPPORTED'] * len(train) + ['UNSUPPORTED'] * len(negatives))
    scope_index = list(scope.classes_).index('SUPPORTED')
    rows = scored_rows(category, embeddings['probes'], probes,
                       scope.predict_proba(embeddings['probes'])[:, scope_index])
    supported = [r for r in rows if r['expected_category'] in categories]
    forced = evaluate([r['expected_category'] for r in supported],
                      [r['top_category'] for r in supported], categories) if supported else None
    return {
        'synthetic_validation': evaluate([r.category for r in validation],
                                          category.predict(embeddings['validation']), categories),
        'development_supported_forced': forced,
        'development_category_cutoff': diagnostic_metrics(rows, recipe['category_cutoff']),
        'development_with_scope': diagnostic_metrics(apply_scope(rows), recipe['category_cutoff']),
        'cases': [{**r, 'accepted_with_scope': r['score'] >= recipe['category_cutoff'] and
                  r['scope_score'] >= recipe['scope_cutoff']} for r in rows],
    }


def run_experiment(prepared_dir: Path, cache_dir: Path, *, probes_path=PROBES_PATH,
                   negatives_path=NEGATIVES_PATH, encoder_factory=None, trainer=None) -> dict:
    manifest, categories, train, validation, probes, negatives = load_inputs(
        prepared_dir, probes_path, negatives_path)
    recipe = dict(RECIPE)
    subset = training_subset(train, recipe['per_class'], recipe['seed'])
    encoder = (encoder_factory or load_encoder)(cache_dir)
    before = encoder_fingerprint(encoder)
    print('Evaluating frozen encoder', flush=True)
    frozen = evaluate_encoder(encoder, train, validation, probes, negatives, categories, recipe)
    training = (trainer or fine_tune_encoder)(encoder, subset, categories, recipe)
    after = encoder_fingerprint(encoder)
    if before == after:
        raise ValueError('Fine-tuning did not change encoder parameters.')
    print('Evaluating fine-tuned encoder', flush=True)
    tuned = evaluate_encoder(encoder, train, validation, probes, negatives, categories, recipe)
    changed_cases = [{
        'case_id': a['case_id'], 'text': a['text'], 'expected_category': a['expected_category'],
        'frozen_category': a['top_category'], 'fine_tuned_category': b['top_category'],
        'frozen_accepted': a['accepted_with_scope'], 'fine_tuned_accepted': b['accepted_with_scope'],
    } for a, b in zip(frozen['cases'], tuned['cases']) if
        a['top_category'] != b['top_category'] or a['accepted_with_scope'] != b['accepted_with_scope']]
    packages = ('scikit-learn', 'numpy', 'scipy', 'joblib')
    test_double = encoder_factory is not None or trainer is not None
    if not test_double:
        packages += ('torch', 'sentence-transformers', 'transformers', 'huggingface-hub', 'tokenizers', 'safetensors')
    return {
        'experiment': 'train_only_supervised_encoder_fine_tuning_pilot', 'recipe': recipe,
        'test_evaluated': False, 'live_model_changed': False, 'candidate_bundle_exported': False,
        'encoder_fine_tuned': not test_double, 'test_double_used': test_double,
        'threshold_selection_performed': False, 'checkpoint_selection_performed': False,
        'encoder': {'id': ENCODER_ID, 'revision': ENCODER_REVISION, 'dimensions': DIMENSIONS,
                    'max_sequence_length_wordpieces': 256, 'device': 'cpu',
                    'before_state_sha256': before, 'after_state_sha256': after},
        'source_revision': manifest['source_revision'],
        'input_sha256': {'manifest': fingerprint(prepared_dir / 'manifest.json'),
                        'train': fingerprint(prepared_dir / 'train.csv'),
                        'validation': fingerprint(prepared_dir / 'validation.csv'),
                        'probes': fingerprint(probes_path), 'negatives': fingerprint(negatives_path)},
        'fine_tuning_counts': dict(Counter(r.category for r in subset)),
        'fine_tuning_ticket_ids': [r.ticket_id for r in subset],
        'head_training_counts': dict(Counter(r.category for r in train)),
        'scope_negative_training_rows': len(negatives), 'training': training,
        'models': {'frozen': frozen, 'fine_tuned': tuned}, 'changed_development_cases': changed_cases,
        'versions': {'python': platform.python_version(), **{p: version(p) for p in packages}},
        'limitations': [
            'One seed and one small fixed recipe; not an optimized or independently validated model.',
            'Fine-tuning updates encoder weights using only the balanced training subset and category labels.',
            'Both representations get newly fitted identical logistic category/scope recipes on full train plus scope negatives.',
            'Validation is synthetic and may share templates with train; exact overlap checks do not remove template overlap.',
            'Existing authored probes have provisional labels and were previously inspected; regression diagnostics only.',
            'No labels from manual review are read. Test CSV is never opened. No new independent evidence is claimed.',
            'Fixed uncalibrated cutoffs need not have the same coverage or error rate across representations.',
            'Multiple-intent detection is not trained; scope negatives teach only the supported/unsupported distinction.',
            'Encoder inputs truncate at 256 wordpieces; this pilot does not implement the live truncation abstention guard.',
            'Training loss is not a quality metric. No checkpoint is selected, exported, or promoted to the browser.',
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('prepared_dir', type=Path)
    parser.add_argument('output', type=Path, help='New report JSON; does not export a serving bundle')
    parser.add_argument('--cache-dir', type=Path, default=Path('artifacts/encoder-cache'))
    args = parser.parse_args()
    try:
        # Reserve before expensive work; remove our incomplete report on failure.
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
    print(json.dumps({name: {'validation_macro_f1': result['synthetic_validation']['macro_f1'],
                            'development_with_scope': result['development_with_scope']}
                      for name, result in report['models'].items()}, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
