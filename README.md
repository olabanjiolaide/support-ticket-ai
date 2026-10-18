# Support Ticket AI

A Python portfolio project for classifying support requests and routing uncertain predictions to human review.

**Status: first baseline trained and evaluated on validation data.** Prediction API and confidence calibration are pending. The test set has not been evaluated.

See [the baseline audit and results](docs/04-baseline-results.md). Validation macro-F1 is 0.9984 on a synthetic source; template overlap may inflate this result. It is not a production accuracy claim.

## Run the first milestone

Python 3.11–3.13 is supported. The demo loader uses the standard library. Install the pinned dependencies for model training and the full test suite.

```bash
python -m pip install -r requirements.txt
python -m support_ticket_ai data/sample_tickets.csv
python -m unittest discover -s tests -v
```

Run commands from the repository root. The first command prints the number of tickets per category. Invalid data produces an error and a nonzero exit code.

## Data contract

CSV files must contain `ticket_id`, `text`, and `category`. IDs must be unique; every field must be nonempty. Categories are `billing`, `account`, or `technical`. Extra columns are permitted and ignored. Files use UTF-8, with an optional byte-order mark.

`data/sample_tickets.csv` contains 12 hand-written synthetic examples for demonstrating the loader. It is not a benchmark, training corpus, or evidence of model quality. Do not upload real customer tickets or personal information.

## Planned milestones

1. **Complete:** CSV validation, command-line summary, tests, and an automated test workflow.
2. **Complete:** pinned source import, data audit, provenance manifest, and duplicate-aware splits. See [preparation instructions](docs/03-importing-and-splitting.md).
3. **Complete:** majority-class and TF-IDF/logistic-regression baselines; validation macro-F1, class metrics, and confusion matrix.
4. Add a prediction API with input validation and versioned model metadata.
5. Evaluate calibration and choose a human-review threshold using validation data.
6. Package a reproducible demo and document limitations.

Validation metrics are available; test performance and probability calibration have not been established. Workflow status should be checked in the Actions tab.

## Learn from your phone

Read [the first learning guide](docs/01-data-contract.md), inspect `support_ticket_ai/data.py`, and open the repository's Actions tab to see automated checks. A local terminal is optional for reviewing this milestone.

## Layout

- `support_ticket_ai/`: loader and command-line entry point
- `data/`: synthetic demonstration CSV
- `tests/`: validation and command-line behavior checks
- `docs/`: practical learning notes
- `.github/workflows/`: automated checks
