"""Build and serve an opt-in, self-contained frozen semantic demo bundle."""

import argparse
from collections import Counter
import hashlib
from importlib.metadata import version
import json
import math
from pathlib import Path
import shutil
import sys
import tempfile
import threading
import warnings

import joblib
import numpy as np
import sklearn
from sklearn.exceptions import ConvergenceWarning
from sklearn.linear_model import LogisticRegression

from .data import load_tickets
from .evaluate_review import FROZEN_REPORT_PATH, frozen_thresholds
from .predict import MAX_TEXT_LENGTH
from .prepare import normalize
from .resources import report_path
from .robustness import fingerprint, load_probes
from .scope_experiment import NEGATIVES_PATH
from .semantic_experiment import DIMENSIONS, ENCODER_ID, ENCODER_REVISION, encode, load_encoder

MODEL_NAME = 'Semantic encoder + scope gate (experimental)'


def metadata_fingerprint(metadata: dict) -> str:
    values = {key: value for key, value in metadata.items() if key != 'model_sha256'}
    return hashlib.sha256(json.dumps(values, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def file_manifest(root: Path) -> dict:
    files = {}
    for path in sorted(root.rglob('*')):
        if path.is_symlink():
            raise ValueError('Model bundles cannot contain symlinks.')
        if path.is_file() and path != root / 'semantic_model.json':
            files[path.relative_to(root).as_posix()] = fingerprint(path)
    return files


def newline_equivalent_checksum(path: Path, expected: str) -> bool:
    # Authored single-line CSV requests can have Git checkout LF/CRLF differences.
    raw = path.read_bytes()
    lf = raw.replace(b'\r\n', b'\n')
    return expected in {hashlib.sha256(value).hexdigest() for value in (raw, lf, lf.replace(b'\n', b'\r\n'))}


def build_bundle(prepared_dir: Path, output: Path, cache_dir: Path) -> dict:
    if output.exists():
        raise ValueError('Semantic bundle already exists; choose a fresh version directory.')
    frozen = json.loads(FROZEN_REPORT_PATH.read_text(encoding='utf-8'))
    thresholds = frozen_thresholds(frozen)
    manifest = json.loads((prepared_dir / 'manifest.json').read_text(encoding='utf-8'))
    expected_manifest = json.loads(report_path('preparation_manifest.json').read_text(encoding='utf-8'))
    if manifest != expected_manifest or manifest['seed'] != frozen['seed']:
        raise ValueError('Use the matching pinned demo prepared data for this frozen semantic recipe.')
    train_path = prepared_dir / 'train.csv'
    if fingerprint(train_path) != manifest['split_sha256']['train']:
        raise ValueError('Training checksum mismatch.')
    if not newline_equivalent_checksum(NEGATIVES_PATH, frozen['negatives_sha256']):
        raise ValueError('Scope negative examples differ from the frozen recipe.')
    categories = set(manifest['audit']['categories'])
    train = load_tickets(train_path, categories=frozenset(categories))
    negatives = load_probes(NEGATIVES_PATH, categories)
    if ({row.category for row in train} != categories or
            any(row['expected_category'] != 'UNSUPPORTED' for row in negatives) or
            {normalize(r.text) for r in train} & {normalize(r['text']) for r in negatives}):
        raise ValueError('Invalid training categories or supported/negative overlap.')
    threshold = thresholds['semantic']['with_scope']
    if threshold is None:
        raise ValueError('Frozen experiment did not select a semantic scope policy.')
    encoder = load_encoder(cache_dir)
    print(f'Encoding {len(train)} training requests; no validation, test, or human-review labels are fitted.', flush=True)
    supported = encode(encoder, [row.text for row in train])
    outside = encode(encoder, [row['text'] for row in negatives])
    category = LogisticRegression(C=1.0, max_iter=1000, random_state=manifest['seed'])
    scope = LogisticRegression(C=1.0, max_iter=1000, random_state=manifest['seed'], class_weight='balanced')
    with warnings.catch_warnings():
        warnings.simplefilter('error', ConvergenceWarning)
        category.fit(supported, [row.category for row in train])
        scope.fit(np.concatenate([supported, outside]), ['SUPPORTED'] * len(train) + ['UNSUPPORTED'] * len(negatives))
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=output.parent) as temporary:
        stage = Path(temporary) / 'bundle'
        stage.mkdir()
        joblib.dump({'category': category, 'scope': scope}, stage / 'heads.joblib')
        encoder.save_pretrained(str(stage / 'encoder'), safe_serialization=True)
        shutil.copyfile(Path(__file__).resolve().parent / 'encoder_license.txt', stage / 'encoder/LICENSE.txt')
        shutil.copyfile(report_path('DATA_LICENSE.txt'), stage / 'DATA_LICENSE.txt')
        (stage / 'ENCODER_NOTICE.txt').write_text(
            f'Encoder: {ENCODER_ID}\nRevision: {ENCODER_REVISION}\nSource: https://huggingface.co/{ENCODER_ID}\n'
            'Encoder license: Apache-2.0 (encoder/LICENSE.txt).\n'
            'Authored scope negatives are synthetic development examples; no reliability claim.\n', encoding='utf-8')
        metadata = {
            'schema_version': 1, 'kind': 'frozen_semantic_with_scope', 'name': MODEL_NAME,
            'encoder_id': ENCODER_ID, 'encoder_revision': ENCODER_REVISION,
            'dimensions': DIMENSIONS, 'max_sequence_length': 256,
            'category_threshold': threshold, 'scope_threshold': frozen['scope_head']['scope_cutoff'],
            'human_review_required': True, 'categories': sorted(categories),
            'training_counts': dict(Counter(row.category for row in train)), 'unsupported_training_rows': len(negatives),
            'frozen_report_sha256': fingerprint(FROZEN_REPORT_PATH),
            'training_sha256': fingerprint(train_path), 'negatives_sha256': fingerprint(NEGATIVES_PATH),
            'versions': {p: version(p) for p in ('scikit-learn', 'sentence-transformers', 'transformers', 'torch')},
            'files': file_manifest(stage),
            'limitations': 'Experimental uncalibrated suggestions. Multiple intents and insufficient context are not reliably detected.',
        }
        metadata['model_sha256'] = metadata_fingerprint(metadata)
        (stage / 'semantic_model.json').write_text(json.dumps(metadata, indent=2) + '\n', encoding='utf-8')
        output.mkdir()  # Exclusive destination: never overwrite an existing bundle.
        try:
            for child in stage.iterdir():
                destination = output / child.name
                shutil.copytree(child, destination) if child.is_dir() else shutil.copyfile(child, destination)
        except OSError:
            shutil.rmtree(output)
            raise
    return metadata


def load_local_encoder(path: Path):
    try:
        import torch
        from sentence_transformers import SentenceTransformer
    except ImportError as error:
        raise ValueError('Install requirements-semantic.txt to enable semantic mode.') from error
    torch.set_num_threads(2)
    encoder = SentenceTransformer(str(path), device='cpu', local_files_only=True, trust_remote_code=False,
                                  model_kwargs={'use_safetensors': True})
    encoder.max_seq_length = 256
    encoder.eval()
    for parameter in encoder.parameters():
        parameter.requires_grad_(False)
    return encoder


class SemanticPredictor:
    """Load only a trusted bundle you built; checksums check consistency, not authorship."""

    def __init__(self, model_dir: Path, *, encoder_factory=None):
        self.metadata = json.loads((model_dir / 'semantic_model.json').read_text(encoding='utf-8'))
        m = self.metadata
        if (not isinstance(m, dict) or type(m.get('schema_version')) is not int or m['schema_version'] != 1 or
                m.get('kind') != 'frozen_semantic_with_scope' or m.get('human_review_required') is not True or
                m.get('model_sha256') != metadata_fingerprint(m) or
                m.get('encoder_id') != ENCODER_ID or m.get('encoder_revision') != ENCODER_REVISION or
                m.get('dimensions') != DIMENSIONS or m.get('max_sequence_length') != 256):
            raise ValueError('Invalid semantic model metadata.')
        for key in ('category_threshold', 'scope_threshold'):
            value = m.get(key)
            if type(value) not in (float, int) or not math.isfinite(value) or not 0 < value <= 1:
                raise ValueError('Invalid semantic policy threshold.')
        if m['versions']['scikit-learn'] != sklearn.__version__:
            raise ValueError('Semantic heads require the recorded scikit-learn version.')
        if encoder_factory is None:
            for package in ('sentence-transformers', 'transformers', 'torch'):
                if version(package).split('+')[0] != m['versions'][package].split('+')[0]:
                    raise ValueError(f'Semantic bundle requires its recorded {package} version.')
        if not isinstance(m.get('files'), dict) or file_manifest(model_dir) != m['files']:
            raise ValueError('Semantic bundle file checksum mismatch.')
        heads = joblib.load(model_dir / 'heads.joblib')
        self.category, self.scope = heads['category'], heads['scope']
        if (not isinstance(self.category, LogisticRegression) or not isinstance(self.scope, LogisticRegression) or
                sorted(self.category.classes_) != m['categories'] or set(self.scope.classes_) != {'SUPPORTED', 'UNSUPPORTED'} or
                self.category.n_features_in_ != DIMENSIONS or self.scope.n_features_in_ != DIMENSIONS):
            raise ValueError('Semantic heads do not match the expected recipe.')
        self.encoder = (encoder_factory or load_local_encoder)(model_dir / 'encoder')
        self.lock = threading.Lock()

    def predict(self, text: str) -> dict:
        if not isinstance(text, str) or not text.strip() or len(text) > MAX_TEXT_LENGTH:
            raise ValueError(f'Use a nonempty request of at most {MAX_TEXT_LENGTH} characters.')
        with self.lock:
            truncated = len(self.encoder.tokenizer(text.strip(), add_special_tokens=True, truncation=False)['input_ids']) > 256
            embedding = encode(self.encoder, [text.strip()])
            scores = self.category.predict_proba(embedding)[0]
            scope_score = float(self.scope.predict_proba(embedding)[0][list(self.scope.classes_).index('SUPPORTED')])
        index = int(np.argmax(scores))
        category, score = str(self.category.classes_[index]), float(scores[index])
        rejected_scope = scope_score < self.metadata['scope_threshold']
        abstain = truncated or rejected_scope or score < self.metadata['category_threshold']
        reason = ('The encoder input was truncated; read the full request and choose manually.' if truncated else
                  'The experimental scope gate withheld this request; review its intent manually.' if rejected_scope else
                  'The experimental category cutoff withheld the suggestion; choose manually.' if abstain else
                  'Experimental semantic suggestion. Confirm the category; multiple or unclear intents may still pass.')
        return {'suggested_category': None if abstain else category, 'model_top_category': category,
                'decision': 'abstain' if abstain else 'suggestion',
                'abstention_threshold': self.metadata['category_threshold'], 'uncalibrated_probability': score,
                'scope_score': scope_score, 'scope_threshold': self.metadata['scope_threshold'],
                'input_truncated': truncated, 'requires_human_review': True,
                'review_reason': reason, 'model_sha256': self.metadata['model_sha256']}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('prepared_dir', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--cache-dir', type=Path, default=Path('artifacts/encoder-cache'))
    args = parser.parse_args()
    try:
        metadata = build_bundle(args.prepared_dir, args.output, args.cache_dir)
    except (OSError, ValueError, KeyError, ImportError, ConvergenceWarning) as error:
        print(f'Error: {error}', file=sys.stderr)
        return 1
    print(f"Semantic bundle ready: {args.output}\nBundle SHA256: {metadata['model_sha256']}\nHuman review required for every suggestion.")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
