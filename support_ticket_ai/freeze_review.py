"""Freeze scenario-family partitions for an unlabeled review collection."""

import argparse
import csv
import hashlib
import json
from pathlib import Path
import sys

from .review_cases import load_cases


def canonical_fingerprint(cases: list[dict]) -> str:
    # Stable across CSV row order and platform LF/CRLF checkout conversions.
    encoded = json.dumps(sorted(cases, key=lambda row: row['case_id']),
                         ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8')
    return hashlib.sha256(encoded).hexdigest()


def build_manifest(cases_path: Path, seed: int = 42) -> dict:
    if type(seed) is not int:
        raise ValueError('Seed must be an integer.')
    cases = load_cases(cases_path)
    families = sorted({row['family_id'] for row in cases},
                      key=lambda family: (hashlib.sha256(f'{seed}:{family}'.encode()).hexdigest(), family))
    if len(families) < 6:
        raise ValueError('At least six scenario families are required.')
    held = len(families) // 6
    groups = {'audit': families[:held], 'selection': families[held:2 * held], 'train': families[2 * held:]}
    family_partitions = {family: split for split, members in groups.items() for family in members}
    partitions = {split: sorted(row['case_id'] for row in cases if family_partitions[row['family_id']] == split)
                  for split in ('train', 'selection', 'audit')}
    return {
        'schema_version': 1, 'kind': 'unlabeled_scenario_family_reservation', 'seed': seed,
        'canonical_cases_sha256': canonical_fingerprint(cases),
        'rows': len(cases), 'families': len(families),
        'assignment_rule': 'SHA256(seed:family_id) order; first floor(families/6) audit, next same selection, remainder train',
        'family_partitions': dict(sorted(family_partitions.items())), 'partition_case_ids': partitions,
        'partition_row_counts': {split: len(ids) for split, ids in partitions.items()},
        'partition_family_counts': {split: len(members) for split, members in groups.items()},
        'labels_pending': True, 'model_scored_before_reservation': False,
        'independent_audit_established': False,
        'limitations': ['Assistant-authored synthetic texts and scenario groups; labels have not been collected.',
                        'Author groups can share linguistic templates; this is not proof of semantic independence.',
                        'No class balance or category coverage is established before human labeling.',
                        'Pre-scoring status is an author declaration; the tool cannot observe other experiments.',
                        'Reserved audit is not a final benchmark or reliability claim.'],
    }


def verify_manifest(cases_path: Path, manifest_path: Path) -> dict:
    frozen = json.loads(manifest_path.read_text(encoding='utf-8'))
    if not isinstance(frozen, dict) or frozen.get('schema_version') != 1:
        raise ValueError('Invalid partition manifest.')
    expected = build_manifest(cases_path, frozen.get('seed'))
    for key in ('kind', 'canonical_cases_sha256', 'rows', 'families', 'assignment_rule',
                'family_partitions', 'partition_case_ids', 'partition_row_counts', 'partition_family_counts'):
        if frozen.get(key) != expected[key]:
            raise ValueError(f'Frozen collection or family assignments changed: {key}.')
    return frozen


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('cases', type=Path)
    parser.add_argument('manifest', type=Path)
    parser.add_argument('--seed', type=int, default=42)
    parser.add_argument('--verify', action='store_true', help='Verify the reservation without changing it')
    args = parser.parse_args()
    try:
        if args.verify:
            manifest = verify_manifest(args.cases, args.manifest)
        else:
            if args.manifest.exists():
                raise ValueError('Manifest already exists; use --verify or a new versioned path.')
            manifest = build_manifest(args.cases, args.seed)
            args.manifest.parent.mkdir(parents=True, exist_ok=True)
            with args.manifest.open('x', encoding='utf-8') as handle:
                json.dump(manifest, handle, indent=2)
                handle.write('\n')
    except (OSError, ValueError, KeyError, UnicodeError, csv.Error) as error:
        print(f'Error: {error}', file=sys.stderr)
        return 1
    print(json.dumps({'partition_row_counts': manifest['partition_row_counts'],
                      'partition_family_counts': manifest['partition_family_counts'],
                      'labels_pending': manifest['labels_pending'],
                      'independent_audit_established': manifest['independent_audit_established']}, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
