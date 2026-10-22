"""Offline lexical baseline for account-access plus payment problem statements."""

import argparse
import json
from pathlib import Path
import re
import sys

from .clarification import digest, summarize
from .resources import data_path

VERSION = 1
MAX_SEGMENTS = 4
QUESTION = 'You mentioned account access and a payment issue. Which would you like help with first?'
RULES = {
    'ACCOUNT': r"(?:i (?:cannot|can't|am unable to) (?:log in|sign in|access my account)|my account (?:is|was) locked)",
    'PAYMENT': r"(?:my (?:checkout )?payment (?:was |is )?(?:rejected|declined|failed)|my card (?:was |is )?declined|i (?:was|have been) charged twice)",
}
BOUNDARY = re.compile(r'(?:\s*,?\s+\b(?:and|also|plus|but)\b\s+|[;\n]+|[.!?]\s+)', re.I)
SKIP = re.compile(r'\b(?:if|unless|either|or|instead|rather than|because|when|after|before)\b|["“”]', re.I)
PATTERNS = {name: re.compile(pattern, re.I) for name, pattern in RULES.items()}
PROTOCOL_PATH = data_path('problem_statements_protocol.json')
CONTRAST_PATH = data_path('problem_statements_contrasts.json')


def configuration():
    return {'version': VERSION, 'max_segments': MAX_SEGMENTS, 'rules': RULES,
            'boundary': BOUNDARY.pattern, 'skip': SKIP.pattern, 'question': QUESTION,
            'match': 'Entire trimmed fragment; all fragments must match, with both ACCOUNT and PAYMENT present.'}


def inspect_problems(text):
    if not isinstance(text, str) or not text.strip() or len(text) > 2000:
        raise ValueError('Use a nonempty request of at most 2000 characters.')
    empty = {'version': VERSION, 'multiple_problem_hypothesis': False,
             'category_hints': [], 'evidence': [], 'question': None}
    if SKIP.search(text):
        return {**empty, 'status': 'conditional_alternative_causal_or_quoted_skipped'}
    intervals, start = [], 0
    for boundary in BOUNDARY.finditer(text):
        intervals.append((start, boundary.start()))
        start = boundary.end()
    intervals.append((start, len(text)))
    if not 2 <= len(intervals) <= MAX_SEGMENTS:
        return {**empty, 'status': 'outside_fragment_bounds'}
    evidence = []
    for start, end in intervals:
        while start < end and text[start] in ' \t\r,.!?':
            start += 1
        while end > start and text[end - 1] in ' \t\r,.!?':
            end -= 1
        original = text[start:end]
        normalized = ' '.join(original.replace('\u2019', "'").split())
        hint = next((name for name, pattern in PATTERNS.items() if pattern.fullmatch(normalized)), None)
        if hint is None:
            return {**empty, 'status': 'unrecognized_fragment'}
        evidence.append({'start': start, 'end': end, 'text': original, 'category_hint': hint})
    categories = sorted({e['category_hint'] for e in evidence})
    if categories != ['ACCOUNT', 'PAYMENT']:
        return {**empty, 'status': 'one_problem_category_only'}
    return {'version': VERSION, 'multiple_problem_hypothesis': True,
            'category_hints': categories, 'evidence': evidence, 'question': QUESTION,
            'status': 'account_and_payment_problem_patterns'}


def apply_problem_check(text, prediction):
    if prediction.get('decision') not in {'suggestion', 'abstain'}:
        raise ValueError('Expected a recorded suggestion or abstention.')
    inspection = inspect_problems(text)
    result = dict(prediction)
    changed = inspection['multiple_problem_hypothesis'] and prediction['decision'] == 'suggestion'
    if changed:
        result.update(decision='abstain', suggested_category=None, requires_human_review=True,
                      review_reason='Account-access and payment problem statements matched the offline rules. Ask which issue to address first.')
    return {'prediction': result, 'inspection': inspection, 'newly_withheld': changed}


def run_experiment(source_path, *, protocol_path=PROTOCOL_PATH, contrast_path=CONTRAST_PATH):
    protocol = json.loads(protocol_path.read_text(encoding='utf-8'))
    if (protocol['source_report_sha256'] != digest(source_path) or
            protocol['contrast_sha256'] != digest(contrast_path) or
            protocol['configuration'] != configuration()):
        raise ValueError('Inputs or configuration differ from the frozen development protocol.')
    source = json.loads(source_path.read_text(encoding='utf-8'))
    rows = []
    for row in source['cases']:
        outcome = apply_problem_check(row['text'], row['after'])
        rows.append({'case_id': row['case_id'], 'text': row['text'],
                     'expected_category': row['expected_category'], 'before': row['after'],
                     'after': outcome['prediction'], 'inspection': outcome['inspection'],
                     'newly_withheld': outcome['newly_withheld']})
    contrasts = []
    for case in json.loads(contrast_path.read_text(encoding='utf-8')):
        inspection = inspect_problems(case['text'])
        contrasts.append({**case, 'inspection': inspection,
                          'matches_authored_expectation': inspection['multiple_problem_hypothesis'] == case['expected_multiple_problem']})
    before, after = summarize(rows, 'before'), summarize(rows, 'after')
    passed = (after['supported_accepted'] >= before['supported_accepted'] and
              after['correct_accepted'] >= before['correct_accepted'] and
              after['incorrect_accepted'] <= before['incorrect_accepted'] and
              after['unsupported_suggestions'] <= before['unsupported_suggestions'] and
              after['review_withheld'] > before['review_withheld'] and
              all(c['matches_authored_expectation'] for c in contrasts))
    return {'experiment': 'problem-statements-v1', 'protocol_sha256': digest(protocol_path),
            'source_report_sha256': digest(source_path), 'contrast_sha256': digest(contrast_path),
            'before': before, 'after': after, 'development_gate_passed': passed,
            'newly_withheld_case_ids': [r['case_id'] for r in rows if r['newly_withheld']],
            'contrast_matches': sum(c['matches_authored_expectation'] for c in contrasts),
            'contrast_rows': len(contrasts), 'cases': rows, 'contrasts': contrasts,
            'model_retrained': False, 'new_model_scores_computed': False,
            'live_model_changed': False, 'browser_integrated': False, 'test_evaluated': False,
            'limitations': ['Designed after inspecting the known account/payment development miss; no independent improvement estimate.',
                            'New contrasts are authored provisional regression checks, not adjudicated or held-out data.',
                            'Only fixed English account-access and payment problem patterns; hints are lexical hypotheses, not verified intents.',
                            'Two stated issues can share a cause or describe one desired outcome; no independence claim.',
                            'Unknown fragments, quotations, alternatives, conditionals and causal/temporal markers are skipped, not resolved.',
                            'Single-message context only. Question usefulness and user follow-up outcomes are untested.',
                            'No private/pending reviews, validation, calibration or held-out tests opened; every suggestion requires human review.',
                            'Offline gate only; no automatic deployment or action execution.']}


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
