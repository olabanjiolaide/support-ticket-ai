# Whole-message and heuristic segment pooling

This study asks whether adding representations of smaller text segments helps a fixed semantic classifier recover complete intent sets. It compares four representations using the same frozen encoder and binary-head settings. The segmenter supplies unvalidated text spans, not inferred actions or verified semantic boundaries.

## Protocol and controls

The [protocol](../data/segment_pooling_protocol.json) was committed in [2b47f4a](https://github.com/olabanjiolaide/support-ticket-ai/commit/2b47f4a124b97121aa13d2b10ea46cc05176ad72) before fitting. It was designed after observing the earlier development studies, including the [C=10 unweighted result](29-semantic-head-study.md). No unseen-data preregistration or independent test estimate is implied.

All settings use the same pinned frozen MiniLM revision, normalized 384-dimensional embeddings, C=10 without class weighting, threshold 0.5, maximum 1,000 iterations and seed 42. Training contains 28,338 requests; selection contains 2,008 requests with 77 native banking labels. No threshold or classifier-grid search is added.

| Representation | Dimensions | Construction |
|---|---:|---|
| whole | 384 | Existing unit-normalized whole-message vector |
| whole_duplicate | 768 | Concatenate the whole vector with itself, divide by sqrt(2) |
| whole_segment_mean | 768 | Concatenate whole vector with unit-normalized mean of segment vectors, divide by sqrt(2) |
| whole_segment_max | 768 | Concatenate whole vector with unit-normalized coordinatewise maximum of segment vectors, divide by sqrt(2) |

The duplicate-vector control preserves the whole-vector Gram matrix and L2 norm mathematically. It checks feature duplication/scaling under the same regularization; finite optimizer tolerances can still cause score differences, which the report records. The two pooling variants add feature directions. This control cannot isolate every capacity effect from the effect of segmentation.

Each source is encoded once as a whole message per partition. Only texts split into several spans require additional segment encodings. Identical segment strings are deduplicated within each partition for deterministic frozen inference. Labels do not influence boundaries, pooling or deduplication. An unsplit text reuses its whole vector; a zero-norm pooled vector falls back to that vector.

Mean pooling averages segment directions. Coordinatewise max pooling is an exploratory numeric feature construction whose meaning depends on the embedding coordinates. Neither operator is established here as a semantic intent-composition rule.

## Heuristic segmentation and preservation

Version 1 cuts after whole-word `and`, `also`, `plus`, `but`, or comma/semicolon/sentence-ending/newline delimiters. The exact expression is recorded in the protocol. Each delimiter remains in its preceding span. Fragments shorter than two whitespace-separated words merge with the previous span; a short initial prefix merges with the next. At most four spans are retained, with all excess tail text merged into the fourth.

Spans are contiguous Python/Unicode-code-point offsets over the unchanged source. Their concatenation reproduces every character. Preserving offsets and text does not establish that a boundary correctly separates intents. The heuristic can split one intent, miss several intents, or separate a condition/reference from the request it modifies. Keeping the whole vector supplies context features but does not prove that the classifier uses that context correctly. The separate browser guard and action-plan validator are unchanged.

## Development results

| Representation | Exact-set accuracy | Micro F1 | Micro precision | Micro recall |
|---|---:|---:|---:|---:|
| whole | 42.23% | 73.09% | 85.66% | 63.73% |
| whole_duplicate | 42.18% | 72.68% | 85.52% | 63.19% |
| whole_segment_mean | 44.67% | 74.46% | 87.11% | 65.02% |
| whole_segment_max | 43.43% | 73.63% | 86.97% | 63.84% |

The predeclared metric rule nominates mean pooling: 897 of 2,008 complete sets correct, compared with 848 for whole-message features. Three-intent complete sets rise from 30/411 (7.30%) to 34/411 (8.27%); max pooling gets 36/411 (8.76%) but has lower overall accuracy, so it does not win the declared ranking. These are raw development results, not a verified causal improvement from segmentation.

**The duplicate control disagrees on 85 request-level predicted sets, with a maximum score difference of 0.6611.** Similar headline accuracy masks this disagreement. Although the duplicate construction is mathematically equivalent under transformed weights and L2 regularization, independently fitted models are not predictively equivalent under these settings. This prevents treating the nominal mean-pooling gain as clean evidence for the representation hypothesis. The nomination is retained in the raw report; no model is exported or promoted on that basis.

All fits meet their configured solver stopping criterion, which is weaker than showing equivalent solutions under an isometric representation. This study uses the library's default tolerance of 1e-4. The separately fixed numerical audit below investigates that issue rather than silently changing this recorded experiment.

| Observed segment count | Training requests | Selection requests |
|---|---:|---:|
| 1 | 12,411 | 938 |
| 2 | 9,266 | 665 |
| 3 | 4,263 | 281 |
| 4 | 2,398 | 124 |

Tail merging caps 815 training and 36 selection requests. Additional frozen inference uses 28,975 unique training segments and 2,288 unique selection segments. Neither whole inputs nor encoded segments exceed the 256-token encoder limit. The whole-message control reproduces the earlier C=10 report exactly, and encoder file fingerprints match.

## Numerical follow-up

After observing the failed control, the [numerical-audit protocol](../data/segment_optimizer_protocol.json) was committed in [851045c](https://github.com/olabanjiolaide/support-ticket-ai/commit/851045cfec1aa58451bd0fd683714bceb58f32b2), alongside the original aggregate report, before its diagnostic fits. This is a disclosed follow-up, not part of the original predeclared comparison.

It fits whole/duplicate representations at tolerances 1e-4 and 1e-8, each with C=10, threshold 0.5, seed 42 and a 5,000-iteration cap. The larger cap applies to both tolerances; actual iteration counts are recorded. Accuracy does not select a tolerance. The audit also transforms fitted whole-model coefficients into duplicate-feature coefficients divided by sqrt(2), preserving the score function without another fit. That check separates construction equivalence from differences caused by independent optimization.

| Solver tolerance | Whole exact-set accuracy | Duplicate exact-set accuracy | Different predicted sets | Maximum score difference |
|---|---:|---:|---:|---:|
| 1e-4 | 42.23% | 42.18% | 85/2,008 | 0.661080 |
| 1e-8 | 45.32% | 45.32% | **0/2,008** | 0.000105 |

The default-tolerance pair reproduces the original control failure exactly. The tighter pair agrees on every selection label set, with a small remaining probability difference. The exact coefficient transformation changes scores by at most 6.6e-15 and changes no predicted sets at either tolerance. That supports the feature construction's mathematical equivalence and identifies independent optimization/stopping as the source of the observed drift.

Both default-tolerance fits stop after at most 43 iterations; both tighter fits use at most 209. Every head meets its configured stopping criterion. Neither reaches even the old 1,000-iteration cap, so the increase to a 5,000-iteration cap does not explain this measured difference. Tighter stopping, rather than an increased iteration limit, resolves the label-set inconsistency in this audit.

The tighter whole-message model gets 910/2,008 complete sets correct, compared with 848 previously. Its micro F1 is 75.15%, macro F1 74.67%, micro precision 87.71% and micro recall 65.74%. Three-intent complete sets improve from 30/411 to 41/411 (9.98%), which remains weak. These are descriptive development results of a numerical diagnostic; accuracy did not select the tolerance, and no independent test or production guarantee is established.

The nominal mean-pooling score of 44.67% is therefore not accepted as a verified representation improvement. Tighter optimization alone produces a stronger whole-message reference. A matched mean/max comparison at the reliable numerical settings is still needed; these cross-tolerance scores cannot establish that pooling itself helps or hurts. The tighter whole-message recipe can serve as the next development comparator, with its measured finite-data invariance check retained.

The subsequent [matched strict-solver comparison](31-matched-segment-comparison.md) performs that follow-up with all four representations and an explicit numerical gate. The earlier results above remain the historical diagnostic record.

The [numerical report](../reports/blendbanking77-v1/segment_optimizer.json) contains both tolerance pairs, score/set discrepancies, exact-transform checks and iteration counts. It does not refit mean/max pooling at tighter tolerance. A fair representation conclusion requires that subsequent matched comparison; neither an optimizer diagnostic nor better convergence validates heuristic request boundaries.

## Selection rule and limits

Only the mean/max representations can replace the whole-message comparator. A candidate must strictly improve overall exact-set accuracy and must not reduce three-intent exact-set accuracy. Eligible candidates are ranked by overall exact-set accuracy, micro F1, micro precision and then earlier protocol order. If none qualifies, the whole-message comparator is retained. This guard concerns development metrics only, with no calibrated or statistical guarantee.

The study reads only the preparation manifest, training and selection files, protocol and encoder files. Calibration and publisher-test payloads, Bitext held-out data, and paused private/reserved review collections remain unused. The downloaded source's all-splits provenance is documented in [benchmark preparation](26-action-plan-and-public-benchmark.md); this experiment does not open that raw source.

The public benchmark supplies intent labels without gold request spans, conditions, negation scope or relations. Its publisher labels are unadjudicated, and composition-family and pretrained-source overlap remain unknown. Repeated development selection limits generalization claims. Native banking results do not establish behavior on the browser's 11 support categories. This exploratory ablation makes no novelty claim and exports no trained weights, embeddings, individual predictions or source text.

## Reproduce

After preparing the benchmark and installing the existing optional CPU semantic dependencies:

```bat
python -m support_ticket_ai.segment_pooling artifacts/blendbanking77-v1 --output artifacts/segment-pooling-v1.json
python -m support_ticket_ai.segment_optimizer artifacts/blendbanking77-v1 --output artifacts/segment-optimizer-v1.json
```

The default protocol is packaged with version 0.9.0; altered settings or input fingerprints fail validation. Use a fresh output filename. The encoder cache is reused, with a download if missing. The recorded local run used offline mode against the cached pinned revision.

The manually triggered **Compare whole-message and segment pooling** GitHub Actions workflow runs tests, preparation, the original comparison and numerical follow-up on CPU. It uploads aggregate reports, protocols, manifest and attribution/license notices for seven days. It provides reproduction from a phone; local measurements are not presented as an asserted completed Actions run. The workflow does not host the app.

The [aggregate report](../reports/blendbanking77-v1/segment_pooling.json) records each representation, selected index, duplicate-control differences, input/protocol fingerprints, encoder file hashes, versions, segment counts and length audits. The protocol's prior-report fingerprint is contextual metadata; the runner itself does not open that report. Control reproduction and encoder fingerprints are checked separately before publishing.

## Software checks

Tests cover exact character/Unicode preservation, tail merging, feature norms, duplicate Gram-matrix equality, zero-vector fallback, train-only fitting and the three-intent selection guard. Mismatched protocols/inputs and missing three-intent selection data fail before encoder loading. Fixtures contain no calibration/test/source files; guarded file reads verify the boundary. Software checks validate the pipeline, not segmentation semantics or model quality.
