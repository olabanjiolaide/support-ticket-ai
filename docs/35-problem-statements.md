# Account-access and payment problem statements

The offline prototype recognizes a narrow combination of account-access and payment failure statements, then proposes:

> You mentioned account access and a payment issue. Which would you like help with first?

For the known message “I cannot log in and my checkout payment was rejected.” it records ACCOUNT and PAYMENT **lexical hints**, with exact matching source spans, and withholds the existing single-category suggestion. It does not execute actions, change the original top category or treat the hints as verified independent customer intents.

## Scope and fixed comparison

This targets one failure identified in the [error analysis](33-error-analysis.md). The [configuration](../data/problem_statements_protocol.json), [30 authored contrasts](../data/problem_statements_contrasts.json) and implementation were committed as `93fcbdacc8520340a53d2148193e0b7d1a184075` before replaying the results. They were designed after inspecting that known failure. No rules or contrast expectations were revised from the resulting measurements.

The check splits supported conjunctions, semicolons, line breaks and sentence boundaries into two to four fragments. **Every fragment must match a complete recognized problem statement**, and both ACCOUNT and PAYMENT patterns must be present. Negated capability such as “cannot log in” can express an actual account problem; a negated payment failure such as “my payment was not rejected” does not match the positive payment pattern. These are explicit patterns, not a general negation parser.

Markers for conditions, alternatives, causal or temporal links, and double quotation marks skip inspection. Extra unrecognized fragments also prevent a match. Skipping avoids asserting evidence the prototype cannot interpret; it can miss real multiple-problem messages. Same-category statements do not qualify. All expressions and limits appear in the frozen configuration.

Evidence offsets address the original input, including original apostrophes and whitespace. Only matching uses normalized whitespace and apostrophes. The `category_hint` name distinguishes these pattern matches from semantic-model predictions.

The question asks the user to prioritize help. Two mentioned problems can share a cause, and the message may still express one desired outcome. The experiment does not establish independent underlying intents or prove that the follow-up question is useful.

## Recorded development replay

The [report](../reports/problem-statements-v1/comparison.json) starts from the [prior clarification replay](../reports/clarification-v1/comparison.json), which already includes the optional separate-request guard. It loads no models and computes no new model scores.

| Count on 98 previously inspected provisional cases | Before problem-statement check | After check |
|---|---:|---:|
| Supported requests receiving a suggestion | 52/66 | 52/66 |
| Correct accepted supported suggestions | 49 | 49 |
| Incorrect accepted supported suggestions | 3 | 3 |
| REVIEW cases withheld | 7/8 | 8/8 |
| Unsupported requests suggested | 0/24 | 0/24 |

Only `ambiguous-08`, the known login-plus-payment message, is newly withheld. All 30 authored contrast expectations match. Six positive examples vary order, account wording, payment wording and punctuation. The 24 negative examples cover short clear requests, same-category problems, conditions, alternatives, causal/temporal descriptions, quoted examples, explicit negation, background or resolved issues, unrecognized extra context and more than four fragments. These examples were authored with the rule design in mind and retain provisional labels.

The offline gate passes: the tracked suggestion counts do not regress, REVIEW withholding increases, and every contrast expectation matches. **The prototype remains offline.** An 8/8 count on this tiny reused REVIEW set is not evidence of general ambiguity detection or readiness for automatic routing. The three accepted category errors are still present, and unseen phrasing can evade the rules.

## Run and inspect

From an updated repository checkout, only Python's standard library is needed for this replay:

```bash
python -m support_ticket_ai.problem_statements reports/clarification-v1/comparison.json reports/problem-statements-v1/local-comparison.json
```

The command validates source-report, contrast and configuration fingerprints. It refuses an existing output path and cleans up partial output after failure. The source report is in the repository, so no encoder download, local semantic bundle or manual labeling is needed. Package 0.12.0 bundles the module, protocol and contrast cases; wheel users must supply the source report separately.

Focused checks:

```bash
python -m unittest discover -s tests -p test_problem_statements.py -v
```

Tests exercise authored contrasts, exact source offsets, invalid inputs, preserved prior abstentions, input immutability, unchanged model scores/fingerprint, tampered-source rejection and safe CLI output handling.

## Learning point and limits

A sentence classifier can pick a plausible category while overlooking another problem. Preserving inspectable evidence and asking a priority question makes that missing decision explicit. However, targeted rules only establish a bounded baseline. Broader paraphrase coverage, conversations, quotation scope, causality and resolution require independent evaluation before expanding the claim or integrating a live check.

There is no validation, calibration or held-out test access, encoder training, private/pending review access, model export, browser change or API change. Every category suggestion still requires human review. Manual labeling remains paused.

Verification: the full suite ran 186 tests: 185 passed and one optional Torch training test was skipped because Torch was unavailable. All seven new problem-statement tests passed. Wheel and source distribution built successfully; an installed-wheel replay from outside the checkout reproduced the recorded counts. Packaged module, protocol and contrast bytes match the checkout.
