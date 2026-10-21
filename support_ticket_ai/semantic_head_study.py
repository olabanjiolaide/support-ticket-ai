"""Six predeclared semantic classifier fits; development selection, no test scoring."""

import argparse
import hashlib
import json
from pathlib import Path
import sys
import warnings

from sklearn.exceptions import ConvergenceWarning
from sklearn.linear_model import LogisticRegression
from sklearn.multiclass import OneVsRestClassifier
from sklearn.preprocessing import MultiLabelBinarizer

from .multilabel_baseline import load_development, measure, threshold_predictions
from .resources import data_path
from .semantic_experiment import DIMENSIONS, ENCODER_ID, ENCODER_REVISION, encode, load_encoder
from .semantic_multilabel import dependency_versions, source_fingerprints

PROTOCOL_PATH = data_path('semantic_head_protocol.json')
CANDIDATES = [{'C': c, 'class_weight': w} for c in (.1, 1., 10.) for w in (None, 'balanced')]
SELECTION_RULE = 'exact_set_accuracy, micro_f1, micro_precision, then earlier candidate'


def validate_protocol(protocol, manifest):
    if not isinstance(protocol, dict):
        raise ValueError('Protocol must be a JSON object.')
    if (type(protocol.get('schema_version')) is not int or protocol['schema_version'] != 1 or
            protocol.get('experiment') != 'semantic-head-study-v1' or
            protocol.get('taxonomy_id') != manifest['taxonomy_id'] or
            protocol.get('encoder_id') != ENCODER_ID or protocol.get('encoder_revision') != ENCODER_REVISION or
            type(protocol.get('threshold')) not in (int, float) or protocol['threshold'] != .5 or
            type(protocol.get('max_iter')) is not int or protocol['max_iter'] != 1000 or
            type(protocol.get('random_state')) is not int or protocol['random_state'] != 42 or
            protocol.get('selection_rule') != SELECTION_RULE or protocol.get('candidates') != CANDIDATES):
        raise ValueError('Protocol differs from the fixed six-candidate study.')
    for candidate in protocol['candidates']:
        if type(candidate['C']) not in (int, float):
            raise ValueError('Candidate C must be numeric, not boolean.')
    expected = {name: manifest['files_sha256'][name] for name in ('train.jsonl', 'selection.jsonl')}
    if protocol.get('development_input_sha256') != expected:
        raise ValueError('Protocol input fingerprints do not match prepared development data.')


def select_candidate(candidates):
    if not candidates:
        raise ValueError('No candidate results.')
    return max(range(len(candidates)), key=lambda index: (
        candidates[index]['selection']['exact_set_accuracy'],
        candidates[index]['selection']['micro_f1'],
        candidates[index]['selection']['micro_precision'], -index))


def fit_candidates(train_features, train_targets, selection_features, selection_targets, protocol):
    results = []
    for index, setting in enumerate(protocol['candidates']):
        print(f"Fitting candidate {index + 1}/6: C={setting['C']}, weight={setting['class_weight']}",
              file=sys.stderr, flush=True)
        heads = OneVsRestClassifier(LogisticRegression(
            C=setting['C'], class_weight=setting['class_weight'], max_iter=1000, random_state=42), n_jobs=1)
        with warnings.catch_warnings():
            warnings.simplefilter('error', ConvergenceWarning)
            heads.fit(train_features, train_targets)
        predicted = threshold_predictions(heads.predict_proba(selection_features))
        results.append({'candidate_index': index, **setting, 'threshold': .5,
                        'all_heads_converged': True, 'selection': measure(selection_targets, predicted)})
    return results


def run(directory: Path, cache_dir: Path, protocol_path: Path = PROTOCOL_PATH, *, encoder_factory=None):
    manifest, partitions = load_development(directory)
    protocol_raw = protocol_path.read_bytes()
    protocol = json.loads(protocol_raw)
    validate_protocol(protocol, manifest)  # No encoder loading/fitting on mismatched data.
    encoder = (encoder_factory or load_encoder)(cache_dir)
    fingerprints = source_fingerprints(cache_dir) if encoder_factory is None else None
    features, truncation = {}, {}
    for split in ('train', 'selection'):
        texts = [row['text'] for row in partitions[split]]
        print(f'Encoding {split}: {len(texts)} requests once for all candidates', file=sys.stderr, flush=True)
        lengths = encoder.tokenizer(texts, truncation=False, padding=False, return_length=True, verbose=False)['length']
        truncation[split] = {'rows_over_256_tokens': sum(int(n > 256) for n in lengths),
                             'maximum_untruncated_tokens': int(max(lengths))}
        features[split] = encode(encoder, texts)
    binarizer = MultiLabelBinarizer(classes=manifest['label_vocabulary'])
    train_targets = binarizer.fit_transform([row['labels'] for row in partitions['train']])
    selection_targets = binarizer.transform([row['labels'] for row in partitions['selection']])
    candidates = fit_candidates(features['train'], train_targets, features['selection'], selection_targets, protocol)
    selected_index = select_candidate(candidates)
    control_index = next(i for i, candidate in enumerate(candidates) if candidate['C'] == 1 and candidate['class_weight'] is None)
    best, control = candidates[selected_index]['selection'], candidates[control_index]['selection']
    return {
        'schema_version': 1, 'experiment': protocol['experiment'],
        'protocol_sha256': hashlib.sha256(protocol_raw).hexdigest(), 'protocol': protocol,
        'dataset': manifest['dataset'], 'taxonomy_id': manifest['taxonomy_id'],
        'source_revision': manifest['source_revision'], 'versions': dependency_versions(),
        'encoder': {'id': ENCODER_ID, 'revision': ENCODER_REVISION, 'frozen': True,
                    'normalized': True, 'dimensions': DIMENSIONS, 'max_sequence_length': 256,
                    'source_file_sha256': fingerprints, 'truncation_audit': truncation,
                    'implementation': 'injected_test_double' if encoder_factory else 'pinned_sentence_transformer'},
        'train_rows': len(partitions['train']), 'selection_rows': len(partitions['selection']),
        'label_count': len(binarizer.classes_), 'candidates': candidates,
        'selected_candidate_index': selected_index, 'control_candidate_index': control_index,
        'selected_minus_control': {key: best[key] - control[key] for key in (
            'exact_set_accuracy', 'micro_f1', 'macro_f1', 'micro_precision', 'micro_recall',
            'empty_prediction_fraction')},
        'calibration_read': False, 'test_evaluated': False, 'test_payload_decoded': False,
        'threshold_tuned': False, 'reference_report_loaded': False,
        'model_exported': False, 'live_model_changed': False,
        'limitations': [
            'This follow-up protocol was designed after prior development results, then frozen before these candidate fits.',
            'The winner is selected on reused development data, not an independent estimate of generalization.',
            'Balanced class weights use training prevalence separately in each binary head; their scores are not calibrated probabilities.',
            'C changes regularization, not the encoder or localization of separate requests.',
            'Publisher labels are unadjudicated; composition-family and pretrained-source overlap remain unknown.',
            'Native banking label sets do not establish support-app routing, out-of-scope handling or faithful action evidence.',
        ],
    }


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
        print(f'Semantic head study failed: {error}', file=sys.stderr)
        return 1
    print(json.dumps({'selected_candidate': report['candidates'][report['selected_candidate_index']],
                      'selected_minus_control': report['selected_minus_control'], 'test_evaluated': False}, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
