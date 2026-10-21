import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
import sklearn
from fastapi.testclient import TestClient

import test_compare_features as fixtures
from support_ticket_ai.api import create_app
from support_ticket_ai.semantic_bundle import (SemanticPredictor, build_bundle, metadata_fingerprint)
from support_ticket_ai.evaluate_review import FROZEN_REPORT_PATH
from support_ticket_ai.resources import report_path


class FakeLocalEncoder:
    def encode(self, texts, **kwargs):
        values = np.zeros((len(texts), 384))
        for i, text in enumerate(texts):
            lower = text.lower()
            index = 0 if 'password' in lower or 'account' in lower else 1 if 'payment' in lower or 'invoice' in lower else 2
            values[i, index] = 1
        return values

    def tokenizer(self, text, **kwargs):
        return {'input_ids': [1] * (len(text.split()) + 2)}

    def save_pretrained(self, directory, **kwargs):
        path = Path(directory)
        path.mkdir()
        (path / 'config.json').write_text('{"unit_test_fixture": true}')


class SemanticBundleTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.prepared, self.word, _ = fixtures.FeatureComparisonTests().fixture(self.root)
        self.output = self.root / 'semantic'
        prior = json.loads(FROZEN_REPORT_PATH.read_text())
        self.prior = self.root / 'frozen.json'
        self.prior.write_text(json.dumps(prior))
        expected_manifest = self.prepared / 'manifest.json'
        actual_report_path = report_path
        def references(name):
            return expected_manifest if name == 'preparation_manifest.json' else actual_report_path(name)
        with patch('support_ticket_ai.semantic_bundle.FROZEN_REPORT_PATH', self.prior), \
                patch('support_ticket_ai.semantic_bundle.report_path', side_effect=references), \
                patch('support_ticket_ai.semantic_bundle.load_encoder', return_value=FakeLocalEncoder()), \
                patch('support_ticket_ai.semantic_bundle.version', side_effect=lambda name: sklearn.__version__ if name == 'scikit-learn' else 'unit-test'):
            (self.prepared / 'validation.csv').unlink()  # builder reads training only; test.csv already removed.
            with patch('builtins.print'):
                self.metadata = build_bundle(self.prepared, self.output, self.root / 'cache')

    def load(self, path=None):
        return SemanticPredictor(path or self.output, encoder_factory=lambda _: FakeLocalEncoder())

    def update_metadata(self, **values):
        self.metadata.update(values)
        self.metadata['model_sha256'] = metadata_fingerprint(self.metadata)
        (self.output / 'semantic_model.json').write_text(json.dumps(self.metadata))

    def test_roundtrip_local_bundle_suggests_and_requires_review(self):
        predictor = self.load()
        result = predictor.predict('password reset')
        self.assertEqual(result['suggested_category'], 'ACCOUNT')
        self.assertTrue(result['requires_human_review'])
        self.assertIsInstance(result['scope_score'], float)
        self.assertFalse(result['input_truncated'])
        self.assertTrue((self.output / 'encoder/LICENSE.txt').is_file())

    def test_scope_rejection_and_long_input_never_produce_a_category(self):
        self.update_metadata(scope_threshold=1.0)
        result = self.load().predict('password reset')
        self.assertEqual(result['decision'], 'abstain')
        self.assertIn('scope', result['review_reason'])
        long = self.load().predict('x ' * 260)
        self.assertTrue(long['input_truncated'])
        self.assertIsNone(long['suggested_category'])
        self.assertIn('truncated', long['review_reason'])

    def test_tampered_encoder_is_rejected_before_loading_pickle(self):
        (self.output / 'encoder/config.json').write_text('tampered')
        with patch('support_ticket_ai.semantic_bundle.joblib.load') as unpickle:
            with self.assertRaisesRegex(ValueError, 'checksum'):
                self.load()
            unpickle.assert_not_called()

    def test_invalid_threshold_and_metadata_identity_fail(self):
        self.update_metadata(category_threshold=float('nan'))
        with self.assertRaisesRegex(ValueError, 'threshold'):
            self.load()
        self.update_metadata(category_threshold=.5, encoder_revision='wrong')
        with self.assertRaisesRegex(ValueError, 'metadata'):
            self.load()

    def test_builder_never_overwrites_existing_bundle(self):
        before = (self.output / 'semantic_model.json').read_bytes()
        with self.assertRaisesRegex(ValueError, 'already exists'):
            build_bundle(self.prepared, self.output, self.root / 'cache')
        self.assertEqual((self.output / 'semantic_model.json').read_bytes(), before)

    def test_api_mode_is_explicit_and_word_remains_default(self):
        real_loader = SemanticPredictor
        with patch('support_ticket_ai.semantic_bundle.SemanticPredictor', side_effect=lambda path: real_loader(path, encoder_factory=lambda _: FakeLocalEncoder())) as loader:
            with TestClient(create_app(self.word, self.output)) as client:
                self.assertEqual(client.get('/models').json()['default'], 'word')
                self.assertTrue(all(item['available'] for item in client.get('/models').json()['modes']))
                self.assertEqual(client.get('/readyz?mode=semantic').status_code, 200)
                default = client.post('/predict', json={'text': 'password reset'}).json()
                semantic = client.post('/predict', json={'text': 'password reset', 'mode': 'semantic'}).json()
                self.assertEqual(default['model_mode'], 'word')
                self.assertEqual(semantic['model_mode'], 'semantic')
                self.assertEqual(semantic['suggested_category'], 'ACCOUNT')
                self.assertTrue(semantic['requires_human_review'])
                self.assertEqual(loader.call_count, 1)
                self.assertEqual(client.post('/predict', json={'text': 'x', 'mode': 'unknown'}).status_code, 422)

    def test_missing_semantic_never_falls_back_to_word(self):
        with TestClient(create_app(self.word)) as client:
            self.assertEqual(client.get('/readyz?mode=semantic').status_code, 503)
            self.assertEqual(client.post('/predict', json={'text': 'password reset', 'mode': 'semantic'}).status_code, 503)
            self.assertEqual(client.post('/predict', json={'text': 'password reset'}).status_code, 200)

    def test_optional_request_guard_withholds_without_changing_model_score(self):
        with patch('support_ticket_ai.semantic_bundle.SemanticPredictor', side_effect=lambda path: self.load(path)):
            with TestClient(create_app(self.word, self.output)) as client:
                body = {'text': 'Change my account name and send my payment invoice.', 'mode': 'semantic'}
                original = client.post('/predict', json=body).json()
                self.assertEqual(original['decision'], 'suggestion')
                self.assertFalse(original['multiple_request_check_enabled'])
                response = client.post('/predict', json={**body, 'check_multiple_requests': True})
                self.assertEqual(response.status_code, 200)
                guarded = response.json()
                self.assertTrue(guarded['multiple_request_check_enabled'])
                self.assertTrue(guarded['multiple_requests_detected'])
                self.assertEqual(guarded['request_check_version'], 1)
                self.assertEqual(guarded['decision'], 'abstain')
                self.assertIsNone(guarded['suggested_category'])
                for field in ('model_top_category', 'uncalibrated_probability', 'model_sha256'):
                    self.assertEqual(guarded[field], original[field])
                self.assertTrue(guarded['requires_human_review'])
                same = client.post('/predict', json={'text': 'Change my account name and reset my password.',
                                                      'mode': 'semantic', 'check_multiple_requests': True}).json()
                self.assertEqual(same['decision'], 'suggestion')
                self.assertFalse(same['multiple_requests_detected'])

    def test_failed_semantic_loading_does_not_break_word_mode(self):
        with self.assertLogs('support_ticket_ai.api', level='ERROR'):
            with TestClient(create_app(self.word, self.root / 'missing')) as client:
                self.assertEqual(client.get('/readyz').status_code, 200)
                self.assertEqual(client.get('/readyz?mode=semantic').status_code, 503)
                self.assertEqual(client.get('/').status_code, 200)
