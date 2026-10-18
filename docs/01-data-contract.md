# Milestone 1: define the data contract

## What we built

The loader turns CSV rows into immutable `Ticket` objects. It checks the inputs and stops with a useful error when a required rule is broken. The command-line entry point summarizes valid data without printing ticket text.

## Why this matters

A classifier trained with missing labels or duplicated IDs can produce misleading results. Validation makes assumptions explicit before training begins. Unique IDs alone do not prevent duplicated text or leakage between train and test sets; we will address those during dataset selection.

## Read these parts on your phone

1. Open `data/sample_tickets.csv`. Identify the input (`text`) and the training target (`category`). `ticket_id` is an identifier, not a prediction feature.
2. Open `support_ticket_ai/data.py`. Find the check for repeated IDs. Notice that it happens after whitespace is stripped.
3. Open `tests/test_data.py`. Compare a valid record with the duplicate-ID test.
4. Open Actions. A green workflow means these checks passed on the configured Python versions; it does not prove model quality.

## Small exercise

Before changing code, predict what happens if a category is changed from `billing` to `payments`. Find the test that demonstrates the answer. Then explain why silently accepting a misspelled label would be a problem.

## Interview practice

“I started with a validated data contract so invalid labels and duplicate identifiers are caught before training. Next I will establish a baseline and a reproducible evaluation split.”

## Next milestone

Choose a dataset after checking its license, label definitions, and duplicate records. Keep an untouched test set, use validation data for development, and compare the classifier with a simple majority-class predictor.
