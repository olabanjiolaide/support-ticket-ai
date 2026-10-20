# Prediction API

The service exposes the existing reviewed prediction function through HTTP. It loads a trusted model bundle once per worker during startup and reuses it across requests.

## Endpoints

| Endpoint | Purpose | Responses |
| --- | --- | --- |
| GET / | Ticket workspace with model status and prediction form | Browser interface |
| GET /healthz | Check that the service responds | 200 alive |
| GET /readyz | Check that the model loaded successfully | 200 ready, or 503 unavailable |
| POST /predict | Submit one ticket and receive a category suggestion | 200 prediction, 422 invalid request, 503 unavailable model, 500 inference failure |
| GET /docs | Interactive API documentation | Browser interface |
| GET /openapi.json | Machine-readable API schema | JSON specification |

## Run on a computer

Install `requirements.txt` and reproduce the model bundle using the baseline instructions. The repository does not include model binaries.

For Bash:

```bash
export SUPPORT_TICKET_MODEL_DIR=artifacts/baseline-v1
python -m uvicorn support_ticket_ai.api:app --host 127.0.0.1 --port 8000
```

For Windows PowerShell:

```powershell
$env:SUPPORT_TICKET_MODEL_DIR = "artifacts/baseline-v1"
python -m uvicorn support_ticket_ai.api:app --host 127.0.0.1 --port 8000
```

Open http://127.0.0.1:8000/ for the ticket workspace, or http://127.0.0.1:8000/docs for the developer API reference. This is a local development service, not a published link for your phone. No hosted service has been deployed.

## Request and response

Send POST /predict with Content-Type application/json:

```json
{"text": "I cannot reset my password."}
```

The response contains `suggested_category`, `uncalibrated_probability`, `requires_human_review`, `review_reason`, and `model_sha256`. The review flag is always true. The score is not an established correctness probability, and this API does not automatically route tickets.

Text must be a string with 1–2,000 characters, including any surrounding whitespace; whitespace-only input is rejected. Unknown request fields are rejected. Validation errors omit input values, and predictions do not echo ticket text. Unexpected prediction failures produce a generic error response. The application logs failure types without logging ticket bodies.

The model directory comes from server configuration, never from the HTTP request. The loader checks its checksum and scikit-learn version. Only use trusted bundles: joblib deserialization can execute code, and a colocated checksum is not author authentication.

If configuration is missing or model loading fails, the service remains alive but returns 503 from readiness and prediction endpoints. Correct the configuration or model files and restart the service; there is no automatic reload mechanism.

## Verification

The full local suite contains 36 passing tests at this milestone. API tests cover input validation, malformed JSON, response fields, unavailable model behavior, startup-only loading, cleanup, generic errors, and OpenAPI generation. Model tests still check checksum failures and training/validation isolation.

This is a local portfolio API. Public hosting, authentication, rate limits, deployment-level body limits, and operational monitoring have not been implemented.

## Learn from your phone

Read `support_ticket_ai/api.py` and locate the three endpoint handlers.

**Liveness:** can the process answer a request?

**Readiness:** can it perform its intended work with the model available?

A process may be alive while its model is unavailable. Separate checks let an operator distinguish those situations.

**Interview practice:** “I wrapped the classifier in a validated API, loaded the model once at startup, and separated liveness from readiness so missing model artifacts produce explicit service-unavailable responses.”

Next: package a reproducible local demo and document operating the service before considering deployment.
