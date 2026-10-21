"""Prepare a pinned public multilabel benchmark; do not decode or score test requests."""

import argparse
import ast
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import re
import shutil
import sys
import tempfile
import urllib.request

from .prepare import normalize
from .resources import data_path

SOURCE_CONFIG = data_path('blendbanking77_source.json')
PREFIX = re.compile(rb'^\{\s*"domain_id"\s*:\s*"(banking77\.[0-9]+)"\s*,\s*"split"\s*:\s*"(train|dev|test)"\s*,')
MAX_DOWNLOAD_BYTES = 16 * 1024 * 1024


def sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def parse_development(raw: bytes):
    """Inspect metadata prefix only for test lines; leave their JSON payload opaque."""
    records, sealed = [], []
    counts, ids = Counter(), set()
    for line in raw.splitlines(keepends=True):
        match = PREFIX.match(line)
        if not match:
            raise ValueError('Unexpected publisher JSONL metadata prefix.')
        source_id, split = [part.decode('ascii') for part in match.groups()]
        counts[split] += 1
        if split == 'test':
            sealed.append(line)
            continue
        row = json.loads(line)
        if (set(row) != {'domain_id', 'split', 'utterance', 'intent'} or
                row['domain_id'] != source_id or row['split'] != split or
                not isinstance(row['utterance'], str) or not row['utterance'].strip() or
                not isinstance(row['intent'], str) or len(row['intent']) > 10000):
            raise ValueError('Invalid development record.')
        # The publisher stores a Python-list literal inside a JSON string. Never eval().
        try:
            labels = ast.literal_eval(row['intent'])
        except (ValueError, SyntaxError, RecursionError) as error:
            raise ValueError('Invalid intent-list literal.') from error
        if (not isinstance(labels, list) or not 1 <= len(labels) <= 77 or
                any(not isinstance(label, str) or not re.fullmatch(r'[A-Za-z][A-Za-z0-9_?]*', label) for label in labels) or
                len(set(labels)) != len(labels)):
            raise ValueError('Labels must be a nonempty list of distinct publisher label names.')
        key = (split, source_id)
        if key in ids:
            raise ValueError('Duplicate development source ID within a publisher split.')
        ids.add(key)
        records.append({'case_id': f'blendbanking77:{split}:{source_id}',
                        'publisher_split': split, 'text': row['utterance'], 'labels': sorted(labels),
                        'text_group_sha256': sha256(normalize(row['utterance']).encode())})
    if any(counts[name] == 0 for name in ('train', 'dev', 'test')):
        raise ValueError('Publisher source must include train, dev, and opaque test records.')
    return records, b''.join(sealed), dict(counts)


def partition_development(records, seed=42):
    groups = defaultdict(list)
    for row in records:
        groups[normalize(row['text'])].append(row)
    partitions = {'train': [], 'calibration': [], 'selection': []}
    audit = {'conflicting_text_groups_quarantined': 0, 'conflicting_rows_quarantined': 0,
             'duplicate_rows_removed': 0, 'train_dev_overlap_groups': 0}
    for text, rows in sorted(groups.items()):
        if len({tuple(row['labels']) for row in rows}) != 1:
            audit['conflicting_text_groups_quarantined'] += 1
            audit['conflicting_rows_quarantined'] += len(rows)
            continue
        audit['duplicate_rows_removed'] += len(rows) - 1
        dev = [row for row in rows if row['publisher_split'] == 'dev']
        if dev:
            if len(dev) < len(rows):
                audit['train_dev_overlap_groups'] += 1
            # Prefer dev, removing matching train/calibration text rather than leaking it.
            retained = min(dev, key=lambda r: r['case_id'])
            name = 'selection'
        else:
            retained = min(rows, key=lambda r: r['case_id'])
            bucket = int(sha256(f'{seed}\0{text}'.encode()), 16) % 10000
            name = 'calibration' if bucket < 2000 else 'train'
        partitions[name].append(retained)
    for rows in partitions.values():
        rows.sort(key=lambda r: r['case_id'])
        if not rows:
            raise ValueError('Development partition is empty.')
    vocabulary = {label for row in partitions['train'] for label in row['labels']}
    for name in ('selection', 'calibration'):
        seen = {label for row in partitions[name] for label in row['labels']}
        if seen != vocabulary:
            raise ValueError(f'{name} label coverage differs from train; do not silently reshuffle.')
    return partitions, audit, sorted(vocabulary)


def prepare(output: Path, source_dir: Path | None = None, *, config=None) -> dict:
    if output.exists():
        raise ValueError('Benchmark directory already exists; choose a fresh version.')
    config = config if config is not None else json.loads(SOURCE_CONFIG.read_text(encoding='utf-8'))
    if config['schema_version'] != 1:
        raise ValueError('Unsupported source metadata version.')
    if config['source_filename'] not in config['files']:
        raise ValueError('Dataset filename must be one of the pinned source files.')
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=output.parent) as directory:
        stage = Path(directory)
        source = stage / 'source'
        source.mkdir()
        for name, metadata in config['files'].items():
            if Path(name).name != name:
                raise ValueError('Source filename must not contain a path.')
            if source_dir is None:
                if not metadata['url'].startswith('https://raw.githubusercontent.com/'):
                    raise ValueError('Only pinned upstream HTTPS file URLs are supported.')
                with urllib.request.urlopen(metadata['url'], timeout=30) as response:
                    raw = response.read(MAX_DOWNLOAD_BYTES + 1)
            else:
                raw = (source_dir / name).read_bytes()
            if len(raw) > MAX_DOWNLOAD_BYTES or len(raw) != metadata['bytes'] or sha256(raw) != metadata['sha256']:
                raise ValueError(f'Source checksum/size mismatch: {name}.')
            (source / name).write_bytes(raw)
        raw = (source / config['source_filename']).read_bytes()
        records, sealed, prefix_counts = parse_development(raw)
        partitions, audit, vocabulary = partition_development(records)
        if len(vocabulary) != config['expected_label_count']:
            raise ValueError('Unexpected publisher taxonomy size.')
        output_hashes = {}
        for name, rows in partitions.items():
            path = stage / f'{name}.jsonl'
            path.write_text(''.join(json.dumps(r, sort_keys=True, ensure_ascii=False) + '\n' for r in rows), encoding='utf-8', newline='\n')
            output_hashes[path.name] = sha256(path.read_bytes())
        (stage / 'sealed_test.jsonl').write_bytes(sealed)
        output_hashes['sealed_test.jsonl'] = sha256(sealed)
        manifest = {
            'schema_version': 1, 'dataset': config['dataset'], 'taxonomy_id': config['taxonomy_id'],
            'source_revision': config['source_revision'], 'source_path': config['source_path'],
            'source_config': config, 'source_config_sha256': sha256(json.dumps(config, sort_keys=True).encode()),
            'seed': 42, 'label_vocabulary': vocabulary, 'publisher_split_prefix_counts': prefix_counts,
            'partition_policy': 'Publisher dev -> selection; normalized exact-text train groups reserve 20% by seeded hash for calibration. Conflicts quarantined; duplicate dev text preferred over train.',
            'partition_counts': {name: len(rows) for name, rows in partitions.items()},
            'label_counts': {name: dict(sorted(Counter(label for row in rows for label in row['labels']).items()))
                             for name, rows in partitions.items()},
            'label_cardinality_counts': {name: dict(sorted(Counter(len(row['labels']) for row in rows).items()))
                                         for name, rows in partitions.items()},
            'audit': audit, 'files_sha256': output_hashes,
            'test_payload_decoded': False, 'test_evaluated': False, 'test_overlap_audited': False,
            'model_trained': False, 'live_model_changed': False,
            'limitations': [
                'Raw publisher download contains all splits. Test lines are copied/hashed using only their metadata prefix; utterances and intent payloads are not JSON-decoded, inspected, or scored.',
                'Test JSON validity and train/test textual or source-component overlap are not audited at this stage.',
                'Exact normalized-text grouping is not a guarantee of independent composition families or templates.',
                'Publisher domain IDs identify blended rows, not their original component-utterance IDs.',
                'Native 77 banking labels are not mapped to the app taxonomy. No source spans, negation, conditions, or action relations are supplied by these labels.',
                'Publisher labels are reused without adjudication; generated combinations can contain noise.',
                'Preparation and calibration reservation do not establish measured performance or calibration.',
            ],
        }
        (stage / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
        (stage / 'ATTRIBUTION.txt').write_text(
            f"BlendX / BlendBanking77: {config['source_repository']}\nRevision: {config['source_revision']}\n"
            'Yoon et al., BlendX: Complex Multi-Intent Detection with Blended Patterns, LREC-COLING 2024.\n'
            'https://aclanthology.org/2024.lrec-main.218/\n'
            'Underlying BANKING77: PolyAI, Casanueva et al., Efficient Intent Detection with Dual Sentence Encoders, 2020.\n'
            'https://github.com/PolyAI-LDN/task-specific-datasets\n'
            'Publisher and underlying license copies are in source/. See manifest for metadata/checksums.\n'
            'Transformation: development-only deduplication/quarantine and hash-based calibration reservation. Test payloads remain opaque.\n', encoding='utf-8')
        output.mkdir()
        try:
            for item in stage.iterdir():
                target = output / item.name
                shutil.copytree(item, target) if item.is_dir() else shutil.copyfile(item, target)
        except OSError:
            shutil.rmtree(output)
            raise
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    parser.add_argument('--source-dir', type=Path, help='Optional directory of the exact pinned source/license files')
    args = parser.parse_args()
    try:
        report = prepare(args.output, args.source_dir)
    except (OSError, ValueError, KeyError, UnicodeError) as error:
        print(f'Benchmark preparation failed: {error}', file=sys.stderr)
        return 1
    print(json.dumps({key: report[key] for key in ('dataset', 'partition_counts', 'audit', 'test_payload_decoded', 'test_evaluated')}, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
