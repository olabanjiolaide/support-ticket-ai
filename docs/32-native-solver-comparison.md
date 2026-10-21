# Solver settings on the actual ticket model

This study returns to the browser's **11 support categories**. The preceding 77-label banking results do not establish that tighter optimization will improve this model.

The [protocol](../data/native_solver_protocol.json) was committed as `6b9e4c004301bb978c7505ab2dfaa2d99acdad51` before either new fit. It fixes C=1, the existing normalized MiniLM sentence vectors, both 0.5 review cutoffs, and the existing scope-negative training examples. The only comparison is default tolerance `1e-4` / 1,000 iterations against tighter tolerance `1e-8` / 5,000 iterations. Both category and scope heads use the selected setting. The scope head retains balanced class weights.

The same cached vectors feed both fits. Before interpreting results, the reconstructed control must reproduce the trusted saved model's category, decision and scores within 1e-6 on every development request and every fragment used by either optional guard run. Convergence warnings fail the experiment.

The follow-up gate requires both guarded and original policies to preserve supported coverage and correct accepted suggestions, without increasing wrong accepted suggestions, unsupported suggestions or REVIEW suggestions. At least one count must improve. Passing qualifies only for additional validation; this command cannot export a candidate bundle or change the browser.

## Recorded result

**Retain the existing browser model.** Tighter fitting changes no suggested category or review decision on any of the 98 probes. It fails the follow-up gate because there is no observed count improvement.

| Development count | Current settings | Tight settings |
|---|---:|---:|
| Supported requests accepted | 52/66 | 52/66 |
| Correct accepted suggestions | 49 | 49 |
| Incorrect accepted suggestions | 3 | 3 |
| Correct forced top category | 56/66 | 56/66 |
| Unsupported requests suggested | 0/24 | 0/24 |
| REVIEW requests suggested, original policy | 5/8 | 5/8 |
| REVIEW requests suggested, optional guard | 3/8 | 3/8 |

Supported counts are identical with and without the optional guard. Both fits use 16,990 category-training rows and 48 authored scope negatives. The reconstructed control agrees on categories and decisions for all 102 distinct probe/fragment texts, with maximum category/scope score difference **2.06e-7**, below the 1e-6 limit.

Category iterations increase from 31 to 83; scope iterations increase from 16 to 35. Neither original head reaches its 1,000-iteration cap. Recorded fitting time rises from 6.09 to 42.68 seconds on this run; this is local timing, not a controlled speed benchmark. Frozen training-vector encoding takes 70.82 seconds and is shared between fits.

This result narrows the next engineering question: changes to representations, training coverage or ambiguity handling need their own evidence. Stricter optimization alone has not improved this app's observed decisions. The banking benchmark's numerical finding does not transfer as a prediction-quality gain here.

Verification: **173 tests passed**, including gates that reject every tracked regression, unchanged-result rejection, control-fidelity failure, separation of REVIEW/unsupported counts and shared-vector caching. Package 0.10.1 includes the study command and protocol; the API remains 0.4.0.

## Reproduce

Use the existing working environment with `requirements-semantic.txt` installed. Supply your trusted semantic bundle and its matching prepared Bitext data; the command validates their checksums against the protocol. A locally rebuilt bundle can have a different fingerprint because of environment or serialization differences; it must not be silently substituted for this study's reference.

```bash
python -m support_ticket_ai.native_solver artifacts/semantic-live-v1 artifacts/bitext-v2 reports/native-solver-v1/local-comparison.json
```

These are the recorded local directory names, not files downloaded by pulling GitHub. The report refuses to overwrite an existing file. The recorded public report is [comparison.json](../reports/native-solver-v1/comparison.json). No trained heads or encoder weights are committed.

## What to learn

A solver tolerance controls when numerical optimization stops. Increasing the iteration cap only matters if optimization reaches the old cap; a stricter tolerance can continue fitting even when the original fit stopped early. Better optimization of training loss does not guarantee better predictions or better abstention decisions.

The 98 authored probes have already been inspected and retain provisional labels. Their counts are development diagnostics, not independently measured reliability. Keeping cutoffs fixed tests transfer of the existing policy; it does not make either head's scores calibrated. Validation, calibration, final tests, private reviews and the pending reserved collection remain unopened by this experiment. Every suggestion requires human review.
