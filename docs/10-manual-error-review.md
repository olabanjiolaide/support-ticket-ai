# Manual development checks: 2026-10-20

These three author-written requests were run by the user through the local ticket workspace. The observations below were transcribed from screenshots. Scores are the rounded values displayed by the interface, not full-precision API probabilities.

They are targeted development probes, not a representative benchmark or the reserved held-out test set. The expected labels were assigned for this exercise.

## Observations

| Entered message | Expected treatment | Observed suggestion | Displayed score | Assessment |
| --- | --- | --- | ---: | --- |
| Please send me an invoice for my last payment.” | INVOICE | INVOICE | 0.347 | Correct category, despite a relatively low top score |
| I was charged twice for my subscription | PAYMENT | ACCOUNT | 0.260 | In-scope classification error |
| Write a poem about the moon | Outside the supported categories | FEEDBACK | 0.347 | Unsupported request receives a forced category |

The trailing closing quotation mark in the first message is retained from the screenshot. The other two messages were entered without a final full stop. These details matter when reproducing text-feature behavior.

The previous account-access request (“Yes, can't access my account. i can't remembered the login details”) separately produced ACCOUNT with a displayed score of 0.979. It is a manual observation, not evidence of general robustness to grammar variation.

## What these checks establish

The user-facing form, prediction endpoint, saved classifier, and result rendering work together on the user's Windows installation. A successful HTTP response does not imply the predicted category is appropriate.

The payment example reproduces a previously documented failure. The poem example exposes a distinct scope limitation: the classifier always chooses one of its learned support categories. It has no trained unsupported-request detector or abstention mechanism.

Both the correct invoice suggestion and the unsupported poem suggestion display 0.347. Equal rounded scores do not imply their full probability distributions are identical. The displayed top score alone cannot distinguish these two cases.

All three predictions retained the human-review requirement. The service did not automatically route the messages.

## Possible causes to investigate

The difference between the near-perfect synthetic validation result and these manual errors suggests a generalization gap worth investigating. Possible contributors include synthetic language patterns, limited coverage of natural payment phrasing, and the absence of an unsupported category. These are hypotheses, not established causal explanations.

Temperature scaling cannot change the predicted category. The earlier calibration experiment also made the wrong payment suggestion more confident, so applying that scaling alone would not resolve these errors.

## Next improvement and evaluation criteria

1. Build a broader, explicitly labelled development challenge set containing varied supported requests, ambiguous requests, and unrelated requests. Keep these cases out of the final held-out test.
2. Evaluate a candidate abstention policy that can return “No reliable suggestion” instead of always presenting a category as actionable. Compare score-based baselines with a dedicated scope-detection approach.
3. Select any thresholds on development-selection examples and assess them on separate development-audit examples.
4. Measure accepted-request accuracy, coverage, unsupported-request rejection, and incorrect rejection of valid support requests. A single accuracy number is insufficient.
5. Keep human review required while evaluating. Do not introduce keyword rules or claim an unsupported-request detector works based only on these three probes.

A threshold that rejects the poem could also reject the correct invoice request. That trade-off must be measured rather than hidden.

No model was retrained, no calibration was activated in live inference, and no held-out test was evaluated for this review.

## Learning point

Separate software correctness, category accuracy, and scope handling. A working service can still make a wrong suggestion, and a category classifier does not automatically know when a request falls outside its task.
