# Clarification-only development evaluation

The anchored grouping report returned 13/14 valid proposals but included four clarifications where the authored reference expected none, omitted two expected clarifications, and rejected a conditional case for a missing note. Additional questions may be useful for fulfilment; this experiment explicitly evaluates interpretation ambiguity rather than operational information collection.

The standalone clarification_pilot sends only the original message and numbered source fragments. It does not depend on generated group titles, receive expected decisions, alter the grouping candidate or execute customer actions. Decisions are none, ask, or note. Questions identify ambiguous targets, alternatives or unclear meaning. Notes identify understood conditional instructions. Every question/note has a reason and supporting fragment IDs; none requires empty evidence and text. Local identity, response bounds and a shared 120-second budget apply, with one generation per case. Invalid outputs are failures, not repaired plans.

The 14 reused inputs have provisional authored decisions: ask which order for the ambiguous address, ask which outcome for either/or, and record a note preserving the conditional refund. Other cases expect no interpretation question. This deliberately does not require identity checks, order IDs or policy details needed to fulfil a request; a clear request's unknown answer is not itself ambiguous meaning.

```bat
python -m support_ticket_ai.clarification_pilot --model qwen2.5:7b --output artifacts/clarification-7b.json
```

Reports retain original evidence, decision, reason, text, model digest, expected decisions, failures and elapsed time. Inspect question/note wording. Metrics compare decision/reason and evidence-ID sets, not useful or truthful wording. The set is prompt-informed development evidence, not independent accuracy. Classification, grouping, UI review and save behavior are not evaluated. The ordinary server and anchored candidate are unchanged. Automated tests use authored outputs; live improvement is unverified.
