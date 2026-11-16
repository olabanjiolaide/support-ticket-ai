# Source-quoted clarification representation

The paired v0.41 run produced 24/24 structurally valid outputs. Meaning-focused fixed the cancellation-choice wording on that input, but both prompts missed the unresolved order reference and both turned the change/keep address choice into an address preference. Neither prompt generated a conditional-cancellation note. This isolates clarification-stage behavior; it does not establish complete model correctness or evaluate combined source preservation.

Version 0.42 introduces a separate CLI-only experiment. One model call returns kind and exact source quotes. Kinds are none, action_choice, unresolved_target, conditional_note and unclear_meaning. Python validates quote membership and cardinality, attaches original code-point offsets, and renders a fixed question or note. The model does not write a free-form customer question.

| Kind | Representation | Rendering |
|---|---|---|
| none | No quotes | Empty none decision |
| action_choice | Two to four quoted alternatives | Which option would you like: quoted alternatives? |
| unresolved_target | One quoted reference | Which item do you mean by quoted reference? |
| conditional_note | One whole conditional instruction | Exact source quote as a note |
| unclear_meaning | One unclear expression | Could you clarify what you mean by quoted expression? |

Run on the earlier complete report:

```bat
python -m support_ticket_ai.clarification_representation --model qwen2.5:7b --input-report artifacts/combined-7b-frozen-followup.json --output artifacts/questions-7b-representation-followup.json
```

All 12 messages reach this stage regardless of grouping outcomes. One generation per input, no retries or repairs, existing local model identity checks and 120-second per-case budget. Source report, payload, schema and prompt hashes are recorded. Existing prompts, paired evaluator and website defaults are unchanged.

This changes the prompt, schema and renderer together. It is not a pure prompt comparison. Inspect the kind, exact quotes and rendered decision together, comparing with the paired report. Exact source membership cannot establish that alternatives are real, complete, mutually exclusive or appropriate; a simultaneous pair wrongly extracted as alternatives will still render an incorrect choice. A missed unresolved reference will still yield none. The generic item wording may be awkward. There is at most one interpretation issue per message and each quote is limited to 200 characters; longer source instructions may fail rather than be silently truncated. Repeated text is attached to its first occurrence within the cited fragment, explicitly rather than claiming unique model-selected alignment.

Reports retain the model representation and source-grounded quote offsets; none is not automatically upgraded to a question. Fixed rendering is a documented transformation, not model-generated wording or semantic repair. Conditional notes here remain a model decision and are separate from combined-pipeline condition preservation. Existing human-review worksheet tooling does not yet accept this new format.

Automated tests verify quote offsets, branch cardinality, rejected invented quotes, one chat per input, and faithful fixed rendering. They deliberately retain a semantically wrong but source-valid representation to demonstrate the boundary of validation. Live interpretation improvement remains unverified. These cases remain observed, prompt-informed development examples.
