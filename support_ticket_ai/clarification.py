"""Offline, narrow English clarification rules; no live routing integration."""

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

from .resources import data_path

VERSION = 1
QUESTION = 'What were you trying to do, and what happened?'
REFERENCE = r'(?:it|this|that|something|everything|(?:the|my) thing|what i bought)'
RULES = {
    'unspecified_failure': rf'{REFERENCE} (?:does not work|doesn\'t work|is not working|isn\'t working|stopped working|failed|is broken)',
    'unspecified_problem': rf'(?:something|everything) is wrong(?: with {REFERENCE})?',
}
PATTERNS = {name: re.compile(pattern, re.I) for name, pattern in RULES.items()}
PROTOCOL_PATH = data_path('clarification_protocol.json')
CONTRAST_PATH = data_path('clarification_contrasts.json')


def inspect_context(text):
    if not isinstance(text, str) or not text.strip() or len(text) > 2000:
        raise ValueError('Use a nonempty request of at most 2000 characters.')
    # Match the entire message. Extra clauses, quotes and concrete task context
    # must not disappear through substring matching or punctuation stripping.
    normalized = ' '.join(text.strip().replace('\u2019', "'").split()).rstrip('.!?').rstrip()
    rule = next((name for name, pattern in PATTERNS.items() if pattern.fullmatch(normalized)), None)
    return {'version': VERSION, 'clarification_proposed': rule is not None,
            'rule': rule, 'question': QUESTION if rule else None,
            'status': 'generic_failure_statement' if rule else 'no_narrow_rule_match'}


def apply_clarification(text, prediction):
    if prediction.get('decision') not in {'suggestion', 'abstain'}:
        raise ValueError('Expected a recorded suggestion or abstention.')
    inspection = inspect_context(text)
    result = dict(prediction)
    changed = inspection['clarification_proposed'] and prediction['decision'] == 'suggestion'
    if changed:
        result.update(decision='abstain', suggested_category=None, requires_human_review=True,
                      review_reason='The generic failure statement needs more context. Ask the proposed clarification question.')
    return {'prediction': result, 'inspection': inspection, 'newly_withheld': changed}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def summarize(rows, field):
    supported = [r for r in rows if r['expected_category'] not in {'REVIEW', 'UNSUPPORTED'}]
    accepted = [r for r in supported if r[field]['decision'] == 'suggestion']
    correct = sum(r[field]['suggested_category'] == r['expected_category'] for r in accepted)
    return {'supported_rows': len(supported), 'supported_accepted': len(accepted),
            'correct_accepted': correct, 'incorrect_accepted': len(accepted) - correct,
            'review_rows': sum(r['expected_category'] == 'REVIEW' for r in rows),
            'review_withheld': sum(r['expected_category'] == 'REVIEW' and r[field]['decision'] == 'abstain' for r in rows),
            'unsupported_suggestions': sum(r['expected_category'] == 'UNSUPPORTED' and r[field]['decision'] == 'suggestion' for r in rows)}


def run_experiment(source_path, *, protocol_path=PROTOCOL_PATH, contrast_path=CONTRAST_PATH):
    protocol = json.loads(protocol_path.read_text(encoding='utf-8'))
    if (protocol['source_report_sha256'] != digest(source_path) or
            protocol['contrast_sha256'] != digest(contrast_path) or
            protocol['rules'] != RULES or protocol['question'] != QUESTION or
            protocol['rule_version'] != VERSION):
        raise ValueError('Inputs or rules differ from the frozen development protocol.')
    source = json.loads(source_path.read_text(encoding='utf-8'))
    # Only the recorded control is read; no model loading, fitting or new scores.
    rows = []
    for row in source['cases']['control']:
        outcome = apply_clarification(row['text'], row['guarded'])
        rows.append({'case_id': row['case_id'], 'text': row['text'],
                     'expected_category': row['expected_category'],
                     'before': row['guarded'], 'after': outcome['prediction'],
                     'inspection': outcome['inspection'], 'newly_withheld': outcome['newly_withheld']})
    contrasts = json.loads(contrast_path.read_text(encoding='utf-8'))
    checked = [{**case, 'inspection': inspect_context(case['text'])} for case in contrasts]
    for case in checked:
        case['matches_authored_expectation'] = case['inspection']['clarification_proposed'] == case['expected_clarification']
    before, after = summarize(rows, 'before'), summarize(rows, 'after')
    gate = (after['supported_accepted'] >= before['supported_accepted'] and
            after['correct_accepted'] >= before['correct_accepted'] and
            after['incorrect_accepted'] <= before['incorrect_accepted'] and
            after['unsupported_suggestions'] <= before['unsupported_suggestions'] and
            after['review_withheld'] > before['review_withheld'] and
            all(case['matches_authored_expectation'] for case in checked))
    return {'experiment': 'clarification-rules-v1', 'protocol_sha256': digest(protocol_path),
            'source_report_sha256': digest(source_path), 'contrast_sha256': digest(contrast_path),
            'before': before, 'after': after, 'development_gate_passed': gate,
            'newly_withheld_case_ids': [r['case_id'] for r in rows if r['newly_withheld']],
            'contrast_matches': sum(c['matches_authored_expectation'] for c in checked),
            'contrast_rows': len(checked), 'cases': rows, 'contrasts': checked,
            'model_retrained': False, 'new_model_scores_computed': False,
            'live_model_changed': False, 'browser_integrated': False, 'test_evaluated': False,
            'limitations': ['Rules designed after inspecting these known development failures; no independent improvement estimate.',
                            'Author-written contrast expectations are provisional and not independently adjudicated.',
                            'Whole-message English patterns only; no general context resolution or multiple-problem understanding.',
                            'No match does not establish sufficient context. A match proposes a question; usefulness of the answer is untested.',
                            'Single-message input; conversation history could already resolve a generic reference.',
                            'No private reviews, pending reserved collection, validation or held-out test data opened.',
                            'Offline development gate only; no automatic promotion. Every suggestion requires review.']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source_report', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    try:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open('x', encoding='utf-8') as handle:
            try:
                report = run_experiment(args.source_report)
                json.dump(report, handle, indent=2, allow_nan=False)
                handle.write('\n')
            except BaseException:
                handle.close()
                args.output.unlink(missing_ok=True)
                raise
    except (OSError, ValueError, KeyError) as error:
        print(f'Error: {error}', file=sys.stderr)
        return 1
    print(json.dumps({k: report[k] for k in ('before', 'after', 'newly_withheld_case_ids',
                      'contrast_matches', 'contrast_rows', 'development_gate_passed')}, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
