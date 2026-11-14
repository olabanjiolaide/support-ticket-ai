# Source-keyed constrained membership experiment

The membership-only run accepted 10/14 authored development cases; four failed because classified active fragments were left unassigned. This release adds an optional constrained output shape and text-free diagnostics. The original memberships contract remains available; server behavior remains unchanged.

The second-pass assignments object has one required key for each original fragment. Active classified fragments allow only a non-null need ID; excluded fragments may use null. Unknown keys are forbidden. Python restores source order by original IDs and applies the same group, category, evidence and clarification checks. It neither invents assignments nor repairs missing ones. The schema constrains assignment shape, not correct meaning or valid group references. A runtime validator independently rejects null active assignments even if a model ignores its schema.

Membership failures now include the unassigned fragment ID, its classified role/category and the failing stage in pilot reports. Customer text, titles and raw output are not added to diagnostics. A classifier can still incorrectly label an alternative as a request, and wrong same-category merges can still pass validation. Relationships remain absent in this experiment.

```bat
python -m support_ticket_ai.proposal_pilot --model qwen2.5:7b --interpretation-mode staged --role-prompt focused --grouping-contract constrained --suite role-contrasts --output artifacts/grouping-7b-constrained.json
```

Compare with grouping-7b-memberships.json using failures and their new diagnostics, omissions, group meanings, negation, conditional/alternative roles, clarification wording and time. Prompt version 7 identifies constrained mode. No live improvement is claimed before this run. These reused development cases cannot establish generalization. Tests exercise the source-specific schema, independent rejection, text-free diagnostics, key coverage, source-order restoration and transport integration using authored model responses.
