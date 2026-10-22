# A narrow offline clarification prototype

The prototype proposes **“What were you trying to do, and what happened?”** when an entire single-message request matches a generic failure statement. It can withhold a recorded category suggestion; it cannot reverse an existing abstention. It does not run in the browser or API.

This is a small rule baseline for one gap found in the [error analysis](33-error-analysis.md). It does not implement a trained clarification model or general semantic understanding. Its patterns were designed after inspecting the existing failures, so success on those cases is expected development evidence, not an independent quality estimate.

## Fixed design

The [protocol](../data/clarification_protocol.json), [24 authored contrasts](../data/clarification_contrasts.json) and rule implementation were committed as `d582e8f5e84365060fd102bcad3360d7d4b3b89d` before replaying the results. No rules or contrast expectations were changed after the run.

The patterns require a generic reference such as “it,” “this,” or “something,” paired with a generic malfunction statement. The entire message must match after whitespace, apostrophe and terminal punctuation normalization. Extra clauses, concrete task context and quoted phrases are not discarded to force a match. Exact expressions and their version are recorded in the protocol.

A matched suggestion becomes an abstention and receives a fixed clarification proposal. The original category and uncalibrated scores remain available for inspection; the question does not make those scores calibrated. For an existing abstention, the prediction and its original reason stay intact, even if a question is proposed alongside it. No match means only that these narrow rules did not fire.

## Recorded development result

The [report](../reports/clarification-v1/comparison.json) replays the guarded control predictions in the pinned [native solver report](../reports/native-solver-v1/comparison.json). It loads no encoder, fits no head and computes no new model scores.

| Count on previously inspected authored cases | Existing optional guard | Guard plus clarification prototype |
|---|---:|---:|
| Supported requests receiving a suggestion | 52/66 | 52/66 |
| Correct accepted suggestions | 49 | 49 |
| Incorrect accepted suggestions | 3 | 3 |
| REVIEW cases withheld | 5/8 | 7/8 |
| Unsupported requests suggested | 0/24 | 0/24 |

Newly withheld: `ambiguous-01`, “It does not work.”, and `ambiguous-04`, “Something is wrong with what I bought.” Both receive the generic follow-up question. All 24 contrast checks match their authored provisional expectations, including short clear requests, concrete task failures, quotations, conditionals and messages with additional context. They were written with the candidate rules in mind and are regression checks, not independent validation.

The predeclared offline gate passes: supported coverage and correctness counts are preserved, REVIEW withholding increases and no contrast expectation fails. **The candidate remains offline.** Passing this gate does not authorize or establish readiness for deployment.

The three wrong accepted categories remain wrong. The declarative multi-problem request “I cannot log in and my checkout payment was rejected.” still passes through as PAYMENT; recognizing generic references does not solve multiple-problem detection.

## Reproduce and learn

From the updated repository checkout, this command uses only Python's standard library:

```bash
python -m support_ticket_ai.clarification reports/native-solver-v1/comparison.json reports/clarification-v1/local-comparison.json
```

Use a fresh output filename. The command validates source-report, contrast and rule fingerprints, refuses to overwrite an existing report, and removes a partial output after failure. The recorded source report is available in the repository; no model download or retraining is required. Installed-wheel users must provide that report separately. Package 0.11.0 bundles the rule module, protocol and contrast cases.

Focused checks:

```bash
python -m unittest discover -s tests -p test_clarification.py -v
```

The tests cover preservation of prior abstentions, input immutability, invalid inputs, preservation of raw scores, the authored contrast expectations, tampered source rejection and safe CLI output handling.

The learning point is to separate **choosing a category** from **deciding whether the request supplies enough context**. A deterministic question is easy to inspect, but its usefulness is a separate outcome. This experiment does not test whether a user answers the question, whether the answer resolves the problem, or whether a follow-up category prediction improves.

Single-message context is another limitation: earlier conversation may already identify what “it” refers to. These English-only expressions also miss many vague paraphrases and can match statements outside customer support when used without a scope check. Any live design would need conversation handling and independent evidence before promotion. Manual labeling remains paused, and this replay opens no private/pending reviews, validation or final-test data.

Verification: the suite ran 179 tests: 178 passed and one optional Torch training test was skipped because Torch was unavailable. All six new clarification tests passed. Wheel and source distribution built successfully; installing the wheel and replaying the pinned report from outside the checkout reproduced the same counts. Bundled source, protocol and contrast bytes were checked against the checkout.
