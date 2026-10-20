"""Collect human labels for an unscored pilot, without loading a model."""

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile

from .prepare import normalize

CASES_PATH = Path(__file__).resolve().parents[1] / 'data/review_pilot.csv'
CATEGORIES = frozenset({'ACCOUNT', 'CANCEL', 'CONTACT', 'DELIVERY', 'FEEDBACK', 'INVOICE',
                        'ORDER', 'PAYMENT', 'REFUND', 'SHIPPING', 'SUBSCRIPTION'})
KINDS = {'1': 'single_intent', '2': 'multiple_intents',
         '3': 'insufficient_context', '4': 'unsupported'}


def load_cases(path: Path) -> list[dict]:
    with path.open(encoding='utf-8-sig', newline='') as handle:
        reader = csv.DictReader(handle, strict=True)
        fields = reader.fieldnames or []
        if len(fields) != 3 or set(fields) != {'case_id', 'family_id', 'text'}:
            raise ValueError('Expected case_id, family_id, text columns only; no suggested labels.')
        rows = list(reader)
    if not rows:
        raise ValueError('Case collection is empty.')
    ids, texts = set(), set()
    for row in rows:
        if None in row or any(value is None or not value.strip() for value in row.values()):
            raise ValueError('Blank or malformed case fields.')
        row.update({key: value.strip() for key, value in row.items()})
        if len(row['text']) > 2000:
            raise ValueError('Case exceeds the application text limit.')
        if row['case_id'] in ids or normalize(row['text']) in texts:
            raise ValueError('Duplicate case ID or normalized text.')
        ids.add(row['case_id'])
        texts.add(normalize(row['text']))
    return rows


def validate_label(kind: str, categories: list[str]) -> None:
    if kind not in KINDS.values() or not isinstance(categories, list):
        raise ValueError('Invalid intent type or category list.')
    if any(not isinstance(label, str) or label not in CATEGORIES for label in categories):
        raise ValueError('Unknown category; use names from the displayed list.')
    if len(set(categories)) != len(categories):
        raise ValueError('Do not repeat a category.')
    if ((kind == 'single_intent' and len(categories) != 1) or
            (kind == 'multiple_intents' and len(categories) < 2) or
            (kind in {'insufficient_context', 'unsupported'} and categories)):
        raise ValueError('Single intent needs one category; multiple intents need at least two; other types need none.')


def new_review(cases_path: Path, reviewer: str) -> dict:
    return {'schema_version': 1, 'collection_sha256': hashlib.sha256(cases_path.read_bytes()).hexdigest(),
            'reviewer': reviewer, 'records': [],
            'status': 'human_annotation_pilot_not_adjudicated',
            'model_predictions_shown': False}


def validate_progress(progress: dict, cases_path: Path, reviewer: str, cases: list[dict]) -> None:
    if (not isinstance(progress, dict) or progress.get('schema_version') != 1 or
            progress.get('collection_sha256') != hashlib.sha256(cases_path.read_bytes()).hexdigest() or
            progress.get('reviewer') != reviewer or not isinstance(progress.get('records'), list)):
        raise ValueError('Progress file does not match this collection/reviewer or has an invalid schema.')
    seen, by_id = set(), {row['case_id']: row for row in cases}
    for record in progress['records']:
        if not isinstance(record, dict):
            raise ValueError('Invalid review record.')
        case_id = record.get('case_id')
        if not isinstance(case_id, str) or case_id not in by_id or case_id in seen:
            raise ValueError('Unknown or duplicate reviewed case ID.')
        if record.get('family_id') != by_id[case_id]['family_id']:
            raise ValueError('Review family does not match collection.')
        validate_label(record.get('kind'), record.get('categories'))
        if not isinstance(record.get('note'), str) or not isinstance(record.get('reviewed_at_utc'), str):
            raise ValueError('Review note/timestamp missing.')
        seen.add(case_id)


def save_progress(path: Path, progress: dict) -> None:
    # Replace only the explicitly created/resumed session file, after each answer.
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent,
                                         prefix='review-', suffix='.tmp', delete=False) as handle:
            temporary = Path(handle.name)
            json.dump(progress, handle, indent=2)
            handle.write('\n')
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def review_session(cases: list[dict], progress: dict, output: Path, limit: int,
                   *, input_fn=input, print_fn=print) -> int:
    completed = {row['case_id'] for row in progress['records']}
    added = 0
    print_fn('No model is loaded. Label the request yourself; skip if uncertain.')
    print_fn('1 = one clear intent; 2 = multiple intents; 3 = insufficient context; 4 = unsupported')
    print_fn('Categories: ' + ', '.join(sorted(CATEGORIES)))
    print_fn('CANCEL = cancellation-fee questions; actual order cancellation = ORDER.')
    print_fn('SUBSCRIPTION = newsletter preferences; SHIPPING = destination addresses.')
    try:
        for case in cases:
            if case['case_id'] in completed or added >= limit:
                continue
            print_fn(f"\nCase {case['case_id']}\n{case['text']}")
            while True:
                answer = input_fn('Type 1/2/3/4, s to skip, or q to save and quit: ').strip().lower()
                if answer == 'q':
                    return added
                if answer == 's':
                    break
                if answer not in KINDS:
                    print_fn('Choose 1, 2, 3, 4, s, or q.')
                    continue
                kind = KINDS[answer]
                labels = []
                if kind in {'single_intent', 'multiple_intents'}:
                    labels = [value.strip().upper() for value in input_fn('Category name(s), separated by commas: ').split(',')]
                try:
                    validate_label(kind, labels)
                except ValueError as error:
                    print_fn(str(error))
                    continue
                note = input_fn('Brief reason or disagreement note (Enter to leave blank): ').strip()
                record = {'case_id': case['case_id'], 'family_id': case['family_id'], 'kind': kind,
                          'categories': sorted(labels), 'note': note,
                          'reviewed_at_utc': datetime.now(timezone.utc).isoformat()}
                progress['records'].append(record)
                try:
                    save_progress(output, progress)
                except OSError:
                    progress['records'].pop()
                    raise
                completed.add(case['case_id'])
                added += 1
                print_fn(f"Saved. Reviewed {len(progress['records'])}/{len(cases)}.")
                break
    except (EOFError, KeyboardInterrupt):
        print_fn('\nStopped. Previously saved answers are preserved.')
    return added


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path, help='Local JSON progress file; use artifacts/ to keep it out of git')
    parser.add_argument('--reviewer', required=True, help='Reviewer name or pseudonym; use the same value to resume')
    parser.add_argument('--cases', type=Path, default=CASES_PATH)
    parser.add_argument('--limit', type=int, default=5, help='Maximum answers this session (default: 5)')
    parser.add_argument('--resume', action='store_true')
    args = parser.parse_args()
    try:
        reviewer = args.reviewer.strip()
        if not reviewer or args.limit < 1:
            raise ValueError('Reviewer must be nonblank and limit must be positive.')
        cases = load_cases(args.cases)
        if args.resume:
            progress = json.loads(args.output.read_text(encoding='utf-8'))
            validate_progress(progress, args.cases, reviewer, cases)
        else:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            progress = new_review(args.cases, reviewer)
            with args.output.open('x', encoding='utf-8') as handle:
                json.dump(progress, handle, indent=2)
                handle.write('\n')
        review_session(cases, progress, args.output, args.limit)
        print(f"Progress: {len(progress['records'])}/{len(cases)} reviewed. File: {args.output}")
        print('These labels are a review pilot, not independently adjudicated ground truth.')
    except (OSError, ValueError, KeyError, UnicodeError, csv.Error) as error:
        print(f'Error: {error}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
