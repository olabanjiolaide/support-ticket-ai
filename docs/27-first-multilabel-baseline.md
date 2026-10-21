# First public multilabel baseline

The public-repository review suggested separating several requests instead of forcing one category. We now have a reproducible first experiment that predicts **sets of native banking intents**, plus a separate validated format for richer action proposals. Neither is integrated into the browser yet.

## Recipe and boundaries

The [prepared BlendBanking77 benchmark](26-action-plan-and-public-benchmark.md) supplies 28,338 training requests and 2,008 selection requests across 77 native labels. Word TF-IDF uses unigrams/bigrams, minimum document frequency 2, at most 50,000 features and sublinear term frequency. The fitted vocabulary contains 27,211 features. One-vs-rest logistic regression fits an independent binary head for each label, with C=1, maximum 1,000 iterations and seed 42. All heads converged.

Each head uses a fixed 0.5 threshold. Several labels or an empty set are allowed. This is not top-two selection from a single-label softmax, and the scores are not calibrated. No settings or thresholds were searched in this experiment. A train-only comparator always predicts the most frequent training label, `declined_card_payment`.

The loader reads only the manifest, training file and selection file. It checks their fingerprints, label vocabulary, row counts, unique IDs and normalized text groups before fitting. It fits the TF-IDF vocabulary and all classifier heads on training data only. Calibration, publisher-test payloads, existing Bitext test data and private review files are not read by this experiment. The report contains aggregate results, not requests or individual predictions.

## Development results

| Metric | TF-IDF multilabel baseline | Most-frequent single label |
|---|---:|---:|
| Exact label-set accuracy | 28.49% | 0.35% |
| Micro F1 | 57.53% | 1.93% |
| Macro F1 | 55.82% | 0.07% |
| Micro precision | 91.38% | 2.84% |
| Micro recall | 41.98% | 1.47% |
| Mean predicted labels per request | 0.89 | 1.00 |
| Empty predictions | 31.37% | 0.00% |

Exact-set accuracy requires every expected label and no extra labels. F1 summarizes label precision/recall; micro pools decisions across labels, while macro gives each label equal weight. These are selection results, **not final-test accuracy**.

| True intents | Requests | Exact-set accuracy |
|---|---:|---:|
| 1 | 539 | 66.42% |
| 2 | 1,058 | 19.38% |
| 3 | 411 | 2.19% |

The baseline identifies a concrete weakness: it often omits intents. High precision paired with low recall and many empty sets does not make it reliable for routing. Hamming loss is only 1.56%, but with 77 sparse labels that number hides substantial incomplete-set errors. It should not be used alone to describe quality.

The [aggregate experiment report](../reports/blendbanking77-v1/multilabel_baseline.json) records source/input fingerprints, dependency versions, the complete recipe and results. The publisher uses generated/composed requests with labels that we have not independently adjudicated. Source-component/template overlap remains unknown. These scores do not measure our app's 11 categories, unsupported-request detection, negation, source-span extraction, conditions or relationships.

## Reproduce

After preparing the benchmark and installing the core dependencies:

```bat
python -m support_ticket_ai.multilabel_baseline artifacts/blendbanking77-v1 --output artifacts/multilabel-baseline-v1.json
```

Use a fresh output filename; existing reports are not overwritten. No semantic dependencies or GPU are needed for this baseline. Nothing changes in the local browser and no additional labeling is required.

From a phone, the **Prepare public multilabel benchmark** GitHub Actions workflow can prepare the data and run this baseline with its default `run_baseline` option enabled. Its download includes the aggregate report, prepared partitions, pinned source and attribution/license notices for seven days. Turning the option off performs preparation only. The workflow does not start or host the app.

## Next controlled experiment

Compare frozen sentence embeddings with the same independent binary-head setup and development partitions. Report exact-set accuracy and performance by intent count alongside precision/recall. Keep the fixed-threshold result visible before trying threshold selection; any later selected threshold is a development decision, not evidence of calibrated confidence. Do not use the reserved calibration data for model selection or open the final test to improve the recipe.

Only a measured improvement justifies advancing to semantic adaptation or browser integration. Even a better label-set classifier will not establish faithful action descriptions, correct condition/negation handling or exact source evidence. Those require a separate evaluation protocol. No research novelty is established by this baseline.
