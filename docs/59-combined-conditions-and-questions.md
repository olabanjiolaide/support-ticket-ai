# Combined evaluation with conditions separate from questions

The constrained clarification experiment returned 14 valid decisions but omitted the conditional-refund note and produced awkward either/or wording. This evaluator separates preserving classified conditions from asking customers to clarify their meaning. It is CLI-only and leaves existing evaluators and server defaults unchanged.

There are three model calls under one shared 120-second deadline: focused fragment classification; active-anchor grouping without a clarification field; and a constrained ask/none question decision. No expected labels are supplied to any pass. First-pass roles/categories are preserved. Python records each classified conditional fragment's exact original text and offsets in preserved_conditions. It does not infer the condition's truth or synthesize a new condition. Wrong first-pass roles can still omit a real condition.

Legacy NeedReview requires a note for conditional, alternative or unclear roles. The evaluator supplies a labeled quote of that classified source evidence for compatibility, then appends a question only when the question pass returns ask. The detailed report retains question and preserved_conditions separately. Exact quoted conditional evidence can thus survive even when no customer question is needed. This is not a silent repair of model output: it is an explicit change assigning source preservation to Python. The question pass cannot return note. Group coverage/category/evidence checks remain required, and no inferred relationships or actions are generated.

```bat
python -m support_ticket_ai.combined_pilot --model qwen2.5:7b --output artifacts/combined-7b.json
```

The report has full grouping diagnostics, separate question-decision metrics, and missing/extra conditional-fragment counts. For question metrics only, the authored conditional note expectation becomes none; condition preservation is scored separately. Legacy grouping metrics still include presence of the compatibility note. Condition counts compare whole classified fragments, not fine-grained condition spans or correctness of condition interpretation. Question wording and useful group titles still require inspection.

Failures retain their stage and attempted model-call count, and remain in the denominator. This reused 14-case development suite is not independent generalization evidence or a browser/save/review evaluation. Additional model calls can increase latency. Automated checks use authored responses to verify exact condition preservation despite a none decision, separation of questions, invalid note rejection and three-call composition. Live combined semantic quality is unverified until this local run.
