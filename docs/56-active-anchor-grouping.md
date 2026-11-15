# Active-anchor grouping experiment

The constrained 7B run returned 11/14 structurally valid proposals. Remaining rejected cases involved excluded-only groups and a missing conditional note. Ambiguous-address and either/or cases also lacked clarification. This release introduces anchored mode while retaining prior modes and ordinary web-server defaults.

Each proposed group names an anchor_fragment_id and its member fragment_ids. The source-specific schema restricts anchors to active classified evidence. Runtime validation independently requires that the anchor be active and included in that group's members. Every fragment appears once in a group or in ungrouped; active fragments cannot be ungrouped. Group IDs are assigned by returned group order, not inferred from text. Roles/categories retain their first-pass values and normal evidence/category consistency checks still apply. Excluded-only source permits zero groups.

If first-pass roles include conditional, alternative or unclear, the output schema and runtime validator require nonblank clarification. This enforces presence, not useful wording. It cannot detect every ambiguous target, and the first-pass either/or error is unchanged. No rule silently changes model meaning or invents a clarification. Wrong same-category merges or inaccurate titles remain possible and require inspection. No inferred relationships are produced.

```bat
python -m support_ticket_ai.proposal_pilot --model qwen2.5:7b --interpretation-mode staged --role-prompt focused --grouping-contract anchored --suite role-contrasts --output artifacts/grouping-7b-anchored.json
```

Compare with grouping-7b-constrained.json on the same reused 14 development cases, including failures, merged/missed goals, excluded evidence, conditional/alternative meaning, actual clarification wording and elapsed time. Prompt version 8 identifies this output. Schema changes narrow the task but do not establish semantic quality. No live improvement is claimed before the local comparison. This CLI run does not verify the website save/review workflow or independent generalization. Tests use authored outputs to check anchors, empty-group exclusion, coverage, required notes and transport/evidence preservation.
