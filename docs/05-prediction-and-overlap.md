# Predicting new requests and inspecting overlap

## Implemented

- `support_ticket_ai.predict`: loads a trusted local model bundle once and returns a JSON category suggestion.
- Input validation: text must be a nonempty string of at most 2,000 characters.
- Model checks: verifies the recorded scikit-learn version and model checksum before deserialization.
- `support_ticket_ai.audit_overlap`: measures validation-to-training similarity in the baseline's fitted TF-IDF space without reading the test split.

All predictions require human review. The numeric score is explicitly labelled `uncalibrated_probability`; it is not an established probability that the suggestion is correct. There is no automatic-routing threshold or unsupported-request detector yet.

## Run prediction locally

First reproduce the [baseline bundle](04-baseline-results.md).

```bash
python -m support_ticket_ai.predict artifacts/baseline-v1 --text "I was charged twice for my subscription."
```

For interactive input without putting ticket text directly in a shell command:

```bash
python -m support_ticket_ai.predict artifacts/baseline-v1 --stdin
```

Enter the ticket, then end standard input using the terminal's EOF mechanism. The result contains the suggested category, uncalibrated score, human-review requirement, review explanation, and model checksum. It does not echo the ticket text.

Only load model bundles you created or otherwise trust. Joblib deserialization can execute code; a checksum stored beside the model detects inconsistent files but cannot authenticate a malicious bundle. The future API must not accept user-uploaded models.

## A useful failure case

The command above returns ACCOUNT with an uncalibrated score of approximately 0.2601 for the first baseline. A duplicate-charge request would ordinarily be a payment issue. This manually written example is an observed error case, not a new benchmark or test-set result.

This illustrates why near-perfect validation performance on the synthetic source is insufficient for automatic routing. The implementation keeps the suggestion under human review, including for unrelated requests.

## Similarity audit

Run:

```bash
python -m support_ticket_ai.audit_overlap artifacts/bitext-v2 artifacts/baseline-v1 artifacts/overlap-v1.json
```

The command transforms requests using the existing training-fitted vectorizer. It computes each validation request's highest cosine similarity to a training request in batches, limiting the size of the dense pairwise matrix.

Observed on 2026-10-18:

| Diagnostic | Result |
| --- | ---: |
| Validation requests | 3,642 |
| Normalized exact overlap with training | 0 |
| Mean nearest-training cosine similarity | 0.7738 |
| Nearest similarity at least 0.90 | 602 (16.53%) |
| Nearest similarity at least 0.95 | 207 (5.68%) |
| Nearest similarity at least 0.99 | 103 (2.83%) |

The full aggregate report is in `reports/bitext-baseline-v1/overlap_summary.json`. No raw matched ticket pairs are published.

These values measure similarity in the model's feature space, not semantic equivalence or template-family membership. Different strings can have identical TF-IDF vectors when tokenization or the vocabulary discards their differences. Similarity can also reflect legitimate category vocabulary. The diagnostic does not prove how much overlap inflated validation scores.

## Learn from your phone

Compare these two questions:

1. **Did the software behave as designed?** Tests check inputs, bundle verification, split access, and output behavior.
2. **Did the model make the right suggestion?** Evaluation and error analysis address predictive quality.

Passing software tests cannot guarantee correct predictions. Our manual duplicate-charge example demonstrates that distinction.

Next: expose the validated prediction function through an API with request validation and health checks, preserving the human-review requirement.
