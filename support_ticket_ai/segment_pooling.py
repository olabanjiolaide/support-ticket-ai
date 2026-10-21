"""Offline heuristic segment-pooling ablation, without gold request boundaries."""

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import sys
import warnings

import numpy as np
from sklearn.exceptions import ConvergenceWarning
from sklearn.linear_model import LogisticRegression
from sklearn.multiclass import OneVsRestClassifier
from sklearn.preprocessing import MultiLabelBinarizer

from .multilabel_baseline import load_development, measure, threshold_predictions
from .resources import data_path
from .semantic_experiment import DIMENSIONS, ENCODER_ID, ENCODER_REVISION, encode, load_encoder
from .semantic_multilabel import dependency_versions, source_fingerprints

PROTOCOL_PATH = data_path('segment_pooling_protocol.json')
BOUNDARY = re.compile(r'(?:\b(?:and|also|plus|but)\b|[,;.!?\n]+)', re.I)
NAMES = ['whole', 'whole_duplicate', 'whole_segment_mean', 'whole_segment_max']
POOLING = ('Unit-normalize each mean/max pooled local vector; concatenate unit whole and local vectors divided by sqrt(2). '
           'Whole duplicate uses the same construction. Zero pooled norm falls back to whole.')
RULE = ('Only mean/max candidates with strictly higher exact-set accuracy and no lower three-intent exact accuracy '
        'than whole are eligible; rank by exact_set_accuracy, micro_f1, micro_precision, earlier representation. Otherwise retain whole.')


def segment_spans(text):
    """Partition unchanged text; delimiters stay on the preceding span, no semantics inferred."""
    if not isinstance(text, str) or not text.strip():
        raise ValueError('Expected nonempty source text.')
    ends = [match.end() for match in BOUNDARY.finditer(text) if match.end() < len(text)] + [len(text)]
    spans, start = [], 0
    for end in ends:
        if spans and len(text[start:end].split()) < 2:
            spans[-1] = (spans[-1][0], end)
        else:
            spans.append((start, end))
        start = end
    if len(spans) > 1 and len(text[slice(*spans[0])].split()) < 2:
        spans = [(0, spans[1][1])] + spans[2:]
    capped = len(spans) > 4
    if capped:
        spans = spans[:3] + [(spans[3][0], len(text))]
    return spans, capped


def validate_protocol(protocol, manifest):
    if not isinstance(protocol, dict):
        raise ValueError('Protocol must be a JSON object.')
    expected_segmenter = {'version': 1, 'boundary_regex': BOUNDARY.pattern, 'ignore_case': True,
                          'minimum_words': 2, 'maximum_segments': 4,
                          'short_fragment_policy': 'merge with previous; prefix merges with next',
                          'overflow_policy': 'merge tail; preserve all characters'}
    if (type(protocol.get('schema_version')) is not int or protocol['schema_version'] != 1 or
            protocol.get('experiment') != 'segment-pooling-v1' or protocol.get('taxonomy_id') != manifest['taxonomy_id'] or
            protocol.get('encoder_id') != ENCODER_ID or protocol.get('encoder_revision') != ENCODER_REVISION or
            protocol.get('representations') != NAMES or protocol.get('segmenter') != expected_segmenter or
            protocol.get('pooling') != POOLING or
            type(protocol.get('C')) not in (int, float) or protocol['C'] != 10 or
            protocol.get('class_weight', 'missing') is not None or
            type(protocol.get('threshold')) not in (int, float) or protocol['threshold'] != .5 or
            type(protocol.get('max_iter')) is not int or protocol['max_iter'] != 1000 or
            type(protocol.get('random_state')) is not int or protocol['random_state'] != 42 or
            protocol.get('selection_rule') != RULE):
        raise ValueError('Protocol differs from the fixed segment-pooling study.')
    expected = {name: manifest['files_sha256'][name] for name in ('train.jsonl', 'selection.jsonl')}
    if protocol.get('development_input_sha256') != expected:
        raise ValueError('Protocol input fingerprints differ from prepared development data.')


def unit_or_fallback(vector, fallback):
    norm = np.linalg.norm(vector)
    return vector / norm if norm > 1e-12 else fallback


def make_representations(whole, bags):
    whole = np.asarray(whole, dtype=np.float64)
    means = np.stack([unit_or_fallback(np.mean(bag, axis=0, dtype=np.float64), full)
                      for full, bag in zip(whole, bags)])
    maxima = np.stack([unit_or_fallback(np.max(bag, axis=0).astype(np.float64), full)
                       for full, bag in zip(whole, bags)])
    combine = lambda local: np.concatenate([whole, local], axis=1) / np.sqrt(2)
    return {'whole': whole, 'whole_duplicate': combine(whole),
            'whole_segment_mean': combine(means), 'whole_segment_max': combine(maxima)}


def encode_partition(encoder, rows, name):
    texts = [row['text'] for row in rows]
    print(f'Encoding {name} whole messages: {len(texts)}', file=sys.stderr, flush=True)
    whole = encode(encoder, texts)
    spans_and_caps = [segment_spans(text) for text in texts]
    unique, indices = [], {}
    for text, (spans, _) in zip(texts, spans_and_caps):
        if len(spans) > 1:
            for start, end in spans:
                fragment = text[start:end]
                if fragment not in indices:
                    indices[fragment] = len(unique)
                    unique.append(fragment)
    blocks = []
    for start in range(0, len(unique), 4096):
        end = min(start + 4096, len(unique))
        print(f'Encoding {name} unique segments: {start + 1}-{end}/{len(unique)}', file=sys.stderr, flush=True)
        blocks.append(encode(encoder, unique[start:end]))
    local = np.concatenate(blocks) if blocks else np.empty((0, DIMENSIONS))
    bags = [whole[i:i + 1] if len(spans) == 1 else
            local[[indices[text[start:end]] for start, end in spans]]
            for i, (text, (spans, _)) in enumerate(zip(texts, spans_and_caps))]
    audit = {'segment_count_histogram': dict(sorted(Counter(len(s) for s, _ in spans_and_caps).items())),
             'capped_rows': sum(capped for _, capped in spans_and_caps), 'unique_encoded_segments': len(unique)}
    audit['token_lengths'] = {}
    for kind, values in [('whole', texts), ('segments', unique)]:
        lengths = encoder.tokenizer(values, truncation=False, padding=False, return_length=True, verbose=False)['length'] if values else []
        audit['token_lengths'][kind] = {'rows_over_256_tokens': sum(int(n > 256) for n in lengths),
                                       'maximum_untruncated_tokens': int(max(lengths, default=0))}
    return make_representations(whole, bags), audit


def choose_representation(candidates):
    control = candidates[0]['selection']
    eligible = [i for i in (2, 3) if
                candidates[i]['selection']['exact_set_accuracy'] > control['exact_set_accuracy'] and
                candidates[i]['selection']['by_true_label_count']['3']['exact_set_accuracy'] >=
                control['by_true_label_count']['3']['exact_set_accuracy']]
    return max(eligible, key=lambda i: (candidates[i]['selection']['exact_set_accuracy'],
               candidates[i]['selection']['micro_f1'], candidates[i]['selection']['micro_precision'], -i)) if eligible else 0


def run(directory: Path, cache_dir: Path, protocol_path: Path = PROTOCOL_PATH, *, encoder_factory=None):
    manifest, partitions = load_development(directory)
    raw = protocol_path.read_bytes()
    protocol = json.loads(raw)
    validate_protocol(protocol, manifest)
    # The selection rule explicitly guards the three-label slice; require it before model work.
    if not any(len(row['labels']) == 3 for row in partitions['selection']):
        raise ValueError('Selection must contain three-label requests for the predeclared rule.')
    encoder = (encoder_factory or load_encoder)(cache_dir)
    fingerprints = source_fingerprints(cache_dir) if encoder_factory is None else None
    features, audits = {}, {}
    for split in ('train', 'selection'):
        features[split], audits[split] = encode_partition(encoder, partitions[split], split)
    binarizer = MultiLabelBinarizer(classes=manifest['label_vocabulary'])
    train_targets = binarizer.fit_transform([row['labels'] for row in partitions['train']])
    expected = binarizer.transform([row['labels'] for row in partitions['selection']])
    candidates, probabilities = [], {}
    for name in NAMES:
        print(f'Fitting representation: {name}', file=sys.stderr, flush=True)
        heads = OneVsRestClassifier(LogisticRegression(C=10., max_iter=1000, random_state=42), n_jobs=1)
        with warnings.catch_warnings():
            warnings.simplefilter('error', ConvergenceWarning)
            heads.fit(features['train'][name], train_targets)
        probabilities[name] = heads.predict_proba(features['selection'][name])
        candidates.append({'representation': name, 'dimensions': features['train'][name].shape[1],
                           'all_heads_converged': True,
                           'selection': measure(expected, threshold_predictions(probabilities[name]))})
    whole, duplicate = probabilities['whole'], probabilities['whole_duplicate']
    selected = choose_representation(candidates)
    return {'schema_version': 1, 'experiment': protocol['experiment'], 'protocol': protocol,
            'protocol_sha256': hashlib.sha256(raw).hexdigest(), 'versions': dependency_versions(),
            'dataset': manifest['dataset'], 'taxonomy_id': manifest['taxonomy_id'],
            'source_revision': manifest['source_revision'], 'train_rows': len(partitions['train']),
            'selection_rows': len(partitions['selection']), 'label_count': len(binarizer.classes_),
            'encoder': {'id': ENCODER_ID, 'revision': ENCODER_REVISION, 'frozen': True,
                        'source_file_sha256': fingerprints,
                        'implementation': 'injected_test_double' if encoder_factory else 'pinned_sentence_transformer'},
            'segmentation_audit': audits, 'candidates': candidates, 'selected_candidate_index': selected,
            'duplicate_control': {'max_absolute_score_difference': float(np.max(np.abs(whole - duplicate))),
                'rows_with_different_predicted_sets': int(np.any(threshold_predictions(whole) != threshold_predictions(duplicate), axis=1).sum())},
            'calibration_read': False, 'test_payload_decoded': False, 'test_evaluated': False,
            'threshold_tuned': False, 'encoder_fine_tuned': False, 'model_exported': False, 'live_model_changed': False,
            'limitations': [
                'A reused-development follow-up, with protocol fixed before fits; selected scores are not independent test estimates.',
                'Heuristic boundaries can split one intent or miss several; preserved offsets do not establish semantic correctness.',
                'Max pooling depends on embedding coordinates; it is an exploratory representation, not a validated intent operator.',
                'Concatenation adds feature directions; duplication checks scaling but cannot isolate all capacity effects.',
                'Segment pooling loses order and does not resolve negation, conditions, references or action relations.',
                'Banking labels, publisher noise and unknown source overlap limit transfer to the app taxonomy.',
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
        print(f'Segment-pooling study failed: {error}', file=sys.stderr)
        return 1
    print(json.dumps({'selected': report['candidates'][report['selected_candidate_index']],
                      'duplicate_control': report['duplicate_control'], 'test_evaluated': False}, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
