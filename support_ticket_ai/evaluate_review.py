"""Evaluate reconciled pilot labels with frozen policies; no pilot fitting or tuning."""

import argparse
from collections import Counter
import csv
import json
from pathlib import Path
import sys
import tempfile

from sklearn.exceptions import ConvergenceWarning

from .predict import TicketPredictor
from .review_cases import CASES_PATH, load_cases, validate_progress
from .robustness import fingerprint
from .semantic_experiment import ENCODER_ID, ENCODER_REVISION, run_experiment

FROZEN_REPORT_PATH = Path(__file__).resolve().parents[1] / 'reports/bitext-baseline-v1/semantic_experiment.json'
WORD_CONFIG = {'ngram_range': [1, 2], 'max_features': 50000, 'min_df': 1, 'sublinear_tf': True,
               'C': 1.0, 'max_iter': 1000, 'class_weight': None, 'solver': 'lbfgs'}


def load_reconciled(path: Path, cases_path: Path) -> tuple[dict, list[dict]]:
    review = json.loads(path.read_text(encoding='utf-8-sig'))
    cases = load_cases(cases_path)
    if not isinstance(review, dict) or not isinstance(review.get('reviewer'), str):
        raise ValueError('Invalid review schema.')
    validate_progress(review, cases_path, review['reviewer'], cases)
    if {r['case_id'] for r in review['records']} != {c['case_id'] for c in cases}:
        raise ValueError('All pilot cases need a reviewed label before evaluation.')
    if review.get('status') != 'human_assistant_reconciled_development_only':
        raise ValueError('Expected the reconciled development review, not the original unanswered/review session.')
    reconciliation = review.get('reconciliation')
    if not isinstance(reconciliation, dict) or reconciliation.get('independently_adjudicated') is not False:
        raise ValueError('Reconciliation provenance must explicitly identify nonindependent development labels.')
    return review, cases


def write_probes(path: Path, review: dict, cases: list[dict]) -> None:
    labels = {row['case_id']: row for row in review['records']}
    with path.open('w', encoding='utf-8', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=['case_id', 'slice', 'text', 'expected_category', 'label_status'])
        writer.writeheader()
        for case in cases:
            label = labels[case['case_id']]
            expected = (label['categories'][0] if label['kind'] == 'single_intent' else
                        'UNSUPPORTED' if label['kind'] == 'unsupported' else 'REVIEW')
            writer.writerow({'case_id': case['case_id'], 'slice': label['kind'], 'text': case['text'],
                             'expected_category': expected, 'label_status': 'reviewed'})


def frozen_thresholds(prior: dict) -> dict:
    encoder = prior['encoder']
    if (encoder['id'] != ENCODER_ID or encoder['revision'] != ENCODER_REVISION or
            encoder['test_double_used'] is not False or encoder['dimensions'] != 384 or
            encoder['max_sequence_length_wordpieces'] != 256 or encoder['normalize_embeddings'] is not True or
            prior['category_head'] != {'C': 1.0, 'max_iter': 1000, 'class_weight': None} or
            prior['scope_head'] != {'C': 1.0, 'max_iter': 1000, 'class_weight': 'balanced', 'scope_cutoff': .5}):
        raise ValueError('Frozen experiment recipe does not match this evaluator.')
    return {name: {policy: data['selection']['selected_threshold'] for policy, data in model['policies'].items()}
            for name, model in prior['models'].items()}


def evaluate_review(model_dir: Path, prepared_dir: Path, review_path: Path, cache_dir: Path,
                    cases_path: Path = CASES_PATH, prior_path: Path = FROZEN_REPORT_PATH) -> dict:
    review, cases = load_reconciled(review_path, cases_path)
    prior = json.loads(prior_path.read_text(encoding='utf-8'))
    thresholds = frozen_thresholds(prior)
    manifest = json.loads((prepared_dir / 'manifest.json').read_text(encoding='utf-8'))
    if (fingerprint(prepared_dir / 'manifest.json') != prior['preparation_manifest_sha256'] or
            manifest['seed'] != prior['seed']):
        raise ValueError('Prepared data/seed does not match the frozen experiment recipe.')
    if TicketPredictor(model_dir).metadata['configuration'] != WORD_CONFIG:
        raise ValueError('Word model configuration differs from the frozen baseline recipe.')
    with tempfile.TemporaryDirectory(prefix='review-evaluation-') as directory:
        probes = Path(directory) / 'reviewed-probes.csv'
        write_probes(probes, review, cases)
        experiment = run_experiment(model_dir, prepared_dir, cache_dir, probes_path=probes,
                                    frozen_thresholds=thresholds)
    metrics = {}
    labels = {row['case_id']: row for row in review['records']}
    for name, model in experiment['models'].items():
        policies = {}
        for policy, values in model['policies'].items():
            threshold = thresholds[name][policy]
            if threshold is None:
                policies[policy] = {'policy_selected': False, 'metrics': None}
                continue
            outcomes = []
            for row in model['probe_cases']:
                accepted = row['score'] >= threshold and (policy != 'with_scope' or row['scope_score'] >= .5)
                label = labels[row['case_id']]
                outcomes.append({'kind': label['kind'], 'accepted': accepted,
                                 'category_correct': row['top_category'] in label['categories']})
            details = {}
            for kind in ('single_intent', 'multiple_intents', 'insufficient_context', 'unsupported'):
                group = [row for row in outcomes if row['kind'] == kind]
                accepted = [row for row in group if row['accepted']]
                details[kind] = {'rows': len(group), 'accepted_rows': len(accepted),
                                 'withheld_rows': len(group) - len(accepted)}
                if kind == 'single_intent':
                    details[kind].update(correct_accepted_rows=sum(row['category_correct'] for row in accepted),
                                         incorrect_accepted_rows=sum(not row['category_correct'] for row in accepted))
            policies[policy] = {'policy_selected': True, 'category_threshold': threshold,
                                'metrics': values['broader_development_probes']['metrics'], 'by_intent_type': details}
        metrics[name] = {'forced_single_intent_metrics': model['forced_supported_probe_metrics'], 'policies': policies}
    return {
        'experiment': 'reconciled_pilot_frozen_policy_evaluation',
        'evaluation_role': 'assisted_reconciled_development_diagnostics_not_independent_audit',
        'pilot_used_for_fitting': False, 'pilot_used_for_threshold_selection': False,
        'threshold_selection_performed': experiment['threshold_selection_performed'],
        'heads_reconstructed_from_source_training': True,
        'encoder_fine_tuned': False, 'test_evaluated': False, 'live_model_changed': False,
        'review_sha256': fingerprint(review_path), 'collection_sha256': fingerprint(cases_path),
        'frozen_experiment_report_sha256': fingerprint(prior_path),
        'frozen_thresholds': thresholds, 'intent_type_counts': dict(Counter(r['kind'] for r in review['records'])),
        'guided_unsupported_rows': len(review['reconciliation'].get('guided_unsupported_case_ids', [])),
        'labels_independently_adjudicated': False,
        'encoder': experiment['encoder'], 'versions': experiment['versions'],
        'preparation_manifest_sha256': experiment['preparation_manifest_sha256'],
        'baseline_model_sha256': experiment['baseline_model_sha256'],
        'training_counts': experiment['training_counts'], 'training_overlap': experiment['training_overlap'],
        'models': metrics,
        'limitations': [
            'Only 40 assistant-authored cases; related scenarios overlap earlier development families.',
            'Labels were reconciled with assistant suggestions; eight unsupported labels were completed with guidance.',
            'Counts describe these assisted development labels, not independent test accuracy or production reliability.',
            'Multiple-intent and insufficient-context cases are evaluated as requests to withhold a single category.',
            'Existing classifiers have no dedicated multi-intent or clarification head; withholding does not identify the reason.',
            'Human-assistance flags are annotations and are not predicted or implemented in the live API.',
            'Heads are reconstructed from the frozen training recipe; no exported semantic bundle is installed.',
            'Encoder limits, uncalibrated scores, and known source/negative-template limitations still apply.',
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('model_dir', type=Path)
    parser.add_argument('prepared_dir', type=Path)
    parser.add_argument('review_file', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--cache-dir', type=Path, default=Path('artifacts/encoder-cache'))
    args = parser.parse_args()
    try:
        if args.output.exists():
            raise ValueError('Report already exists; choose a new filename.')
        report = evaluate_review(args.model_dir, args.prepared_dir, args.review_file, args.cache_dir)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open('x', encoding='utf-8') as handle:
            json.dump(report, handle, indent=2)
            handle.write('\n')
    except (OSError, ValueError, KeyError, UnicodeError, csv.Error, ConvergenceWarning) as error:
        print(f'Error: {error}', file=sys.stderr)
        return 1
    print(json.dumps({'intent_type_counts': report['intent_type_counts'], 'models': report['models'],
                      'pilot_used_for_fitting': False, 'threshold_selection_performed': False}, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
