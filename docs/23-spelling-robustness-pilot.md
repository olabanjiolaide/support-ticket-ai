# Frozen semantic and character-feature spelling pilot

The encoder fine-tuning pilot regressed on two typo-heavy development requests. This experiment instead keeps the pretrained sentence encoder frozen and adds spelling-sensitive character features to the category classifier. It uses existing data and requires no manual labeling.

## Fixed comparison

| Component | Semantic reference | Hybrid candidate |
|---|---|---|
| Sentence encoder | Pinned frozen MiniLM, 384 dimensions | Same encoder and same embeddings |
| Character features | None | Character TF-IDF, `char_wb`, lengths 3–5, min_df=2, maximum 50,000 features |
| Category inputs | Unit-normalized sentence embedding | Concatenated semantic and character blocks, then L2-normalized |
| Category classifier | Logistic regression, C=1, max_iter=1000 | Same classifier recipe |
| Category training | All supported training requests | Same requests and labels |
| Scope detector | Semantic logistic head trained on support train plus 48 authored negatives | Exact same fitted scope head and scores |
| Category / scope cutoff | 0.5 / 0.5 | 0.5 / 0.5 |

The character configuration is reused from the earlier character-only experiment, not selected by sweeping this comparison. Character TF-IDF and sentence embeddings each have unit norm where nonzero. Concatenation gives them equal weight; the combined vector is then normalized. If a request contains no known character fragments, the semantic block remains usable. The joint feature matrix stays sparse to avoid a large dense document-by-character matrix.

Characters encode local fragments shared by related spellings. This does not rewrite the input or run automatic spelling correction. The original customer message reaches both feature extractors unchanged.

The shared scope head isolates category-feature changes. Unrelated-request rejection that remains unchanged is not evidence of a better unsupported-request detector. Neither model is trained to identify multiple intents.

## Data boundaries and measurements

The workflow reuses the fine-tuning pilot's input checks: matching train/validation checksums, category coverage, disjoint ticket IDs, and no exact normalized text overlap among train, validation, scope negatives, and development probes. Exact checks do not eliminate template or semantic overlap.

Only train requests fit character vocabulary, IDF, and category heads. Scope negatives fit only the shared semantic scope head. Validation and development cases are transformed and scored after fitting. No private review file or held-out test CSV is opened.

The report includes:

- Synthetic validation macro-F1, class metrics, and confusion matrix.
- Correct top categories and macro-F1 on the 66 supported development requests before abstention.
- Coverage and correctness of accepted suggestions, plus unrelated and ambiguous requests withheld.
- Separate plain, typo, indirect, ambiguity, and unrelated-task slice diagnostics.
- Every development case's top category, uncalibrated score, shared scope score, and acceptance decision.
- Character vocabulary size/hash, feature dimensions, input fingerprints, versions, and encoding/head-fit durations.

There is no parameter sweep, threshold search, encoder update, checkpoint export, or change to the browser. Equal numeric cutoffs are diagnostic; they do not establish matched risk or calibrated probabilities.

## Run the comparison

From the repository root, in the environment that already runs semantic mode:

```bat
python -m support_ticket_ai.hybrid_experiment artifacts/demo-v1/prepared artifacts/hybrid-pilot-v1.json
```

This uses the existing `requirements-semantic.txt` dependencies. Use a fresh report filename per run. For a fully cached encoder without Hub access, the `HF_HUB_OFFLINE=1` environment setting described in [the fine-tuning guide](22-encoder-fine-tuning-pilot.md) also applies.

The manually triggered **Run offline spelling robustness pilot** Actions workflow rebuilds the pinned data and uploads the report. It does not deploy a service or update either browser model.

## Limits

The 98 authored cases have already been inspected and their labels are provisional. They are development diagnostics, not independent estimates of future accuracy. The synthetic validation source may share templates with training. One configuration and seed do not establish general robustness.

The encoder truncates at 256 wordpieces; character features may cover more text. The offline report does not implement the browser's extra truncation-abstention guard and does not measure HTTP latency or concurrent serving. Any serving implementation would need those safeguards and its own checks.

Manual labeling remains paused. These results cannot be used to claim a general solution to ambiguity, unsupported requests, or real customer traffic.

## Recorded result and decision

The [full report](../reports/bitext-baseline-v1/hybrid_pilot.json) records an actual CPU comparison using 16,990 supported training requests and 3,642 validation requests. The fitted character vocabulary contains 8,851 features, so the hybrid has 9,235 input dimensions. The encoder was not fine-tuned.

| Development measurement | Semantic reference | Hybrid candidate |
|---|---:|---:|
| Correct plain top categories before abstention | 22/22 | 22/22 |
| Correct typo top categories before abstention | 16/22 | 17/22 |
| Correct indirect top categories before abstention | 18/22 | 17/22 |
| Total correct supported top categories before abstention | 56/66 | 56/66 |
| Supported macro-F1 before abstention | 0.85193 | 0.85407 |
| Supported requests receiving a suggestion | 52/66 | 47/66 |
| Correct accepted supported suggestions | 49/52 | 45/47 |
| Incorrect accepted supported suggestions | 3 | 2 |
| Unrelated requests withheld by the shared scope policy | 24/24 | 24/24 |
| Ambiguous requests withheld | 3/8 | 4/8 |

Synthetic validation macro-F1 rises from 0.99634 to 0.99890. That increase does not correspond to a gain in total correct supported stress-case categories. The higher correctness fraction among accepted suggestions also comes with lower coverage: the hybrid withholds more correct requests. These are conditional quantities, not interchangeable accuracy measures.

Decision: keep the semantic reference in the browser. The candidate is a useful spelling-feature experiment, not a general prediction upgrade. It repairs the top category of the typo case `can i add an itme to my oder` from FEEDBACK to ORDER, but changes the indirect newsletter request `I no longer want the promotional emails your company keeps sending.` from SUBSCRIPTION to FEEDBACK. Inspect the report's case texts and scores for the precise outcomes; no thresholds were retuned after seeing them.

The additional withheld ambiguous request is the context-free `It does not work.`. This does not establish detection of requests containing two separate actions. Explicit ambiguity handling remains a distinct development task.
