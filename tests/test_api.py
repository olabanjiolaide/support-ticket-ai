import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
import joblib
import sklearn

from support_ticket_ai.api import create_app
from support_ticket_ai.predict import TicketPredictor
from support_ticket_ai.train import build_model


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        model = build_model()
        model.fit(["password reset", "password login", "invoice card", "invoice refund"],
                  ["ACCOUNT", "ACCOUNT", "PAYMENT", "PAYMENT"])
        joblib.dump(model, self.root / "model.joblib")
        self.model_sha = hashlib.sha256((self.root / "model.joblib").read_bytes()).hexdigest()
        (self.root / "validation_metrics.json").write_text(json.dumps({
            "versions": {"scikit-learn": sklearn.__version__}, "model_sha256": self.model_sha,
        }))

    def test_health_ready_and_prediction(self):
        with TestClient(create_app(self.root)) as client:
            self.assertEqual(client.get("/healthz").json(), {"status": "alive"})
            self.assertEqual(client.get("/readyz").json()["model_sha256"], self.model_sha)
            response = client.post("/predict", json={"text": "password reset"})
            self.assertEqual(response.status_code, 200)
            body = response.json()
            self.assertEqual(body["suggested_category"], "ACCOUNT")
            self.assertTrue(body["requires_human_review"])
            self.assertNotIn("text", body)

    def test_invalid_requests_rejected_without_echoing_text(self):
        bodies = [{}, {"text": None}, {"text": 123}, {"text": "  "},
                  {"text": "x" * 2001}, {"text": "private request", "secret": "do-not-echo"},
                  {"text": "private request", "check_multiple_requests": True},
                  {"text": "private request", "mode": "semantic", "check_multiple_requests": "true"}]
        with TestClient(create_app(self.root)) as client:
            for body in bodies:
                with self.subTest(keys=list(body)):
                    response = client.post("/predict", json=body)
                    self.assertEqual(response.status_code, 422)
                    self.assertNotIn("private request", response.text)
                    self.assertNotIn("do-not-echo", response.text)
                    self.assertTrue(all("input" not in item for item in response.json()["detail"]))

    def test_malformed_json_rejected(self):
        with TestClient(create_app(self.root)) as client:
            response = client.post("/predict", content='{"text": "sensitive',
                                   headers={"Content-Type": "application/json"})
            self.assertEqual(response.status_code, 422)
            self.assertNotIn("sensitive", response.text)

    def test_unavailable_model_is_alive_but_not_ready(self):
        with self.assertLogs("support_ticket_ai.api", level="ERROR"):
            with TestClient(create_app(self.root / "missing")) as client:
                self.assertEqual(client.get("/healthz").status_code, 200)
                self.assertEqual(client.get("/readyz").status_code, 503)
                response = client.post("/predict", json={"text": "help"})
                self.assertEqual(response.status_code, 503)
                self.assertNotIn(str(self.root), response.text)

    def test_missing_configuration_is_not_ready(self):
        with patch.dict("os.environ", {}, clear=True):
            with TestClient(create_app()) as client:
                self.assertEqual(client.get("/readyz").status_code, 503)

    def test_model_loaded_once_and_released_after_shutdown(self):
        with patch("support_ticket_ai.api.TicketPredictor", wraps=TicketPredictor) as loader:
            application = create_app(self.root)
            with TestClient(application) as client:
                client.post("/predict", json={"text": "password"})
                client.post("/predict", json={"text": "invoice"})
                self.assertEqual(loader.call_count, 1)
            self.assertIsNone(application.state.predictor)

    def test_internal_error_is_generic(self):
        with TestClient(create_app(self.root)) as client:
            with patch.object(TicketPredictor, "predict", side_effect=RuntimeError("private-path")):
                with self.assertLogs("support_ticket_ai.api", level="ERROR"):
                    response = client.post("/predict", json={"text": "password"})
            self.assertEqual(response.status_code, 500)
            self.assertNotIn("private-path", response.text)

    def test_openapi_documents_request_and_response(self):
        with TestClient(create_app(self.root)) as client:
            response = client.get("/openapi.json")
            self.assertEqual(response.status_code, 200)
            self.assertIn("/predict", response.json()["paths"])
            self.assertIn("PredictionResponse", response.json()["components"]["schemas"])

    def test_diagnostics_versions_asset_identity_and_no_private_paths(self):
        from support_ticket_ai.version import __version__
        with TestClient(create_app(self.root)) as client:
            diagnostic = client.get('/diagnostics')
            data = diagnostic.json()
            self.assertEqual(data['application_version'], __version__)
            self.assertEqual(client.get('/openapi.json').json()['info']['version'], __version__)
            self.assertEqual(data['models']['word']['model_sha256'], self.model_sha)
            self.assertFalse(data['models']['semantic']['loaded'])
            self.assertNotIn(str(self.root), diagnostic.text)
            self.assertNotIn('password', diagnostic.text)
            html = client.get('/')
            self.assertIn(f'/assets/{data["frontend_build"]}/app.js', html.text)
            self.assertIn(f'content="{data["frontend_build"]}"', html.text)
            for path in ['/', '/diagnostics', '/assets/app.js', f'/assets/{data["frontend_build"]}/breakdown.js']:
                self.assertEqual(client.get(path).headers['cache-control'], 'no-store')
            # Relative module imports resolve inside the same content-addressed graph.
            self.assertEqual(client.get(f'/assets/{data["frontend_build"]}/evidence-edit.js').status_code, 200)

    def test_workspace_and_local_assets_are_served(self):
        with TestClient(create_app(self.root)) as client:
            response = client.get("/")
            self.assertEqual(response.status_code, 200)
            self.assertIn("text/html", response.headers["content-type"])
            self.assertIn('id="ticket-form"', response.text)
            self.assertIn('type="module"', response.text)
            for path, media_type in [("/assets/styles.css", "text/css"),
                                     ("/assets/app.js", "javascript"),
                                     ("/assets/result-view.js", "javascript"),
                                     ("/assets/workspace.js", "javascript")]:
                asset = client.get(path)
                self.assertEqual(asset.status_code, 200)
                self.assertIn(media_type, asset.headers["content-type"])
            self.assertEqual(client.get("/docs").status_code, 200)

    def test_workspace_available_when_model_is_not_configured(self):
        with patch.dict("os.environ", {}, clear=True):
            with TestClient(create_app()) as client:
                self.assertEqual(client.get("/").status_code, 200)
                self.assertEqual(client.get("/readyz").status_code, 503)
                self.assertEqual(client.get("/assets/../api.py").status_code, 404)

    def test_optional_policy_returns_abstention_with_nullable_category(self):
        (self.root / "abstention_policy.json").write_text(json.dumps({
            "policy_version": 1, "kind": "experimental_max_probability", "threshold": 1.0,
            "model_sha256": self.model_sha, "human_review_required": True,
        }))
        with TestClient(create_app(self.root)) as client:
            response = client.post("/predict", json={"text": "password reset"})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["decision"], "abstain")
            self.assertIsNone(response.json()["suggested_category"])
            self.assertTrue(response.json()["requires_human_review"])
