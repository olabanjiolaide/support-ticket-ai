# Support Ticket AI

A Python portfolio project for classifying support requests and routing uncertain predictions to human review.

**Status: milestone 1 — validated data loading.** Model training, confidence calibration, and the prediction API are planned; they are not implemented yet.

## Run the first milestone

Python 3.11 or newer is required. This milestone has no third-party dependencies.

```bash
python -m support_ticket_ai data/sample_tickets.csv
python -m unittest discover -s tests -v
```

Run commands from the repository root. The first command prints the number of tickets per category. Invalid data produces an error and a nonzero exit code.

## Data contract

CSV files must contain `ticket_id`, `text`, and `category`. IDs must be unique; every field must be nonempty. Categories are `billing`, `account`, or `technical`. Extra columns are permitted and ignored. Files use UTF-8, with an optional byte-order mark.

`data/sample_tickets.csv` contains 12 hand-written synthetic examples for demonstrating the loader. It is not a benchmark, training corpus, or evidence of model quality. Do not upload real customer tickets or personal information.

## Planned milestones

1. **Complete:** CSV validation, command-line summary, tests, and an automated test workflow.
2. Select a suitably licensed dataset; document provenance and design leakage-resistant splits.
3. Train a majority-class baseline and a TF-IDF/logistic-regression pipeline; report macro-F1 and per-class errors.
4. Add a prediction API with input validation and versioned model metadata.
5. Evaluate calibration and choose a human-review threshold using validation data.
6. Package a reproducible demo and document limitations.

No accuracy or confidence claims have been established. Workflow status should be checked in the Actions tab.

## Learn from your phone

Read [the first learning guide](docs/01-data-contract.md), inspect `support_ticket_ai/data.py`, and open the repository's Actions tab to see automated checks. A local terminal is optional for reviewing this milestone.

## Layout

- `support_ticket_ai/`: loader and command-line entry point
- `data/`: synthetic demonstration CSV
- `tests/`: validation and command-line behavior checks
- `docs/`: practical learning notes
- `.github/workflows/`: automated checks
