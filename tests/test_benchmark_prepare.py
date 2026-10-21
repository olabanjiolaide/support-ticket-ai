import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from support_ticket_ai.benchmark_prepare import (parse_development, partition_development,
                                                prepare, sha256)


class BenchmarkPreparationTests(unittest.TestCase):
    def source(self):
        rows = []
        for index in range(100):
            rows.append({'domain_id': f'banking77.{index + 1}', 'split': 'train',
                         'utterance': f'Please assist with unique request {index}',
                         'intent': repr(['account_help'] if index % 2 else ['payment_help', 'account_help'])})
        for index in range(8):
            rows.append({'domain_id': f'banking77.{200 + index}', 'split': 'dev',
                         'utterance': f'Different validation wording {index}',
                         'intent': repr(['account_help', 'payment_help'])})
        raw = ''.join(json.dumps(row) + '\n' for row in rows).encode()
        # A sentinel payload proves test JSON is not decoded, even for validation.
        return raw + b'{"domain_id":"banking77.999","split":"test","utterance":DO_NOT_DECODE_TEST_PAYLOAD}\n'

    def config(self, root, raw=None):
        source = root / 'source'
        source.mkdir()
        raw = self.source() if raw is None else raw
        values = {'BlendBanking77.jsonl': raw, 'LICENSE.txt': b'Synthetic test fixture license'}
        for name, data in values.items():
            (source / name).write_bytes(data)
        config = {'schema_version': 1, 'dataset': 'Fixture', 'taxonomy_id': 'fixture-multilabel',
                  'source_repository': 'https://github.com/HYU-NLP/BlendX', 'source_revision': 'a' * 40,
                  'source_path': 'fixture.jsonl', 'source_filename': 'BlendBanking77.jsonl',
                  'expected_label_count': 2, 'files': {name: {'url': 'https://raw.githubusercontent.com/fixture',
                  'sha256': sha256(data), 'bytes': len(data)} for name, data in values.items()}}
        return source, config

    def test_opaque_test_copy_and_all_learning_partitions_are_disjoint(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, config = self.config(root)
            output = root / 'prepared'
            original_loads = json.loads
            decoded = []
            def guarded_loads(value, *args, **kwargs):
                self.assertNotIn(b'DO_NOT_DECODE_TEST_PAYLOAD', value if isinstance(value, bytes) else value.encode())
                decoded.append(value)
                return original_loads(value, *args, **kwargs)
            with patch('support_ticket_ai.benchmark_prepare.json.loads', side_effect=guarded_loads):
                report = prepare(output, source, config=config)
            self.assertEqual(len(decoded), 108)
            self.assertFalse(report['test_payload_decoded'])
            self.assertFalse(report['test_evaluated'])
            self.assertFalse(report['test_overlap_audited'])
            self.assertEqual(report['publisher_split_prefix_counts']['test'], 1)
            self.assertIn(b'DO_NOT_DECODE_TEST_PAYLOAD', (output / 'sealed_test.jsonl').read_bytes())
            groups = []
            for split in ('train', 'calibration', 'selection'):
                self.assertNotIn(b'\r\n', (output / f'{split}.jsonl').read_bytes())
                rows = [json.loads(line) for line in (output / f'{split}.jsonl').read_text().splitlines()]
                groups.append({r['text_group_sha256'] for r in rows})
                self.assertTrue(all(r['labels'] == sorted(r['labels']) for r in rows))
            for i, first in enumerate(groups):
                for second in groups[i + 1:]:
                    self.assertFalse(first & second)

    def test_duplicates_group_conflicts_quarantine_and_development_preferred(self):
        rows, _, _ = parse_development(self.source())
        sample = copy.deepcopy(rows[0])
        sample.update(case_id='new-dev-copy', publisher_split='dev')
        rows.append(sample)
        conflict = copy.deepcopy(rows[1])
        conflict.update(case_id='conflict-copy', labels=['payment_help'])
        rows.append(conflict)
        partitions, audit, _ = partition_development(rows)
        self.assertEqual(audit['train_dev_overlap_groups'], 1)
        self.assertEqual(audit['conflicting_rows_quarantined'], 2)
        self.assertIn('new-dev-copy', {r['case_id'] for r in partitions['selection']})
        self.assertFalse({r['case_id'] for r in partitions['train'] + partitions['calibration']} & {rows[0]['case_id']})
        reversed_partitions, reversed_audit, _ = partition_development(list(reversed(rows)))
        self.assertEqual(partitions, reversed_partitions)
        self.assertEqual(audit, reversed_audit)

    def test_intent_literals_never_execute_and_duplicate_labels_are_rejected(self):
        raw = self.source()
        original_line = raw.splitlines()[0]
        for bad in ("__import__('os').system('echo unsafe')", "['account_help', 'account_help']", "[]"):
            row = json.loads(original_line)
            row['intent'] = bad
            changed = json.dumps(row).encode() + b'\n' + b'\n'.join(raw.splitlines()[1:]) + b'\n'
            with self.assertRaises(ValueError):
                parse_development(changed)

    def test_source_checksum_failure_precedes_parsing_and_preserves_existing_output(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, config = self.config(root)
            output = root / 'prepared'
            (source / config['source_filename']).write_bytes(b'changed')
            with patch('support_ticket_ai.benchmark_prepare.parse_development') as parse:
                with self.assertRaisesRegex(ValueError, 'checksum'):
                    prepare(output, source, config=config)
                parse.assert_not_called()
            self.assertFalse(output.exists())
            output.mkdir()
            (output / 'keep.txt').write_text('original')
            with self.assertRaisesRegex(ValueError, 'already exists'):
                prepare(output, source, config=config)
            self.assertEqual((output / 'keep.txt').read_text(), 'original')
