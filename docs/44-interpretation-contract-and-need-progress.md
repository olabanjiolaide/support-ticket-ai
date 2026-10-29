# Interpretation contracts and individual need progress

Version 0.21.0 adds human-authored action/target references and unknowns to reviewed needs, plus independent need progress. It does not add a new extraction model, execute customer operations, or measure a model-quality improvement. The optional local proposal model still produces the existing goal/obstacle draft; these new fields are filled by the reviewer. Manual bulk labeling remains paused.

## Interpretation contract

| Concept | Meaning in this application | Boundary |
|---|---|---|
| Goal | Desired customer outcome, using the existing need title and Goal kind. | An obstacle is not automatically a request for a specific remedy. |
| Obstacle | Reported barrier preventing progress, using the existing Obstacle kind and evidence role. | It does not establish causality or authorize a password reset. |
| Proposed action | A human-authored description of a possible step, up to eight per need. | It performs no operation and has no separate action-level completion status in this release. |
| Target reference | Exact text selected from the immutable message, with Unicode start/end offsets. | It identifies wording, not a verified order/customer record. A reviewer can still choose the wrong exact quote. |
| Evidence | Original fragments attached to a need. | Main fragment membership remains one need per fragment. Action target references may share or overlap original source ranges. |
| Unknown | A missing fact or question, up to eight per need. | Recorded unknowns prevent resolving that need until reviewed and cleared, or the need is dismissed with a reason. |

Example: `Cancel order A. Keep order B.` can be two ORDER needs with different actions and target quotes. This preserves the distinction lost by a category set alone. `Find my order number but I cannot access my account.` can remain an ORDER goal and ACCOUNT obstacle without inventing a password-reset action or assuming login is required to retrieve the number.

## Browser walkthrough

1. Save the request explicitly and open its breakdown. Generate or manually edit the evidence and need groups.
2. On each need, expand **Proposed actions, targets and unknowns**. Add proposed actions as descriptions and enter missing information one line at a time.
3. For an action, expand **Choose target wording from original message**, select the exact target phrase in the read-only original message and choose **Use selected target**. Selecting a later occurrence of repeated wording preserves that occurrence's offsets. Clear the target if the message does not identify one; do not invent it.
4. Explicitly **Save grouped review**. It validates the complete interpretation but does not confirm the parent category or start handling. New-request analysis can now be saved with the request as an unreviewed draft; human review still needs explicit confirmation and saving. See [draft handoff](46-needs-draft-handoff.md).
5. Confirm the parent category and **Start handling**. The current parent category is a primary human routing label, not a complete representation of all needs.
6. In **Progress for each need**, add a note and **Start need**. Later add completion evidence and **Resolve need**, or **Dismiss with reason** when no work should proceed. Dismissal is not a statement that the customer's issue was solved.
7. **Mark resolved** on the parent is rejected while any saved need remains open or in progress. Finishing the last need does not automatically resolve the parent; a separate parent resolution note is required.
8. Reopen the parent before revisiting a closed request, then **Reopen need** with a note. Other completed needs retain their outcomes.

Each progress update reloads the last saved interpretation. Save interpretation edits before updating progress. Reviewer names and completion notes are self-reported; this remains an unauthenticated local single-user prototype.

## State and audit rules

- Need states: `open -> in_progress -> resolved`; `open` or `in_progress` may become `dismissed` with a reason. Closed states must return to `open` before further changes. Every progress transition requires a note and current parent revision.
- Starting or resolving a need requires the parent to be in progress with its category reviewed. Resolving also rejects UNCLEAR kind/category, conditional/alternative/unclear fragments and recorded unknowns. Investigation may start while an unknown exists.
- A need description, category, kind, proposed action, target, unknown or assigned evidence change resets its active progress to open. Its earlier state remains in history. Completed/dismissed interpretations must be reopened before changing or removing them. Saving an unchanged interpretation preserves progress.
- Relationships remain interpretation hypotheses. They are not automatically scheduled dependencies or verified causal facts. This release does not enforce a dependency order between needs.
- Resolving a need records a reviewer-reported outcome for the entire need. When its proposed actions need independent ownership or completion states, create separate completable needs; individual action execution/status remains future work.
- Original message and original model prediction remain immutable. Progress updates neither retrain models nor modify the parent category/status.
- Request-level optimistic revisions cover both interpretation and progress writes. Two competing updates cannot both succeed on the same revision; stale updates return 409.

## Compatibility and storage

Need-review schema 3 adds `actions` and `unknowns`; schema 1/2 payloads remain accepted without these nonempty fields. The SQLite schema advances to 3 by adding `request_need_progress`. Existing request records, review JSON and event history are retained. Existing saved needs initially have open progress when no individual outcome was recorded. Existing resolved parents are not silently reopened; reopen them explicitly if their new individual progress must be reconciled.

The new endpoint is `POST /requests/{id}/need-progress` with `version`, `actor`, `need_id`, `status` and `note`. It operates only on saved, validated needs and returns the updated request with `need_progress`. Structural target validation rejects altered quotations, bad offsets and unsupported schema fields. Exact target text is necessary but does not prove semantic correctness or establish business permission.

## Practical learning and validation

This milestone demonstrates source-grounded references, schema evolution, additive database migration, transaction boundaries, state machines and optimistic concurrency. Try resolving one of two needs, then attempt parent resolution: the server should reject early closure. Inspect history after correcting an in-progress interpretation to see why its progress resets.

Automated checks cover exact/forged targets, two needs sharing a category, unknowns, partial completion, dismissal, reopening, interpretation changes, migration and concurrent writes. The browser check uses Unicode text, selects target quotes, saves/reloads the contract, tests blocked parent completion and checks phone/desktop widths. Existing proposal-draft and evidence-editing regressions remain separate from live-model evaluation. Ambiguous references across conversation turns, verified external entities, automatic action extraction, reviewer adjudication and action-level workflows remain unimplemented.
