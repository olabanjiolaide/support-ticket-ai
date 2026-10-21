"""Compare two predeclared solver settings on the app's public development probes."""

import argparse
import copy
import json
from pathlib import Path
import sys
from time import perf_counter
import warnings

import numpy as np
from sklearn.exceptions import ConvergenceWarning
from sklearn.linear_model import LogisticRegression

from .data import load_tickets
from .multi_intent import VERSION, guarded_prediction
from .prepare import normalize
from .resources import data_path
from .robustness import PROBES_PATH, fingerprint, load_probes
from .scope_experiment import NEGATIVES_PATH, reject_negative_overlap
from .semantic_bundle import SemanticPredictor
from .semantic_experiment import encode

PROTOCOL_PATH = data_path('native_solver_protocol.json')


class CachedEncoder:
    """Share exactly the same frozen sentence vectors between all fitted heads."""

    def __init__(self, encoder):
        self.encoder = encoder
        self.tokenizer = encoder.tokenizer
        self.values = {}

    def encode(self, texts, **kwargs):
        missing = list(dict.fromkeys(text for text in texts if text not in self.values))
        if missing:
            values = self.encoder.encode(missing, **kwargs)
            self.values.update(zip(missing, values))
        return np.asarray([self.values[text] for text in texts])


def counts(rows, policy):
    supported = [r for r in rows if r['expected_category'] not in {'UNSUPPORTED', 'REVIEW'}]
    accepted = [r for r in supported if r[policy]['decision'] == 'suggestion']
    correct = sum(r[policy]['model_top_category'] == r['expected_category'] for r in accepted)
    return {'supported': len(supported), 'supported_accepted': len(accepted),
            'correct_accepted': correct, 'incorrect_accepted': len(accepted) - correct,
            'forced_supported_correct': sum(r[policy]['model_top_category'] == r['expected_category'] for r in supported),
            'unsupported_suggestions': sum(r['expected_category'] == 'UNSUPPORTED' and r[policy]['decision'] == 'suggestion' for r in rows),
            'review_suggestions': sum(r['expected_category'] == 'REVIEW' and r[policy]['decision'] == 'suggestion' for r in rows)}


def eligibility(control, tight, faithful):
    changes = []
    safe = faithful
    for policy in ('original', 'guarded'):
        for key, direction in [('supported_accepted', 1), ('correct_accepted', 1),
                               ('incorrect_accepted', -1), ('unsupported_suggestions', -1),
                               ('review_suggestions', -1)]:
            delta = direction * (tight[policy][key] - control[policy][key])
            safe = safe and delta >= 0
            changes.append(delta)
    return bool(safe and any(delta > 0 for delta in changes))


def run_experiment(model_dir, prepared_dir, *, protocol_path=PROTOCOL_PATH):
    protocol = json.loads(protocol_path.read_text(encoding='utf-8'))
    # The protocol is a recipe, not an arbitrary hyperparameter-search interface.
    if (protocol['settings'] != {'control': {'tol': 1e-4, 'max_iter': 1000},
                                'tight': {'tol': 1e-8, 'max_iter': 5000}} or
            protocol['C'] != 1 or protocol['seed'] != 42 or
            protocol['category_threshold'] != .5 or protocol['scope_threshold'] != .5 or
            protocol['scope_class_weight'] != 'balanced'):
        raise ValueError('Unexpected native solver protocol.')
    paths = {'train': prepared_dir / 'train.csv', 'negatives': NEGATIVES_PATH, 'probes': PROBES_PATH}
    hashes = {key: fingerprint(path) for key, path in paths.items()}
    if hashes != protocol['input_sha256']:
        raise ValueError('Inputs differ from the predeclared protocol.')
    manifest = json.loads((prepared_dir / 'manifest.json').read_text(encoding='utf-8'))
    metadata = json.loads((model_dir / 'semantic_model.json').read_text(encoding='utf-8'))
    if (manifest['split_sha256']['train'] != hashes['train'] or manifest['seed'] != 42 or
            metadata['training_sha256'] != hashes['train'] or
            metadata['negatives_sha256'] != hashes['negatives'] or
            metadata['model_sha256'] != protocol['reference_model_sha256'] or
            metadata['category_threshold'] != .5 or metadata['scope_threshold'] != .5):
        raise ValueError('Trusted bundle and training provenance do not match.')
    categories = set(metadata['categories'])
    train = load_tickets(paths['train'], categories=frozenset(categories))
    probes = load_probes(paths['probes'], categories)
    negatives = load_probes(paths['negatives'], categories)
    reject_negative_overlap(negatives, probes)
    if {normalize(r.text) for r in train} & {normalize(r['text']) for r in probes + negatives}:
        raise ValueError('Training text overlaps scope negatives or development probes.')
    reference = SemanticPredictor(model_dir)  # Validates manifest before loading trusted joblib.
    reference.encoder = CachedEncoder(reference.encoder)
    started = perf_counter()
    x = encode(reference.encoder, [r.text for r in train])
    nx = encode(reference.encoder, [r['text'] for r in negatives])
    sx = np.vstack([x, nx])
    sy = ['SUPPORTED'] * len(train) + ['UNSUPPORTED'] * len(negatives)
    y = [r.category for r in train]
    encoding_seconds = perf_counter() - started
    fitted, results, cases, timings = {}, {}, {}, {}
    for name, setting in protocol['settings'].items():
        candidate = copy.copy(reference)
        started = perf_counter()
        with warnings.catch_warnings():
            warnings.simplefilter('error', ConvergenceWarning)
            candidate.category = LogisticRegression(C=1, random_state=42, **setting).fit(x, y)
            candidate.scope = LogisticRegression(C=1, random_state=42, class_weight='balanced', **setting).fit(sx, sy)
        timings[name] = {'fit_seconds': perf_counter() - started,
                         'category_iterations': candidate.category.n_iter_.tolist(),
                         'scope_iterations': candidate.scope.n_iter_.tolist()}
        # Do not attribute newly fitted in-memory weights to the reference bundle.
        candidate.metadata = {**metadata, 'model_sha256': None}
        fitted[name] = candidate
        rows = [{**r, **guarded_prediction(r['text'], candidate)} for r in probes]
        cases[name] = rows
        results[name] = {policy: counts(rows, policy) for policy in ('original', 'guarded')}
        results[name]['by_slice'] = {sl: {policy: counts([r for r in rows if r['slice'] == sl], policy)
                                         for policy in ('original', 'guarded')}
                                     for sl in sorted({r['slice'] for r in rows})}
    # Check every probe and every fragment used by either policy, never the training sentences.
    texts = sorted({r['text'] for r in probes} | {fragment['text'] for rows in cases.values()
                    for row in rows for fragment in row['inspection']['fragments']})
    deviations, disagreements = [], 0
    for text in texts:
        baseline, control = reference.predict(text), fitted['control'].predict(text)
        disagreements += any(baseline[k] != control[k] for k in ('decision', 'model_top_category'))
        deviations.extend(abs(baseline[k] - control[k]) for k in ('uncalibrated_probability', 'scope_score'))
    fidelity = {'texts_checked': len(texts), 'decision_or_category_disagreements': disagreements,
                'maximum_score_difference': max(deviations),
                'passed': disagreements == 0 and max(deviations) <= 1e-6}
    eligible = eligibility(results['control'], results['tight'], fidelity['passed'])
    return {'experiment': protocol['experiment'], 'protocol_sha256': fingerprint(protocol_path),
            'input_sha256': hashes, 'reference_model_sha256': metadata['model_sha256'],
            'versions': metadata['versions'], 'guard_version': VERSION,
            'training_rows': len(train), 'scope_negative_rows': len(negatives),
            'encoding_seconds': encoding_seconds, 'fits': timings, 'control_fidelity': fidelity,
            'models': results, 'eligible_for_further_validation': eligible,
            'test_evaluated': False, 'validation_evaluated': False,
            'threshold_selection_performed': False, 'candidate_bundle_exported': False,
            'live_model_changed': False, 'cases': cases,
            'limitations': ['Previously inspected authored provisional labels; no independent quality estimate.',
                            'Fixed .5 cutoffs test policy transfer; tighter fitting does not calibrate scores.',
                            'Only C=1 and two solver settings; no encoder or scope training-data improvements.',
                            'No private reviews or reserved cases opened. All suggestions require human review.',
                            'Passing development gate only qualifies for further validation, not deployment.']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('model_dir', type=Path)
    parser.add_argument('prepared_dir', type=Path)
    parser.add_argument('output', type=Path)
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
    except (OSError, ValueError, KeyError, ImportError, ConvergenceWarning) as error:
        print(f'Error: {error}', file=sys.stderr)
        return 1
    print(json.dumps({k: report[k] for k in ('models', 'control_fidelity', 'fits', 'eligible_for_further_validation')}, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
