# Optional semantic mode in the browser

The frozen semantic model can now be used in the local ticket workspace. **Word baseline remains the default.** A model selector offers **Semantic · experimental** only when its bundle has loaded successfully. Every suggestion still requires human review. No further manual labeling is needed to enable this mode.

The semantic mode uses the frozen MiniLM sentence encoder, a category head, and a binary support-scope head. It uses the previously selected category cutoff 0.50 and scope cutoff 0.50. It does not add a reliable multi-intent or clarification classifier. See the [semantic experiment](15-semantic-embedding-experiment.md) and [reviewed-pilot results](17-reviewed-pilot-evaluation.md) for the remaining errors.

An unchecked [experimental separate-request option](24-separate-request-check.md) is now available in semantic mode. It uses bounded English rules and existing clause predictions to withhold some messages containing separate requests. It is not a trained general multi-intent detector, and enabling it does not rebuild or change the model bundle.

## One-time setup on Windows

Run from `C:\Users\User\support-ticket-ai`. Stop the current server with Ctrl+C. If the prompt says `(support-ticket-ai)`, deactivate to the base environment before pulling, because Git was unavailable in that environment on this computer:

```bat
conda deactivate
git pull --ff-only
```

If already in `(base)`, start with `git pull --ff-only`.

Use a separate Python 3.12 environment for semantic dependencies. If it already exists, activate it instead of creating it again:

```bat
conda create -n support-ticket-semantic python=3.12 -y
conda activate support-ticket-semantic
python -m pip install torch==2.8.0 --index-url https://download.pytorch.org/whl/cpu
python -m pip install -r requirements-semantic.txt
```

This installs the pinned CPU packages without needing a GPU. Torch and the initial encoder download are larger than the core app dependencies. Your existing word-model files are preserved.

## Build the semantic bundle once

Use the existing prepared data created by your pinned demo run:

```bat
python -m support_ticket_ai.semantic_bundle artifacts/demo-v1/prepared artifacts/semantic-v1
```

The builder checks the logical preparation manifest and training checksum against the frozen recipe. JSON newline differences between Windows and Linux are tolerated through parsed-manifest comparison. For the authored, single-line scope-negative CSV it accepts equivalent LF/CRLF serialization; changed text still fails the frozen-source checksum check.

Only source training tickets and the existing 48 authored scope negatives are fitted. The builder does not read validation/test CSVs or fit user review labels, and it performs no threshold selection. It stores a new self-contained encoder plus category/scope heads, checksums, metadata, upstream dataset license, and encoder license/attribution. An existing output directory is never overwritten; use another versioned path for a deliberate rebuild.

If the matching prepared data is not available, create a fresh pinned demo first with `python -m support_ticket_ai.demo artifacts/demo-v2`, then use its `prepared` and `model` directories consistently. Do not substitute an unrelated dataset and reuse the frozen cutoffs.

## Start the two-model workspace

```bat
python -m support_ticket_ai.serve --model-dir artifacts/demo-v1/model --semantic-model-dir artifacts/semantic-v1
```

Open http://127.0.0.1:8000/. Select **Semantic · experimental** in the **Prediction model** control. The active-model text and experimental notice identify this mode. Editing text or switching modes clears the previous visible result. Model switching is disabled while a prediction is in flight.

After building, serving loads the local encoder with local-files-only enabled; it does not fetch weights at prediction time. Both models load once per process. Semantic encoding is serialized inside that process to bound local CPU contention. Concurrency and production throughput are not established.

If semantic mode is not configured or its bundle fails checks, the option remains unavailable. The word model stays available if its own bundle is healthy. Explicit semantic API requests return 503 rather than silently falling back to word predictions.

## What to try

Try a short request with indirect wording and compare both modes. Results can differ, and semantic mode is not guaranteed to improve every sentence. A known duplicate-charge example can still be withheld. An invoice-plus-order-cancellation request can still receive a single category: the interface warns that multiple or unclear intents may pass.

The category score and scope score are **uncalibrated model outputs**, not correctness probabilities. Scope scores and the active mode appear in the JSON details. If an input exceeds the encoder's 256-wordpiece limit, the output is withheld and `input_truncated=true`; the review reason tells you to read the full request manually. The 2,000-character API limit still applies separately.

## API additions (version 0.3)

`POST /predict` accepts an optional `mode` field: `word` or `semantic`. Omitting it preserves word mode.

```json
{"text": "I cannot reset my password.", "mode": "semantic"}
```

Responses retain the existing fields and add `model_mode`, `model_name`, nullable `scope_score`/`scope_threshold`, and `input_truncated`. `GET /models` lists available modes. `GET /readyz?mode=semantic` checks the selected mode; plain `/readyz` remains the word-model check. Unsupported mode names fail validation. Environment-based startup may set `SUPPORT_TICKET_MODEL_DIR` and optional `SUPPORT_TICKET_SEMANTIC_MODEL_DIR` when running uvicorn directly.

The semantic bundle fingerprint covers its metadata and file checksums. Encoder files are checked before loading; heads require the recorded scikit-learn version, and semantic runtime packages must match the recorded versions (platform-local Torch suffixes are ignored). Like the existing joblib bundle, this must be a model you built or otherwise trust: checksums establish consistency, not author authenticity.

## Phone/build alternative

The **Build semantic browser demo** GitHub Actions workflow builds both bundles and runs real browser checks. It can be run manually and also runs when its builder, browser checker, or workflow changes. Its downloadable artifact contains `demo-v1/model`, `semantic-v1`, licenses/provenance, and browser-check output. It is retained for seven days and does not host the app.

Extract it under a fresh folder such as `artifacts/browser-demo-v1`, preserve the two bundle directories intact, then start with:

```bat
python -m support_ticket_ai.serve --model-dir artifacts/browser-demo-v1/demo-v1/model --semantic-model-dir artifacts/browser-demo-v1/semantic-v1
```

The optional semantic dependencies are still needed on the serving PC. A Windows-local build is preferable when runtime versions or platform serialization differ.

## Verification and scope

Unit tests use generated tiny heads and a fake encoder to check checksum failures, invalid metadata, scope rejection, input truncation, explicit model routing, default word behavior, and no fallback. The real pinned encoder has also been built and served locally, and Chromium checks exercise both modes at desktop/mobile widths, mode changes, actual predictions, abstention, and overlong encoder input. Installed-wheel/browser checks continue to exercise the core app with semantic mode absent.

This is an opt-in local demonstration, not automatic ticket routing or a public deployment. The pending annotation collection remains paused. No private MuFedSL code or user annotation records are included in the downloadable bundles.
