# Semantic class weights and regularization

This bounded follow-up asks whether the frozen semantic classifier's missing intents can be reduced by changing its binary heads. It does not change the encoder, threshold, dataset partitions or live app.

## Protocol fixed before candidate fitting

The [six-candidate protocol](../data/semantic_head_protocol.json) was committed in [9174862](https://github.com/olabanjiolaide/support-ticket-ai/commit/9174862db9e3997e90862cb9f5dce9ed09eecbbe) before these fits ran. The protocol was designed after observing the [first semantic comparison](28-semantic-multilabel-comparison.md); this is not a preregistered study on unseen data. Its input hashes and reference-report hash identify that development context.

The grid is C in {0.1, 1, 10}, crossed with class weights {none, balanced}. All six settings use a fixed 0.5 decision threshold, seed 42 and at most 1,000 iterations. The C=1 unweighted setting is the original semantic control. The winner is selected by exact-set accuracy, then micro F1, then micro precision, then earlier protocol order. No extra settings or thresholds are added after observing the grid results.

Smaller C means stronger regularization: the classifier is penalized more heavily for large coefficients. Larger C relaxes that penalty. Balanced weighting gives positive and negative classes equal aggregate training weight separately for each one-vs-rest intent head. It uses training prevalence, not selection labels. Reweighted scores must not be interpreted as calibrated probabilities under the original prevalence.

The same pinned, frozen MiniLM encoder produces one set of normalized 384-dimensional features for training and one for selection, shared by all candidates. Heads fit on 28,338 training requests and are scored on 2,008 selection requests across 77 native banking labels. Neither probability calibration nor encoder adaptation is performed.

## Selection results

| C | Class weights | Exact-set accuracy | Micro F1 | Precision | Recall |
|---:|---|---:|---:|---:|---:|
| 0.1 | none | 18.13% | 34.99% | 92.50% | 21.58% |
| 0.1 | balanced | 3.59% | 45.89% | 30.67% | 91.15% |
| 1 | none (original control) | 35.81% | 67.28% | 89.17% | 54.01% |
| 1 | balanced | 8.52% | 51.99% | 36.47% | 90.48% |
| **10** | **none (selected)** | **42.23%** | **73.09%** | **85.66%** | **63.73%** |
| 10 | balanced | 14.84% | 54.55% | 39.52% | 88.01% |

The declared rule selects **C=10 without class balancing**, still at threshold 0.5. Complete-set accuracy increases by 6.42 percentage points, from 719 to 848 fully correct requests out of 2,008. Micro F1 increases by 5.81 points and recall by 9.72 points, while precision falls by 3.52 points. Macro F1 reaches 72.50%; empty predictions fall from 12.30% to 5.63%.

All six fits converge. The original C=1 unweighted control reproduces its earlier metrics exactly in this environment, and the encoder file fingerprints also match. Neither partition has any requests over the configured 256-token limit.

| True intents | Requests | Original semantic control | Selected C=10 |
|---|---:|---:|---:|
| 1 | 539 | 418 correct (77.55%) | 429 correct (79.59%) |
| 2 | 1,058 | 291 correct (27.50%) | 389 correct (36.77%) |
| 3 | 411 | 10 correct (2.43%) | 30 correct (7.30%) |

Weaker regularization helps this fixed representation recover more labels. That supports regularization as one factor in the earlier misses; it does not isolate their entire cause. Balanced weights strongly increase recall but lower precision and complete-set accuracy at every tested C. With the fixed threshold, they add too many labels to be selected. This does not establish that all class-balancing methods or calibrated weighting policies would fail.

Three-intent complete-set accuracy remains only 7.30%, despite micro F1 of 62.32% on that slice. More labels are being recovered, but most complete sets are still wrong. The selected C is the largest tested value; no optimum beyond this small grid is established. The grid is not expanded after observing this endpoint result.

## What the study can establish

The selected recipe has been chosen on reused development data. Its score is a development selection result, not an unbiased accuracy estimate, a significance result or a production guarantee. The candidate table should remain visible so readers can inspect precision/recall trade-offs and weaker outcomes as well as the selected one.

These are established classifier techniques; the study makes no NLP-method novelty claim. C=10 without balancing can serve as a fixed development comparator for a later request-local representation study. That study must evaluate its localization method and preserve the final-test boundary, rather than assuming that splitting text solves references, conditions or negation.

A change in C or class weights cannot establish faithful action descriptions, source spans, conditions, negation handling or relations. Better label-set predictions also do not validate unsupported-request detection. The benchmark's 77 banking labels remain separate from the browser's 11 support categories. Publisher labels are not independently adjudicated, and composition-family and pretrained-source overlap remain unknown.

The experiment reads the manifest, training file, selection file and protocol only, plus the frozen encoder's files. It does not read calibration data, publisher-test payloads, Bitext test data or paused private/reserved reviews. The raw public source still contains all publisher splits, as documented in the [preparation boundary](26-action-plan-and-public-benchmark.md); this study does not open that source. No models, embeddings or per-request predictions are exported by the study, and the browser is unchanged.

## Reproduce without additional labeling

With prepared benchmark data and the existing optional semantic dependencies:

```bat
python -m support_ticket_ai.semantic_head_study artifacts/blendbanking77-v1 --output artifacts/semantic-head-study-v1.json
```

The default protocol is included in the installed package. Input fingerprints must match; changing the grid, threshold or selection rule causes the runner to fail rather than silently running a different study. Use a fresh output filename. The encoder is downloaded to the usual cache if missing; the recorded run used the cached pinned encoder with offline mode enabled.

The manually triggered **Compare semantic class weights and regularization** GitHub Actions workflow performs tests, preparation and the six fits on CPU. It uploads aggregate results, protocol, preparation manifest and attribution/license notices for seven days. This workflow provides reproduction from a phone; the recorded report comes from the local run, not an asserted completed Actions run. No Windows installation or additional user labeling is required to keep using the current app.

The [aggregate report](../reports/blendbanking77-v1/semantic_head_study.json) records every candidate, the selected index, control differences, protocol hash, versions and encoder fingerprints. Its reference-report hash is metadata: the experiment itself does not open that report. Reproduction of the original control and encoder fingerprints is checked separately before publishing results.

## Validation

Tests check that all six fits receive training features/targets, that encoding occurs once per partition, and that no calibration/test/source files are opened. Other checks cover protocol/input mismatch rejection before encoder loading and deterministic selection/tie-breaking. Aggregate counts and the control are verified against the earlier report. No software test is presented as ML-quality evidence.
