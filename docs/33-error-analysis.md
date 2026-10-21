# What the remaining mistakes tell us

This analysis inspects the existing public development results; it fits no model and requests no new labels. Source: [native solver report](../reports/native-solver-v1/comparison.json), control setting. These authored labels are provisional and have already been inspected. The observations below explain recorded behavior; proposed causes remain hypotheses.

## Wrong accepted categories

| Case | Public request | Expected | Suggested | Uncalibrated score |
|---|---|---|---|---:|
| cancel-04 | will i pay a penelty for cancling? | CANCEL | REFUND | 0.713 |
| contact-05 | I would rather discuss this with someone who works for your company. | CONTACT | FEEDBACK | 0.901 |
| feedback-04 | where can i leav a reveiw of this shop | FEEDBACK | ORDER | 0.724 |

Two mistakes occur on deliberately misspelled requests. This is evidence of a spelling-related failure slice, not proof that spelling alone causes either error: this analysis does not run corrected-text counterfactuals. Under this project's taxonomy, cancellation-fee questions belong to CANCEL; actual order-cancellation requests belong to ORDER.

The indirect request to speak with someone receives FEEDBACK with a score of 0.901. The wording expresses a contact preference under the authored label. This illustrates a category error that the current score cutoff accepts. That score is not a 90.1% reliability guarantee, and raising the cutoff cannot be assumed to solve the problem without losing useful suggestions.

## REVIEW cases that still pass the optional guard

| Case | Public request | Suggested | Observed gap |
|---|---|---|---|
| ambiguous-01 | It does not work. | ACCOUNT | Insufficient context: the failed item or action is unspecified. |
| ambiguous-04 | Something is wrong with what I bought. | ORDER | Insufficient context: the purchase problem and desired resolution are unspecified. |
| ambiguous-08 | I cannot log in and my checkout payment was rejected. | PAYMENT | Two stated problems: login access and checkout payment failure; no recognized affirmative request openings. |

All three have guard status `fewer_than_two_explicit_requests`. The first two do not contain two requests at all. They require a context-sufficiency decision, which the current guard does not implement. The third describes problems rather than issuing affirmative commands. The guard requires recognized affirmative request openings and conservatively skips negated fragments. Its source therefore explains why this declarative example is missed. A high scope score only supports an in-domain decision; it does not establish that one routing category is sufficient.

Of eight REVIEW probes, the original semantic policy withholds three and the optional guard withholds two more. The remaining three are the cases above. Withholding an example is not the same as understanding or resolving it.

## Keep the coverage trade-off visible

The semantic policy accepts 52 of 66 supported requests: 49 correct suggestions and three wrong suggestions. It withholds 14 supported requests, including seven whose forced top category is correct and seven whose top category is wrong. The guard leaves all these supported counts unchanged. All 24 authored unsupported requests are withheld. These counts describe this small reused development set only.

## Next experiment to design

Prioritize a separate offline decision about whether a message supplies enough information for one category, needs clarification, or describes multiple independent problems. Keep that decision separate from the category score and the in-domain scope gate. Evaluate vague and declarative problem statements alongside clear short requests, background context, alternatives and negation; a rule that rejects every short sentence or every occurrence of "and" would introduce predictable regressions.

This is a proposed target, not an implemented or validated ambiguity model. A bounded candidate should be specified before scoring. Report supported coverage, correct and incorrect accepted suggestions, unsupported suggestions, and separate counts for insufficient-context versus multiple-problem cases. Previously viewed examples can explain failures and serve as regression checks, but cannot supply an independent estimate of improvement. Manual labeling remains paused; any automatically authored new cases must retain provisional status.

Do not repeat the existing character-feature pilot as though it were an untested remedy. The [recorded hybrid comparison](23-spelling-robustness-pilot.md) improves typo top-category correctness from 16/22 to 17/22, but regresses on indirect wording, leaves total supported top-category correctness at 56/66, and reduces accepted supported requests from 52 to 47. The [native solver comparison](32-native-solver-comparison.md) changes none of these decisions. Both findings argue for targeting the specific missing decision capability and measuring regressions, rather than assuming a larger or more tightly fitted classifier will fix it.

## Audit trail

Source report SHA256: `3deab97ad11da9c38afbb40de15a4ee52ef8da43c1801792c89e6b53f83050aa`.

The six case IDs and counts above were checked programmatically against that report. This is documentation-only analysis: no prediction code, model weights, thresholds or browser behavior changed. No validation/test files, private reviews or pending reserved cases were opened.
