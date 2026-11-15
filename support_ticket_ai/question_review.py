"""Offline human wording review for combined-pilot reports; no model calls."""
import argparse
import hashlib
import json
from pathlib import Path

CRITERIA = {
    'decision_appropriate': 'Was asking, or not asking, appropriate for interpreting this message?',
    'resolves_ambiguity': 'Does the question resolve the actual ambiguity, naming the alternatives when needed?',
    'preserves_actions_and_targets': 'Does it preserve actions, order identifiers and negation without assuming a choice?',
    'no_invented_requirements': 'Does it avoid invented priorities, business rules or requests to repeat known information?',
}


def worksheet(report, digest):
    if report.get('evaluation_mode') != 'combined_conditions_questions':
        raise ValueError('Expected a combined-pilot report.')
    rows = []
    seen = set()
    for case in report['cases']:
        ident = case['id']
        if not isinstance(ident, str) or ident in seen:
            raise ValueError('Case IDs must be distinct strings.')
        seen.add(ident)
        valid = case['valid_structured_response']
        if type(valid) is not bool:
            raise ValueError('Invalid case validity flag.')
        proposal = case.get('proposal', {}) if valid else {}
        question = proposal.get('question')
        if valid and (not isinstance(question, dict) or question.get('decision') not in {'ask', 'none'}):
            raise ValueError('Expected a validated ask/none question.')
        rows.append({
            'id': ident, 'valid_structured_response': valid,
            'source_text': proposal.get('review', {}).get('source_text'),
            'question': question, 'failure_code': case.get('failure_code'),
            'review': {'reviewer': '', 'ratings': {key: None for key in CRITERIA}, 'notes': ''},
        })
    return {'schema_version': 1, 'report_sha256': digest, 'rubric': CRITERIA,
            'instructions': 'Use pass/fail for decision_appropriate. For ask, use pass/fail for all remaining criteria. For none, mark remaining criteria not_applicable. Failed generations remain failures and are not wording reviews. Null ratings remain unreviewed. Review original meaning; automatic decision metrics do not establish wording quality.',
            'cases': rows}


def summarize_review(report, digest, review):
    expected = worksheet(report, digest)
    if set(review) != set(expected) or review['schema_version'] != 1 or review['report_sha256'] != digest:
        raise ValueError('Worksheet does not match the source report.')
    if review['rubric'] != expected['rubric'] or review['instructions'] != expected['instructions']:
        raise ValueError('Worksheet rubric was changed.')
    if len(review['cases']) != len(expected['cases']):
        raise ValueError('Worksheet case coverage changed.')
    totals = {'attempted': len(expected['cases']), 'generation_failures': 0,
              'reviewed_valid': 0, 'unreviewed_valid': 0, 'all_criteria_passed': 0,
              'criteria_failures': {key: 0 for key in CRITERIA}}
    for actual, source in zip(review['cases'], expected['cases']):
        if set(actual) != set(source) or any(actual[key] != source[key] for key in source if key != 'review'):
            raise ValueError('Worksheet source content or case order changed.')
        entry = actual['review']
        if not isinstance(entry, dict) or set(entry) != {'reviewer', 'ratings', 'notes'}:
            raise ValueError('Invalid review entry.')
        if not isinstance(entry['reviewer'], str) or not isinstance(entry['notes'], str):
            raise ValueError('Reviewer and notes must be strings.')
        ratings = entry['ratings']
        if not isinstance(ratings, dict) or set(ratings) != set(CRITERIA):
            raise ValueError('Invalid review criteria.')
        ask = source['question'] is not None and source['question']['decision'] == 'ask'
        for key, value in ratings.items():
            allowed = [None, 'pass', 'fail'] if key == 'decision_appropriate' or ask else [None, 'not_applicable']
            if value not in allowed:
                raise ValueError('Invalid or inapplicable rating.')
        if not source['valid_structured_response']:
            if any(value is not None for value in ratings.values()) or entry['reviewer'] or entry['notes']:
                raise ValueError('Failed generations cannot receive wording ratings.')
            totals['generation_failures'] += 1
            continue
        if not entry['reviewer'].strip() or any(value is None for value in ratings.values()):
            totals['unreviewed_valid'] += 1
            continue
        totals['reviewed_valid'] += 1
        failures = [key for key, value in ratings.items() if value == 'fail']
        totals['all_criteria_passed'] += not failures
        for key in failures:
            totals['criteria_failures'][key] += 1
    return {'schema_version': 1, 'report_sha256': digest, 'summary': totals,
            'limitations': 'Human judgments only; no automatic semantic certification. Unreviewed valid cases and generation failures are never counted as passing. No independent accuracy estimate.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report', required=True, type=Path)
    parser.add_argument('--review', type=Path, help='Completed worksheet to summarize; omit to create one.')
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists():
        parser.error('Output already exists; choose another filename.')
    try:
        raw = args.report.read_bytes()
        report = json.loads(raw)
        digest = hashlib.sha256(raw).hexdigest()
        result = (summarize_review(report, digest, json.loads(args.review.read_bytes()))
                  if args.review else worksheet(report, digest))
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open('x', encoding='utf-8') as handle:
            json.dump(result, handle, indent=2, ensure_ascii=False)
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as error:
        parser.error(str(error))
    print('Saved offline human question review summary.' if args.review else 'Saved unreviewed question worksheet. No semantic ratings were inferred.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
