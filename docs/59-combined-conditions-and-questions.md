# Combined evaluation with conditions separate from questions

The constrained clarification experiment returned 14 valid decisions but omitted the conditional-refund note and produced awkward either/or wording. This evaluator separates preserving classified conditions from asking customers to clarify their meaning. It is CLI-only and leaves existing evaluators and server defaults unchanged.

There are three model calls under one shared 120-second deadline: focused fragment classification; active-anchor grouping without a clarification field; and a constrained ask/none question decision. No expected labels are supplied to any pass. First-pass roles/categories are preserved. Python records each classified conditional fragment's exact original text and offsets in preserved_conditions. It does not infer the condition's truth or synthesize a new condition. Wrong first-pass roles can still omit a real condition.

Legacy NeedReview requires a note for conditional, alternative or unclear roles. The evaluator supplies a labeled quote of that classified source evidence for compatibility, then appends a question only when the question pass returns ask. The detailed report retains question and preserved_conditions separately. Exact quoted conditional evidence can thus survive even when no customer question is needed. This is not a silent repair of model output: it is an explicit change assigning source preservation to Python. The question pass cannot return note. Group coverage/category/evidence checks remain required, and no inferred relationships or actions are generated.

```bat
python -m support_ticket_ai.combined_pilot --model qwen2.5:7b --output artifacts/combined-7b.json
```

The report has full grouping diagnostics, separate question-decision metrics, and missing/extra conditional-fragment counts. For question metrics only, the authored conditional note expectation becomes none; condition preservation is scored separately. Legacy grouping metrics still include presence of the compatibility note. Condition counts compare whole classified fragments, not fine-grained condition spans or correctness of condition interpretation. Question wording and useful group titles still require inspection.

Failures retain their stage and attempted model-call count, and remain in the denominator. This reused 14-case development suite is not independent generalization evidence or a browser/save/review evaluation. Additional model calls can increase latency. Automated checks use authored responses to verify exact condition preservation despite a none decision, separation of questions, invalid note rejection and three-call composition. Live combined semantic quality is unverified until this local run.


## Reusing the constrained clarification component (v0.37)

The first combined live run returned 14 structurally valid results, preserved the one authored conditional case, and matched all 16 expected needs. Its custom question prompt nevertheless produced five unexpected questions, including invented either/or choices for simultaneous requests. These development results do not establish accuracy on new messages.

Use the new explicit option to reuse CONSTRAINED_SYSTEM and the entire constrained none/ask/note schema from the standalone clarification pilot, unchanged:

```bat
python -m support_ticket_ai.combined_pilot --model qwen2.5:7b --question-contract reused-constrained --output artifacts/combined-7b-reused-constrained.json
```

The default ask-only option preserves the previous experiment. Both variants retain three model calls, the same grouping pass and source-based condition preservation. This comparison changes both the custom prompt and its ask-only schema back to the existing component; it does not isolate prompt wording alone.

Reports retain the raw clarification_decision. An ask is also the customer question; a note is explicitly projected to an empty none question and is never appended to the review or used to create preserved_conditions. Raw clarification metrics score notes against the original authored expectations, so a hallucinated or missing note remains visible even when customer-question metrics omit notes. Preserved condition metrics still depend on first-pass labels. The report records the selected contract and its prompt hash. No server default changes. Live results for this option are pending; automated checks verify exact prompt/schema reuse and separation of model notes from source evidence.
