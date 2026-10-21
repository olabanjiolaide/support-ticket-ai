# Segment pooling with matched strict solvers

The earlier [pooling study and numerical audit](30-segment-pooling.md) found that default solver stopping could change predictions under equivalent vector duplication. This follow-up compares the same four representations with the tighter numerical settings applied to every classifier. It preserves the original studies for reproduction.

## Fixed follow-up protocol

The [protocol](../data/segment_stable_protocol.json) was committed in [077a1e0](https://github.com/olabanjiolaide/support-ticket-ai/commit/077a1e02bca59b6bdabd19982262b9c4d07bc4ad) before these fits. This design follows prior development findings; it is not preregistered unseen-data research. The protocol records the earlier numerical-report hash and development-file fingerprints.

All heads use C=10, no class balancing, tolerance 1e-8, at most 5,000 iterations, seed 42 and a fixed 0.5 decision threshold. The same pinned MiniLM encoder remains frozen. Training has 28,338 requests; reused selection has 2,008 requests across 77 native banking labels. There is no new regularization/threshold search, encoder update or segmentation-rule change.

| Representation | Features |
|---|---|
| whole | 384-dimensional normalized whole-message vector |
| whole_duplicate | Whole vector concatenated with itself, divided by sqrt(2) |
| whole_segment_mean | Whole vector plus normalized mean of segment embeddings, divided by sqrt(2) |
| whole_segment_max | Whole vector plus normalized coordinatewise maximum of segment embeddings, divided by sqrt(2) |

The three concatenated vectors have 768 dimensions and preserve unit input norm. The duplicate representation adds no information mathematically. The pooled representations add feature directions; the control does not separate all capacity effects from segmentation. Mean/max pooling loses segment order, and max pooling depends on embedding coordinates. Segments remain heuristic text spans without gold request boundaries. The [original guide](30-segment-pooling.md#heuristic-segmentation-and-preservation) specifies unchanged boundaries, merging, capping and source preservation.

## Numerical and predictive gates

Independent whole/duplicate fits must agree on every selection label set, with maximum absolute score difference at most 0.001. This numerical tolerance was fixed after observing the preceding audit, before this run. Passing it establishes measured consistency on this finite partition, not a guarantee on every future input.

Only mean/max candidates can replace the whole-message comparator. A candidate must strictly improve overall exact-set accuracy without reducing three-intent exact-set accuracy. Eligible candidates are ranked by overall exact-set accuracy, micro F1, micro precision and earlier protocol order. If the numerical control fails, the comparison is marked unusable and whole remains the reference even if a candidate is nominated by the predictive metrics. If no candidate meets the predictive gate, whole is retained.

## Matched development results

| Representation | Exact-set accuracy | Micro F1 | Three-intent exact-set accuracy |
|---|---:|---:|---:|
| **whole (retained)** | **45.32%** | **75.15%** | **9.98% (41/411)** |
| whole_duplicate | 45.32% | 75.15% | 9.98% (41/411) |
| whole_segment_mean | 46.07% | 75.67% | 9.25% (38/411) |
| whole_segment_max | 45.72% | 75.13% | 8.76% (36/411) |

**Neither pooling candidate qualifies.** Mean pooling adds 15 complete sets overall (925 versus 910), an increase of 0.75 percentage points, but loses three complete three-intent sets. Max pooling adds eight complete sets overall (918 versus 910) while losing five three-intent sets. Both violate the predefined nonregression condition. The whole-message model remains the development reference despite the higher average scores.

The numerical gate passes: whole/duplicate fits disagree on **zero of 2,008 predicted label sets**, with maximum absolute score difference 0.000104921, within the 0.001 bound. Their complete metrics reproduce the preceding numerical audit. This resolves the earlier control problem for this matched run; the pooling rejection follows the predictive slice criterion rather than a numerical-control failure.

Mean pooling's micro precision/recall are 87.89%/66.44%, compared with 87.71%/65.74% for whole-message features. These modest aggregate improvements do not remove the recorded three-intent regression. The result concerns these fixed heuristics and representations. Learned, context-aware segmentation requires its own evaluation.

| Representation | Measured fit seconds | Maximum iterations in any head |
|---|---:|---:|
| whole | 114.8 | 209 |
| whole_duplicate | 184.5 | 209 |
| whole_segment_mean | 189.0 | 197 |
| whole_segment_max | 191.1 | 203 |

All heads meet their configured stopping criterion without approaching the 5,000-iteration cap. Fit time measures classifier training only, excluding encoder loading, whole/segment encoding, prediction and HTTP/UI handling. These local CPU measurements are descriptive and do not establish production inference latency. Pooling also requires additional segment encodings beyond the whole-message representation.

The input hashes, encoder file fingerprints and segmentation counts match the preceding studies. No input exceeds the encoder's configured token limit. The finding closes this bounded pooling comparison: retain the simpler whole-message reference, preserve the rejected candidates and examine context-sensitive request decomposition separately before making richer action-understanding claims.

## Interpretation and boundaries

This study tests established frozen-feature pooling variants on reused development data. It makes no novelty, significance, independent generalization or calibrated-confidence claim. Label-set results do not validate action descriptions, source evidence, negation, conditional scope or relations. The native banking taxonomy remains distinct from the browser's 11 support categories; publisher labels and source-family/pretraining overlap retain their earlier limitations.

Only the preparation manifest, training file, selection file, protocol and encoder files are read. Calibration, publisher-test payloads, Bitext held-out data, and paused private/reserved reviews remain unused. No trained model, embedding cache, individual predictions or dataset text is exported. The browser/API behavior is unchanged.

## Reproduce

After preparing the pinned benchmark and installing existing optional CPU semantic dependencies:

```bat
python -m support_ticket_ai.segment_pooling artifacts/blendbanking77-v1 --stable --output artifacts/segment-stable-v1.json
```

`--stable` uses the packaged protocol. It is mutually exclusive with `--protocol`. The default command without either flag retains the historical default-tolerance protocol; recorded historical results are not overwritten. Use a fresh output filename. The local run uses the existing pinned encoder cache with offline mode enabled. No Windows setup or labeling is required to keep using the browser app.

The manually triggered **Compare segment pooling with matched strict solvers** Actions workflow runs preparation, tests and this comparison on CPU. It uploads the report, protocol, preparation manifest and attribution/license notices for seven days. The workflow supports reproduction from a phone; local measurements are not asserted to be a completed Actions run. It does not host the app.

The [aggregate report](../reports/blendbanking77-v1/segment_stable.json) records all four representations, the metric nomination, numerically gated selection, solver settings, maximum iterations, measured fit time, encoder/input fingerprints and segmentation audit. Timing is environment-dependent and is not a selection criterion. The earlier-report fingerprint is contextual metadata; that report is not opened by the runner. Control reproduction is verified separately before publication.

## Software validation

Tests verify identical strict settings and train-only inputs for all four fits, guarded reads with no calibration/test/source files present, numerical score/set checks, and retention of whole features when a nominated candidate fails the numerical gate. Altered tolerance/cap/gate settings fail before encoder loading. Existing tests preserve the historical 1e-4/1,000-iteration recipe. These checks establish implementation behavior, not NLP quality.
