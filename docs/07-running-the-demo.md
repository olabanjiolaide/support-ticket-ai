# Run the complete local demo

The demo downloads a pinned Bitext source CSV and its publisher license, checks both SHA-256 fingerprints, prepares deduplicated splits, trains the fixed baseline, and makes a smoke prediction. It does not evaluate the test set.

## Computer setup

Clone the repository or download and extract its ZIP. Open a terminal at the repository root. Use Python 3.11–3.13 and an isolated virtual environment.

Create the environment:

```bash
python -m venv .venv
```

Activate it on Bash:

```bash
source .venv/bin/activate
```

Or on Windows PowerShell:

```powershell
.venv\Scripts\Activate.ps1
```

Then run:

```bash
python -m pip install -r requirements.txt
python -m support_ticket_ai.demo artifacts/demo-v1
python -m support_ticket_ai.serve --model-dir artifacts/demo-v1/model
```

The build needs an internet connection to download approximately 19 MB from the publisher's pinned GitHub revision. A checksum mismatch or oversized download stops the build. Existing output directories are never overwritten. If a build fails, inspect the incomplete directory and choose a new output name when retrying.

The server binds to the local loopback interface. Open http://127.0.0.1:8000/docs on the same computer, expand POST /predict, choose Try it out, and submit:

```json
{"text": "I cannot reset my password."}
```

The baseline should suggest ACCOUNT for this smoke example. Scores may vary slightly across environments. Every suggestion requires human review. Press Ctrl+C in the server terminal to stop it.

## Working from your phone

The GitHub workflow builds a downloadable bundle; it does not host a website or API.

1. Open this repository in your phone's browser and select Actions.
2. Select **Build local demo bundle**.
3. Choose **Run workflow**, keep the main branch, and confirm the run.
4. Open the completed run and find its **Artifacts** section. The bundle name starts with `support-ticket-demo-`.

The workflow also runs automatically when the demo builder or its workflow changes on a push. Artifacts expire after seven days. GitHub sign-in and repository access are required; mobile UI layout can differ.

The artifact includes model files, aggregate validation reports, the preparation manifest, source provenance, and publisher license. Raw source and split CSV files are excluded. Treat the model as a trusted-code artifact and load only a bundle from a run you trust.

A downloaded bundle cannot run directly on a phone without a Python environment. You can inspect its JSON reports now and use the model later on your computer.

## Output layout

| Path inside demo directory | Contents |
| --- | --- |
| source/ | Pinned CSV, license, download timestamp, source URLs and checksums |
| prepared/ | Train/validation/test CSVs, manifest, copied dataset license |
| model/ | Trusted model.joblib and validation_metrics.json |
| demo_summary.json | Completion summary and smoke prediction |

Generated files remain under the ignored artifacts directory. The source revision and source fingerprints are fixed in `support_ticket_ai/demo.py`. Download timestamps change between runs; model bytes may vary across Python or dependency versions even when scores agree.

## Verification at this milestone

The complete command was run on 2026-10-18 using a fresh output directory and real pinned downloads. It retained 24,274 requests and reproduced validation macro-F1 of 0.9983936052. On the same runtime, the model checksum matched the earlier baseline. The produced bundle passed API readiness and prediction checks. The test set remained unevaluated.

The local suite has 41 passing tests, including checksum failures, download-size limits, preservation of existing files, mocked-download pipeline integration with real training, and local server configuration.

## Phone learning task

Open `support_ticket_ai/demo.py` and follow the sequence: download, verify, prepare, train, predict. Explain why verifying source bytes before training helps someone reproduce a result.

An accurate interview description is: “I built a reproducible local demo that pins source data, verifies checksums, trains a baseline, and serves reviewed predictions through a tested API.”

Remaining model work: confidence calibration, unsupported-request detection, stronger template-family evaluation, and a final held-out assessment. Public deployment is separate work.
