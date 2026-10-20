# Support Ticket AI

A Python portfolio project for classifying support requests and routing uncertain predictions to human review.

**Status: baseline, prediction CLI, local FastAPI service, similarity audit, and offline calibration experiment implemented.** Calibration is not activated in the live prediction interfaces. The test set has not been evaluated. All predictions require human review. Optional experimental abstention can withhold low-scoring category suggestions.

See [the baseline audit and results](docs/04-baseline-results.md). Validation macro-F1 is 0.9984 on a synthetic source; template overlap may inflate this result. It is not a production accuracy claim.

The [prediction and overlap guide](docs/05-prediction-and-overlap.md) documents the command-line interface, similarity measurements, and an observed error on a manually written payment request.

The [API guide](docs/06-prediction-api.md) explains local startup, request validation, and liveness/readiness checks. No hosted service has been deployed.

The [calibration experiment](docs/08-calibration-experiment.md) improved development probability metrics but increased confidence in a known wrong suggestion. Its threshold policy remains an offline simulation.

![Support Ticket AI workspace showing a real local-model prediction](docs/images/workspace.png)

The [abstention experiment](docs/11-experimental-abstention.md) adds an opt-in “No reliable suggestion” outcome. On its small authored audit set it withheld all 12 unrelated requests, but also withheld 8 of 11 valid support requests. It is a score-based baseline, not a general unsupported-request detector.

The [broader robustness diagnostics](docs/12-robustness-diagnostics.md) add 98 provisional stress probes, per-category and writing-style reports, and a label-review protocol. At the frozen 0.70 cutoff, only 14/66 valid probes receive a suggestion and 4/24 unrelated tasks still pass. These diagnostic findings motivate further model work; they are not independent accuracy estimates.

The [character-feature experiment](docs/13-character-feature-experiment.md) compares a fixed spelling-tolerant candidate with the word baseline. Correct categories on provisional supported probes rose from 34/66 to 45/66 before abstention, but coverage and unrelated-task failures remain unresolved. This is an offline experiment; the live model is unchanged.

The [scope-detector experiment](docs/14-scope-detector-experiment.md) adds a separate binary support-scope gate offline. Combined with the word-category cutoff, unrelated false suggestions fall from 4/24 to 1/24 while supported coverage remains 14/66 on existing provisional probes. Negative training examples reflect known failure families, so these are development findings, not independent audit results.

The [frozen semantic-embedding experiment](docs/15-semantic-embedding-experiment.md) improves indirect wording on provisional probes: 18/22 correct versus 10/22 for word features. With a separately selected cutoff and semantic scope gate, it accepts 52/66 valid probes (49 correct) and rejects 24/24 unrelated probes, but accepts 5/8 ambiguous requests. It remains offline, and the guide discloses a training duplicate discovered in the older cutoff-selection collection.

The [human label-review pilot](docs/16-human-label-review.md) collects interpretations of 40 new, unscored requests, five at a time, without model suggestions. It supports one routing intent, multiple routing intents, insufficient context, and unsupported tasks. Human review and adjudication are still pending.

## Run the complete demo

From the repository root, with Python 3.11–3.13 in a virtual environment:

```bash
python -m pip install -r requirements.txt
python -m support_ticket_ai.demo artifacts/demo-v1
python -m support_ticket_ai.serve --model-dir artifacts/demo-v1/model
```

The demo downloads approximately 19 MB of pinned source data, verifies checksums, prepares splits, trains the baseline, and creates a trusted local model bundle. Use a fresh output path on each run. Open http://127.0.0.1:8000/ for the ticket workspace. The developer API reference remains at http://127.0.0.1:8000/docs.

See [complete setup and phone instructions](docs/07-running-the-demo.md). From your phone, the **Build local demo bundle** GitHub Actions workflow can build a downloadable model and reports. This workflow does not host the API.

See [the workspace guide](docs/09-ticket-workspace.md) for examples, result explanations, and updating an existing local checkout without retraining.

## Run the first milestone

Python 3.11–3.13 is supported. The demo loader uses the standard library. Install the pinned dependencies for model training and the full test suite.

```bash
python -m pip install -r requirements.txt
python -m support_ticket_ai data/sample_tickets.csv
python -m unittest discover -s tests -v
```

Run commands from the repository root. The sample-data command prints the number of tickets per category. Invalid data produces an error and a nonzero exit code.

## Data contract

The original demo CSV must contain `ticket_id`, `text`, and `category`. IDs must be unique; every field must be nonempty. Its default categories are `billing`, `account`, and `technical`. Extra columns are permitted and ignored. Files use UTF-8, with an optional byte-order mark.

The trained Bitext model uses the source dataset's 11 categories instead, including ACCOUNT, PAYMENT, and ORDER. The importer preserves those labels and records their vocabulary in the preparation manifest. See [the baseline audit](docs/04-baseline-results.md) for the complete list.

`data/sample_tickets.csv` contains 12 hand-written synthetic examples for demonstrating the loader. It is not a benchmark, training corpus, or evidence of model quality. Do not upload real customer tickets or personal information.

## Planned milestones

1. **Complete:** CSV validation, command-line summary, tests, and an automated test workflow.
2. **Complete:** pinned source import, data audit, provenance manifest, and duplicate-aware splits. See [preparation instructions](docs/03-importing-and-splitting.md).
3. **Complete:** majority-class and TF-IDF/logistic-regression baselines; validation macro-F1, class metrics, and confusion matrix.
4. **Complete locally:** CLI and prediction API, input validation, checked model bundles, versioned output, and health/readiness checks.
5. **Offline experiment complete:** temperature scaling and threshold simulation on disjoint validation subsets; live automatic routing remains disabled.
6. **Complete locally:** pinned-download demo builder, portable server command, limitations guide, and GitHub Actions bundle workflow.

Validation and exploratory calibration metrics are available; held-out test performance and calibration under distribution shift remain unestablished. Workflow status should be checked in the Actions tab.

## Learn from your phone

Read [the first learning guide](docs/01-data-contract.md), inspect `support_ticket_ai/data.py`, and open the repository's Actions tab to see automated checks. A local terminal is optional for reviewing this milestone.

## Layout

- `support_ticket_ai/`: loader and command-line entry point
- `data/`: synthetic demonstration CSV
- `tests/`: validation and command-line behavior checks
- `docs/`: practical learning notes
- `.github/workflows/`: automated checks
