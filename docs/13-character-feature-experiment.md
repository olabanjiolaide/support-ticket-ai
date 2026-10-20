# Word versus character features

## Question and fixed experiment

Can character fragments improve spelling robustness without making unrelated requests more likely to receive a category?

The current model represents words and adjacent word pairs. The candidate instead represents character sequences of length 3–5 inside word boundaries (`char_wb`). A misspelling can destroy a word feature while preserving some character fragments. This is a hypothesis about spelling robustness, not a general solution to scope detection or language understanding.

The candidate uses TF-IDF, at most 50,000 features, `min_df=2`, sublinear term frequency, and the same logistic regression settings as the baseline: C=1, maximum 1,000 iterations, no class weighting, seed 42. Both use the same 16,990 training rows. Character vocabulary and classifier are fitted only on training data. Source validation and the 98 authored probes do not enter fitting. The fixed diagnostic cutoff is 0.70, chosen in the earlier word-model experiment; there is no threshold search here.

This is one exploratory candidate proposed after inspecting word-model failures. It is not a preregistered independent comparison. The report records both configurations, source fingerprints, versions, per-category results, per-slice results, and individual probe scores.

## Results

Full output: [feature comparison JSON](../reports/bitext-baseline-v1/feature_comparison.json).

| Measurement | Word features | Character features |
|---|---:|---:|
| Synthetic validation macro-F1 | 0.99839 | 0.99964 |
| Correct categories among 66 supported probes before abstention | 34/66 | 45/66 |
| Supported probes accepted at 0.70 | 14/66 (21.2%) | 19/66 (28.8%) |
| Correct among accepted supported probes | 14/14 | 19/19 |
| Unrelated probes receiving a category at 0.70 | 4/24 | 3/24 |
| Ambiguous probes withheld at 0.70 | 6/8 | 6/8 |
| Fitted vocabulary size | 10,559 | 8,851 |

The vocabulary cap is a maximum, not a guaranteed vocabulary size. Character fragments are shared between many words.

### Supported requests by writing style

| Slice (22 cases each) | Word: correct before abstention | Character: correct before abstention | Word: accepted at 0.70 | Character: accepted at 0.70 |
|---|---:|---:|---:|---:|
| Plain wording | 18 | 19 | 11 | 9 |
| Typos | 6 | 14 | 1 | 8 |
| Indirect wording | 10 | 12 | 2 | 2 |

The largest observed improvement is on typos. Coverage does not improve on indirect wording and declines on plain wording at this shared cutoff. Raw probability scores are uncalibrated and differ between models: equal numerical cutoffs do not establish equal risk, confidence, or operating conditions.

The character model still gives unrelated tasks high scores:

- “Translate the phrase shipping address into Italian.” → SHIPPING, 0.969.
- “Explain the history of credit card payment networks.” → PAYMENT, 0.822.
- “Invent dialogue for a fictional customer support agent.” → CONTACT, 0.889.

Neither classifier has learned an UNSUPPORTED class. Both are trained to choose among 11 support categories. Character features help some spelling variation but do not establish whether a task belongs within the service's scope.

## Label-review status

On October 20, 2026, the user agreed with three proposed rules: duplicate charge → PAYMENT; actual order cancellation → ORDER; invoice plus cancellation → REVIEW. The answers were shown before agreement, and two statements were paraphrased versions of benchmark intents. Record this as a discussion of the annotation contract, not independent blind review or adjudication of the entire dataset. All 98 shipped probe labels remain provisional.

The counts above describe this authored collection. They do not establish production accuracy, statistical significance, or reliability on future tickets. Repeated intents are correlated. The synthetic source validation also has known template overlap.

## Run locally

After downloading the repository update, from its root in the project environment:

```bat
python -m support_ticket_ai.compare_features artifacts/demo-v1/model artifacts/demo-v1/prepared artifacts/feature-comparison-v1.json
```

The command loads your trusted word-model bundle, verifies the matching prepared-data manifest and train/validation checksums, rejects train/validation overlap and normalized exact probe/train overlap, trains the fixed character candidate in memory, and writes a new report. Use another output filename for a repeat run. It reads train and validation CSVs only; it does not open the held-out test. The candidate weights are not exported or installed, and the live model/policy files are not changed. Windows model serialization fingerprints can differ from the published report while the source data and experiment settings match.

The experiment needs no additional packages beyond `requirements.txt`. Existing report files are preserved. A failure to converge is an error rather than a silently accepted candidate.

## Practical learning

1. **Representation matters:** a lightweight change to text features can recover misspelled requests without a larger language model.
2. **Measure multiple outcomes:** selected accuracy alone hides the 47 of 66 valid requests the character model withholds at 0.70.
3. **Scope is a separate problem:** vocabulary matching cannot reliably distinguish requesting support from writing about support.
4. **Keep experiments separate from deployment:** this result supports further development; a fresh audit is needed before promotion.

The next milestone is a reviewed development collection containing both supported and unsupported tasks, with a separate scope decision and a frozen audit partition. Compare candidates at declared coverage/error criteria using selection data only. Keep the final source test untouched until model and policy choices are settled. A final in-source test will still not prove out-of-scope detection or real-world generalization.
