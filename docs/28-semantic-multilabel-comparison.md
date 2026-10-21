# Frozen semantic features for multiple intents

The first controlled semantic comparison improves complete intent-set predictions from **28.49% to 35.81%** on the same 2,008 BlendBanking77 development requests. That is 147 additional fully correct sets, an increase of 7.32 percentage points. The improvement is descriptive development evidence; it is not final-test accuracy or a browser capability claim.

## What changed

The [word baseline](27-first-multilabel-baseline.md) uses TF-IDF. This experiment replaces those features with frozen, unit-normalized, 384-dimensional sentence embeddings from `sentence-transformers/all-MiniLM-L6-v2`, revision `1110a243fdf4706b3f48f1d95db1a4f5529b4d41`. The encoder is not fine-tuned. Inference uses CPU, batches of 64 and a 256-token input limit.

Both systems train independent one-vs-rest logistic-regression heads on the identical 28,338 requests, with C=1, maximum 1,000 iterations and seed 42. Both use independent fixed 0.5 thresholds, allowing multiple labels or an empty set. The word control is recomputed in the same run and reproduces the previously saved report exactly in this environment. All heads converge. No threshold, class weighting, encoder adaptation or hyperparameter search is performed.

The comparison reads only the preparation manifest, training file and selection file. Their fingerprints, row counts, label vocabulary, identities and normalized text groups are validated before fitting. Calibration data and publisher-test payloads are not read by this experiment. Existing Bitext test data and private/reserved review collections remain unused. No trained bundle or browser change is exported.

## Development results

| Metric | Word TF-IDF | Frozen sentence embeddings |
|---|---:|---:|
| Exact label-set accuracy | 28.49% | **35.81%** |
| Micro F1 | 57.53% | **67.28%** |
| Macro F1 | 55.82% | **65.92%** |
| Micro precision | **91.38%** | 89.17% |
| Micro recall | 41.98% | **54.01%** |
| Empty predictions | 31.37% | **12.30%** |
| Mean predicted labels | 0.89 | 1.17 |

Semantic features recover more expected intents and produce fewer empty sets, while adding some incorrect labels. They do not improve every metric. The scores remain uncalibrated; a fixed threshold does not establish a reliability guarantee or out-of-scope detection.

| True intents | Requests | Word: fully correct | Semantic: fully correct |
|---|---:|---:|---:|
| 1 | 539 | 358 (66.42%) | 418 (77.55%) |
| 2 | 1,058 | 205 (19.38%) | 291 (27.50%) |
| 3 | 411 | 9 (2.19%) | 10 (2.43%) |

The three-intent slice remains a major weakness. Its micro F1 rises from 37.55% to 50.64%, but almost every complete set is still wrong. Recovering some labels and recovering every requested intent are different goals. This result supports further development, not automatic routing or deployment.

## Input-length check

The tokenizer audit finds **zero requests over 256 tokens** in either partition. Maximum untruncated lengths are 156 tokens in training and 98 in selection. The configured input limit therefore does not truncate these requests. That excludes one mechanical explanation for these results; it does not prove why the remaining errors occur.

Whole-message pooling may lose distinctions between separate requests, but this is a hypothesis, not a finding established by these aggregate scores. Regularization, fixed thresholds, label imbalance, label noise and feature quality can also affect performance. The same C and threshold make a controlled first comparison; they do not make either feature representation optimally tuned.

## Reproduce

After preparing the [pinned public benchmark](26-action-plan-and-public-benchmark.md), install the optional CPU semantic dependencies:

```bat
python -m pip install torch==2.8.0 --index-url https://download.pytorch.org/whl/cpu
python -m pip install -r requirements-semantic.txt
python -m support_ticket_ai.semantic_multilabel artifacts/blendbanking77-v1 --output artifacts/semantic-multilabel-v1.json
```

Use a fresh output filename. The pinned encoder is downloaded to `artifacts/encoder-cache` if needed. With the complete cache present, `HF_HUB_OFFLINE=1` and `TRANSFORMERS_OFFLINE=1` can enforce an offline run; this recorded experiment ran offline against the cached encoder. No extra Windows setup is needed to keep using the current browser app.

From a phone, the manually triggered **Compare public multilabel semantic features** GitHub Actions workflow performs preparation, tests and the comparison on CPU. It uploads the aggregate report, preparation manifest and source/encoder license notices for seven days. It does not host the application or publish weights. This workflow is provided for reproduction; the recorded measurements are from the local run, not an asserted completed Actions run.

The [aggregate report](../reports/blendbanking77-v1/semantic_multilabel.json) contains the control report, input fingerprints, encoder revision and selected source-file hashes, versions, input-length audit, metrics and limitations. No dataset requests or individual predictions are committed. The comparison module and tests are included in package 0.7.0. The report remains repository documentation rather than an installed package resource.

## Learning and next experiment

The subsequent [class-weight and regularization study](29-semantic-head-study.md) implements the bounded follow-up described below, with its six-setting protocol committed before fitting.

Sentence embeddings help this fixed classifier recover semantic intent signals, but they do not demonstrate complete sentence understanding. In particular, the three-intent results show why adding a semantic encoder alone does not solve compositional routing.

The next bounded study should predeclare a small training/selection protocol for imbalance and regularization, keeping the frozen 0.5 result visible. Reserve calibration data for its stated future purpose and retain the final-test boundary. A later comparison of whole-message and request-local representations could test the pooling hypothesis, provided both use the same data and the localization method is evaluated rather than assumed correct.

The benchmark has 77 native banking labels, distinct from the browser's 11 support categories. Its publisher labels are not independently adjudicated and component/template overlap remains unknown; pretrained-encoder source overlap is also unknown. Label-set scores do not validate action spans, descriptions, negation, conditions or relations. Those remain separate evaluation requirements before integrating the proposed action-plan format. Neither this established method nor this result supports a novelty claim.
