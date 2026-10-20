# Evaluate the reconciled review pilot

## Purpose and boundaries

The user completed 40 annotation-pilot cases. After discussing nine proposed corrections and one account/agent routing-rule change, a separate reconciled version contains 24 single-intent, four multiple-intent, four insufficient-context, and eight unsupported requests. Ten label assignments changed. Human-assistance preference is recorded on two account requests. The final eight unsupported labels were completed with assistant guidance.

These are user/assistant-reconciled development labels, not independently adjudicated ground truth. The author of the synthetic texts also proposed corrections. No statistical significance or production reliability claim is appropriate.

This evaluator reconstructs the semantic category and scope heads using the **previously frozen recipe and source training data**, with the same frozen pretrained sentence encoder. It never fits on the 40 pilot labels. It loads the original word model and checks its recipe. It imports each category cutoff from the earlier semantic experiment report:

| Policy | Category cutoff | Scope cutoff |
|---|---:|---:|
| Word category only | 0.70 | None |
| Semantic category only | 0.90 | None |
| Semantic category plus scope gate | 0.50 | 0.50 |

Cutoff selection is disabled in this mode. No pilot labels, audit rows, or exposed mistakes are used to adjust thresholds. The evaluator checks the prepared-data fingerprint, seed, baseline configuration, review completeness, and review provenance. The original semantic experiment command retains its earlier development-selection behavior when frozen thresholds are not supplied.

The source held-out test remains unopened, candidate weights are not exported, and the live app is unchanged.

## How to read the metrics

Single-intent cases have one target category. Report accepted coverage and correctness among accepted cases together. Multiple-intent and insufficient-context cases are scored separately as cases where a single-category suggestion should be withheld. Unsupported requests also should be withheld.

Existing models produce one category and optional abstention; they have no dedicated classifier for multiple intents or insufficient context. An abstention does not demonstrate that the model recognized *why* it should withhold. The human-assistance annotation is not currently predicted by the live API.

The generated report includes counts by all four intent types. Its aggregate results omit reviewer names, timestamps, notes, and individual annotations. File hashes identify the private input and frozen recipe. The annotation file is not committed to the public repository.

## Observed results on the reconciled pilot

These are assisted development-label counts, not independent test accuracy. The original review and reconciled annotations remain private; the public report contains aggregate metrics and hashes.

| Frozen policy | Single-intent accepted | Correct among accepted | Multiple-intent withheld | Insufficient-context withheld | Unsupported withheld |
|---|---:|---:|---:|---:|---:|
| word: category_only | 4/24 | 2/4 | 3/4 | 4/4 | 6/8 |
| semantic: category_only | 8/24 | 8/8 | 3/4 | 4/4 | 7/8 |
| semantic: with_scope | 24/24 | 20/24 | 1/4 | 2/4 | 8/8 |

Full aggregate output: [reviewed-pilot evaluation report](../reports/bitext-baseline-v1/review_pilot_evaluation.json).

The correct-accepted column is conditional on receiving a suggestion. High conditional correctness can coexist with withholding many valid requests. For multi-intent and insufficient-context rows, the desired single-category interface behavior is abstention; a passing scope gate alone does not resolve them. Thresholds were copied from the earlier report without re-selection or adjustment based on these results.

## What these counts show

The conservative semantic policy accepts only 8 of 24 single-intent requests, all correctly. The semantic policy with scope and the lower frozen category cutoff accepts all 24, but four categories are wrong. That policy also passes three of four multiple-intent cases and two of four insufficient-context cases. Rejecting all eight unrelated tasks does not resolve those errors.

The word policy makes two wrong suggestions among only four accepted single-intent requests. Earlier high selected accuracy on a different development collection therefore did not transfer to this pilot. Before abstention, word categories match 15/24 single-intent labels and semantic categories match 20/24. These observations reinforce the need to evaluate wording variation and multiple error types rather than rely on synthetic validation macro-F1.

Do not lower or raise cutoffs to make these exposed results look better and then claim this pilot as independent evaluation. A separate, more varied and reviewed collection is needed for developing explicit intent-type handling and evaluating it on reserved scenario families.

## Run locally

From the updated repository root, with the reconciled JSON under `artifacts/`, use the separate semantic environment described in [the semantic experiment guide](15-semantic-embedding-experiment.md):

```bat
conda activate support-ticket-semantic
python -m support_ticket_ai.evaluate_review artifacts/demo-v1/model artifacts/demo-v1/prepared artifacts/review-ola-v2-reconciled.json artifacts/review-evaluation-v1.json
```

If you have not created that environment, follow the optional dependency installation in the linked guide. It is separate from the working demo environment. Initial installation may download CPU Torch and encoder weights; the encoder cache is reused afterward.

Use a fresh output filename when repeating a run. The evaluator preserves the input review file. It rejects incomplete sessions and the original unreconciled `v1` status; supply the separate reconciled `v2` file. Model bundle serialization can differ between Windows and Linux, so the evaluator checks the known baseline configuration and matching prepared-data recipe rather than requiring the same joblib bytes across platforms. The trusted model bundle's own checksum and scikit-learn version are still verified.

The command encodes source train and validation texts and the evaluation collection, then fits category/scope heads on their original training inputs only. Encoding a pilot text is feature extraction, not training on its label. The regular test suite uses a deterministic fake encoder without network access; a real encoder evaluation is reported separately.

## Interpretation and next action

This pilot can reveal whether multiple-intent and insufficient-context requests still receive a single category. It cannot establish a deployable ambiguity detector. Do not silently train on these rows and keep calling them an audit. They are now inspected development examples.

Before training an intent-type classifier or SetFit candidate, clarify the annotation rules, obtain more varied reviewed examples, and reserve separate scenario families for evaluation before fitting. Keep assisted/reconciled provenance visible. The next candidate must improve ambiguity handling while preserving useful coverage on genuine single-intent requests.
