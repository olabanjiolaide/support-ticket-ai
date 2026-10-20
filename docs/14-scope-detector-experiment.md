# Separate scope detection from category prediction

## What changed in this experiment

The category model answers “which of these 11 support categories fits best?” It was never trained to answer “is this actually a support request?” This experiment adds a separate binary scope classifier, trained to distinguish SUPPORTED from UNSUPPORTED.

The category classifier remains the existing word-based model. The character-category candidate from the previous experiment is not included here. No weights or policy files are exported or installed. The final held-out source test remains untouched; the scope command also does not read source validation.

## Fixed design

- Positive scope training examples: all 16,990 supported requests from the matching source training split.
- Negative scope training examples: 48 assistant-authored provisional unrelated tasks, including 24 general tasks and 24 tasks mentioning support vocabulary.
- Features: a union of word TF-IDF 1–2 grams and within-word character TF-IDF 3–5 grams, at most 20,000 features per branch, minimum document frequency 1, sublinear term frequency, default unit branch weights.
- Classifier: logistic regression, C=1, maximum 1,000 iterations, seed 42, `class_weight='balanced'` because the negative class is much smaller.
- Scope threshold: fixed at 0.50 before scoring, with equality accepted.
- Category threshold: existing 0.70, with equality accepted.
- Evaluation: the existing 98 provisional development probes, not a new independent audit.

Both vocabularies and the binary classifier are fitted on scope training texts only. The evaluator checks fingerprints, matching category coverage, and normalized exact overlap between negatives, supported training texts, and evaluation probes. It does not certify template-family independence.

Balanced class weights give the two classes equal total loss weight; they do not create varied negative examples, make scores calibrated, or reproduce the prevalence of unrelated requests in future traffic.

## Three policies, measured separately

1. **Category cutoff only:** current word-category score must be at least 0.70.
2. **Scope gate only:** binary scope score must be at least 0.50; accept the top category regardless of its category score.
3. **Combined:** both conditions must pass. This can only preserve or reduce the suggestions accepted by the category cutoff; it cannot improve category coverage by itself.

Category and scope scores are stored separately. Their product is not treated as a calibrated joint probability.

Full report: [scope experiment JSON](../reports/bitext-baseline-v1/scope_experiment.json).

| On the 98 provisional development probes | Category cutoff only | Scope gate only | Combined |
|---|---:|---:|---:|
| Supported requests receiving a category | 14/66 | 65/66 | 14/66 |
| Correct among selected supported requests | 14/14 | 33/65 | 14/14 |
| Incorrect selected supported categories | 0 | 32 | 0 |
| Unrelated requests receiving a category | 4/24 | 6/24 | 1/24 |
| Unrelated requests withheld | 20/24 | 18/24 | 23/24 |
| Ambiguous requests withheld | 6/8 | 0/8 | 6/8 |

The combined policy removes three of the four exposed unrelated false suggestions while retaining the same 14 supported suggestions. It still withholds 52 valid supported probes. The scope gate alone has much higher supported coverage but permits 32 category errors: accepting a support request does not mean routing it correctly.

The remaining unrelated combined false suggestion is “Make a crossword clue whose answer is refund.” → REFUND, category score 0.747, scope score 0.550. Do not add a special-case rule for this sentence or tune the threshold against it and then present this collection as untouched evaluation.

The scope gate rejects one valid probe: “Your colleague was exceptionally helpful and I want that praise recorded.” (FEEDBACK; scope score 0.416). The old category cutoff already withheld it, so it does not reduce combined coverage on this collection. This is still a scope false rejection worth tracking.

## Important limits of the result

The 48 negatives were deliberately authored after inspecting earlier failure families. Evaluation texts are not fitted directly, but negative training phrases resemble some evaluation tasks, such as translation requests containing shipping vocabulary. These measurements are useful development feedback and may be optimistic. There is no family-disjoint or independently labeled scope audit yet. All negative and probe labels remain provisional.

Eight REVIEW probes contain multiple intents or insufficient context. They are excluded from supported category accuracy and unsupported rejection. A scope gate is not a multi-intent resolver: it accepts all eight when used alone.

These are descriptive counts from one fixed configuration and seed. There is no significance claim, real-world accuracy estimate, or guarantee that human review can be removed. This milestone does not justify installing the detector in the live app.

## Reproduce locally

From the repository root with a previously built demo bundle:

```bat
python -m support_ticket_ai.scope_experiment artifacts/demo-v1/model artifacts/demo-v1/prepared artifacts/scope-v1.json
```

The command uses the existing pinned requirements. Choose a new output filename for repeated runs. Optional `--negatives PATH` and `--probes PATH` support explicitly versioned collections. The command loads only a trusted local model bundle and the matching prepared manifest/train CSV, fits the scope candidate in memory, and preserves all existing model and policy files.

## Practical learning and next decision

This experiment separates two errors: **scope errors** accept unrelated tasks, while **routing errors** choose the wrong category for real support requests. A successful scope gate does not establish routing correctness, and perfect selected routing accuracy on a small collection does not establish useful coverage.

Before deployment, create a separately reviewed scope dataset, reserve complete task families for audit before training, and freeze both feature and threshold choices on development data. Include unfamiliar support wording, multilingual or mixed-language requests, fragments, quoted text, multiple intents, and unsupported tasks without explicit “write” or “translate” instructions. Do not reuse the current probes as a final test. Compare category-only and combined policies on the fresh audit, including per-category coverage and unsupported false suggestions.

Keep this work bounded: the portfolio already demonstrates reproducible training, API serving, a usable interface, error analysis, and two offline model experiments. Documenting these limits and obtaining a defensible audit is more valuable than continuing to tune against the same 98 examples.
