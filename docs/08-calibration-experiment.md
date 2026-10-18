# Offline calibration and review-threshold experiment

## Decision

Keep every API and CLI suggestion under human review. Temperature scaling improved probability metrics on the synthetic development data, but it increased confidence in a known wrong manual prediction. This experiment does not justify automatic routing.

## Experiment design

The frozen baseline model is reused without refitting its vectorizer or classifier. The existing validation data is partitioned by category and deterministic ID hashes (seed 73) into three disjoint subsets:

| Subset | Requests | Role |
| --- | ---: | --- |
| Calibration fit | 1,457 | Fit one temperature parameter by minimizing negative log likelihood |
| Threshold selection | 1,091 | Choose a candidate score threshold from a fixed grid |
| Development audit | 1,094 | Describe the selected temperature and threshold on separate rows |

The validation population had already been inspected in earlier development. These subsets are not a newly untouched external benchmark. The held-out test file is never read by this experiment.

Temperature scaling computes softmax(log(p) / T), where p is the frozen model's class-probability vector. T is fitted within bounds [0.05, 10]. Because T is positive, class ordering is preserved; calibration cannot correct a wrong predicted class.

Method reference: [scikit-learn probability calibration documentation](https://scikit-learn.org/stable/modules/calibration.html). The implementation uses a single bounded SciPy optimization over log temperature rather than refitting the classifier.

## Development audit results

Fitted temperature: **0.2326808254**.

| Metric | Original probabilities | Temperature-scaled probabilities |
| --- | ---: | ---: |
| Accuracy | 0.999086 | 0.999086 |
| Negative log likelihood | 0.082374 | 0.003668 |
| Multiclass Brier score | 0.017427 | 0.002068 |
| Top-label expected calibration error | 0.069896 | 0.002608 |

Lower is better for the three probability metrics. Brier score is the mean sum of squared class-probability errors, without division by class count. ECE uses 15 equal-width confidence bins; it is a bin-dependent summary, not proof of calibration in every category or deployment setting. The aggregate report includes bin counts, mean confidence, and observed accuracy.

## Threshold simulation

The predefined candidate grid is 0.50, 0.60, 0.70, 0.80, 0.90, 0.95, 0.98, and 0.99. Selection maximizes coverage subject to at least 50 selected examples and observed selected accuracy of at least 0.99 on the threshold-selection subset. This is an empirical development criterion, not a statistical accuracy guarantee.

The rule selected threshold **0.50**. On the separate development-audit subset, it selected all 1,094 requests and made one error. This is a simulation only: actual API review coverage remains 100%.

## Counterexample: a wrong suggestion becomes more confident

Author-written input: “I was charged twice for my subscription.” The author assigns PAYMENT as the intended category.

| Check | Result |
| --- | --- |
| Model's suggested category | ACCOUNT, before and after scaling |
| Original top score | 0.2601 |
| Temperature-scaled top score | 0.8959 |
| Passes the simulated 0.50 threshold | Yes |
| Live behavior | Human review required |

This example is illustrative, not an independently sampled benchmark. It demonstrates that calibration fitted on one source can sharpen an erroneous suggestion on a new phrasing. The method does not detect unsupported requests, remove template overlap, or establish robustness under distribution shift.

## Reproduce

First build the [local demo](07-running-the-demo.md), then run:

```bash
python -m support_ticket_ai.calibrate artifacts/demo-v1/prepared artifacts/demo-v1/model artifacts/calibration-v1.json
python -m unittest discover -s tests -q
```

Choose a new report filename for repeated runs. Input checksums and manifest fingerprints are verified. The report records the model fingerprint, dependency versions, temperature, partition seed, subset ID fingerprints, reliability bins, threshold candidates, simulation results, and the manual counterexample.

The experiment was run on 2026-10-18. Its aggregate report is `reports/bitext-baseline-v1/calibration_experiment.json`. Raw ticket data is not included, apart from the explicitly author-written probe. All 49 local tests pass at this milestone.

## Learn from your phone

**Calibration asks whether scores match observed correctness frequencies. It does not teach the classifier new categories or repair its mistakes.**

Interview answer: “I evaluated temperature scaling on disjoint development subsets and tested a review-threshold policy. Although probability metrics improved on the synthetic source, a manual error became more confident, so I retained human review.”

Next research and engineering work should address unsupported requests and evaluation under new phrasing or domains before any automatic-routing decision. The final held-out test remains reserved.
