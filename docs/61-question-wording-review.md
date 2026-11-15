# Reviewing question meaning separately from decision scores

The v0.38 frozen follow-up run on qwen2.5:7b returned 12/12 structurally valid responses, matched 13/13 expected needs and preserved both authored conditional fragments. There were two category errors (actual order cancellations labeled CANCEL instead of ORDER), two alternative-to-request role errors, and one missing question for an unresolved order reference. Mean elapsed time was 8.80 seconds; this is one run, not a controlled speed comparison.

The action-choice output asked “Which order, Z, would you like to cancel?” although the input offered cancelling or keeping the same order. Decision/reason/evidence metrics marked the question correct: they do not evaluate its wording. The delivery-choice question also shifted an action choice into an address preference. History evidence was left ungrouped in the history-and-current case; the existing active-evidence overlap metric does not detect that contextual attachment difference. Do not interpret matching need counts as complete semantic correctness.

Version 0.39 adds an offline JSON worksheet and summarizer, with no model calls or prompt/server changes. It binds reviews to the original report bytes using SHA-256 and verifies case order, source text and question content against that report. Reviewers edit only each case's review object. The worksheet contains original customer text and questions: keep it with the local report rather than publishing private support messages.

Create a worksheet:

```bat
python -m support_ticket_ai.question_review --report artifacts/combined-7b-frozen-followup.json --output artifacts/followup-question-review.json
```

Each valid case starts unreviewed. Enter a reviewer name, notes and ratings. For an ask, all four criteria require pass or fail:

| Criterion | Review question |
|---|---|
| decision_appropriate | Is a question needed to understand the intent? Is silence appropriate for a none decision? |
| resolves_ambiguity | Does it resolve the actual ambiguity and retain the available alternatives? |
| preserves_actions_and_targets | Does it keep action choices separate from object identifiers and respect negation? |
| no_invented_requirements | Does it avoid invented priority choices, business rules or repetition? |

For a none decision, rate decision_appropriate pass/fail and mark the other three not_applicable. Null ratings or a blank reviewer leave the entire case unreviewed. Failed model generations remain separate generation failures and cannot receive wording ratings. A missing question should receive fail for decision_appropriate, even though no question text exists.

Summarize a completed or partially completed worksheet:

```bat
python -m support_ticket_ai.question_review --report artifacts/combined-7b-frozen-followup.json --review artifacts/followup-question-review.json --output artifacts/followup-question-review-summary.json
```

Outputs never overwrite existing files. The summary reports reviewed, unreviewed and failed generations separately, plus per-criterion failures. It does not infer semantic ratings or certify correctness. This is a review aid, not a substitute for source interpretation, independent evaluation or multiple reviewers. These follow-up cases are now observed development cases. Any subsequent prompt changes must be described as tuning on development evidence.

The CLI schema, report binding and accounting have automated tests. Unit tests with authored responses do not establish question quality. Website integration remains deferred while the documented interpretation failures remain unresolved.
