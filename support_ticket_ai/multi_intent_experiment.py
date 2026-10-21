"""Evaluate the explicit-request guard offline using a trusted semantic bundle."""

import argparse
import csv
import json
from pathlib import Path
import sys
from time import perf_counter

from .data import load_tickets
from .multi_intent import (ACTION, ALTERNATIVE, BOUNDARY, MAX_SEGMENTS, NEGATED,
                           REQUEST, VERSION, guarded_prediction)
from .prepare import normalize
from .robustness import PROBES_PATH, diagnostic_metrics, fingerprint, load_probes
from .semantic_bundle import SemanticPredictor


def run_experiment(model_dir: Path, prepared_dir: Path, *, probes_path=PROBES_PATH,
                   predictor_factory=None) -> dict:
    # Validate data before loading the optional encoder. Validation/test are not opened.
    metadata = json.loads((model_dir / 'semantic_model.json').read_text(encoding='utf-8'))
    manifest = json.loads((prepared_dir / 'manifest.json').read_text(encoding='utf-8'))
    train_path = prepared_dir / 'train.csv'
    train_hash = fingerprint(train_path)
    if train_hash != metadata['training_sha256'] or train_hash != manifest['split_sha256']['train']:
        raise ValueError('Training data does not match the semantic bundle.')
    categories = set(metadata['categories'])
    probes = load_probes(probes_path, categories)
    train = load_tickets(train_path, categories=frozenset(categories))
    if {normalize(r.text) for r in train} & {normalize(r['text']) for r in probes}:
        raise ValueError('Development probes overlap training text.')
    predictor = (predictor_factory or SemanticPredictor)(model_dir)
    rows = []
    start = perf_counter()
    for probe in probes:
        outcomes = guarded_prediction(probe['text'], predictor)
        rows.append({**probe, **outcomes})
    seconds = perf_counter() - start

    def metrics(subset, name):
        # Zero here encodes policy withholding only; raw model scores remain in cases.
        scored = [{**r, 'top_category': r[name]['model_top_category'],
                   'score': r[name]['uncalibrated_probability'] if r[name]['decision'] == 'suggestion' else 0}
                  for r in subset]
        return diagnostic_metrics(scored, metadata['category_threshold'])

    results = {name: {'development': metrics(rows, name),
                      'by_slice': {sl: metrics([r for r in rows if r['slice'] == sl], name)
                                   for sl in sorted({r['slice'] for r in rows})}}
               for name in ('original', 'guarded')}
    return {
        'experiment': 'explicit_cross_category_request_guard', 'guard_version': VERSION,
        'test_evaluated': False, 'validation_evaluated': False, 'model_retrained': False,
        'live_model_changed': False, 'policy_installed': False, 'candidate_bundle_exported': False,
        'threshold_selection_performed': False, 'test_double_used': predictor_factory is not None,
        'model_sha256': metadata['model_sha256'],
        'input_sha256': {'train': train_hash, 'manifest': fingerprint(prepared_dir / 'manifest.json'),
                        'probes': fingerprint(probes_path)},
        'configuration': {'max_segments': MAX_SEGMENTS, 'category_cutoff': metadata['category_threshold'],
                          'scope_cutoff': metadata['scope_threshold'],
                          'boundary_pattern': BOUNDARY.pattern, 'alternative_pattern': ALTERNATIVE.pattern,
                          'negation_pattern': NEGATED.pattern, 'request_pattern': REQUEST.pattern,
                          'imperative_actions': ACTION},
        'models': results, 'cases': rows,
        'newly_withheld_case_ids': [r['case_id'] for r in rows if r['inspection']['review_triggered']],
        'additional_model_calls': sum(len(r['inspection']['fragments']) for r in rows),
        'local_scoring_seconds': seconds, 'model_versions': metadata['versions'],
        'limitations': [
            'Hand-written bounded English request rules plus existing category/scope predictions, not a trained ambiguity model.',
            'No guard match is not evidence of one clear intent; existing unclear and implicit multiple-problem requests can still pass.',
            'Fragments lose cross-clause context and model scores remain uncalibrated.',
            'Different categories are model predictions, not established independent requested outcomes.',
            'Conditional/alternative requests and more than four segments are skipped, not resolved.',
            'Negated fragments are skipped conservatively; scope, irony, quotations, and indirect wording are not parsed generally.',
            'Same-category multiple actions do not trigger this cross-category routing check.',
            'CONTACT is conservatively ignored alongside a specific task to avoid treating a human-agent preference as another route; independent contact-information requests can be missed.',
            'Previously inspected authored probes have provisional labels; results are development diagnostics only.',
            'Existing abstentions are preserved; the guard can only reduce suggestions.',
            'No private reviews or pending reserved collection is read. Validation and held-out test files stay closed.',
            'Every suggestion still requires human review. This offline run does not activate the separate opt-in browser/API setting.',
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('model_dir', type=Path)
    parser.add_argument('prepared_dir', type=Path)
    parser.add_argument('output', type=Path, help='New offline report, never overwrites a previous run')
    args = parser.parse_args()
    try:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open('x', encoding='utf-8') as handle:
            try:
                report = run_experiment(args.model_dir, args.prepared_dir)
                json.dump(report, handle, indent=2, allow_nan=False)
                handle.write('\n')
            except BaseException:
                handle.close()
                args.output.unlink(missing_ok=True)
                raise
    except (OSError, ValueError, KeyError, ImportError, UnicodeError, csv.Error) as error:
        print(f'Error: {error}', file=sys.stderr)
        return 1
    print(json.dumps({'models': report['models'], 'newly_withheld_case_ids': report['newly_withheld_case_ids'],
                      'additional_model_calls': report['additional_model_calls']}, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
