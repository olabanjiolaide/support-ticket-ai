# Carry analysis into a saved request

Version 0.23.0 connects New request analysis to saved requests and displays separate proposal, editing, human review and persistence states. It does not change classifier weights or proposal prompts. No new model-quality result is claimed.

## One save, two distinct records

When New request contains an AI proposal, an editable breakdown, or both, the save button becomes **Save request + needs draft**. This explicitly saves the original request and a separate unreviewed needs draft in one SQLite transaction. A failed draft write rolls back the request/event creation as well. The existing optional fresh category-prediction setting still applies.

The snapshot can contain an unadopted proposal, adopted model interpretation, or incomplete manual choices: unconfirmed fragments, blank need titles/categories, incomplete action descriptions, exact source targets, relationships and clarification. It never records the review checkbox as a completed human decision. Proposal generation and adoption alone still write nothing to storage.

The saved detail page restores that analysis after navigation or browser reload. It shows **Unreviewed draft saved**. Existing model-derived choices remain model hypotheses; manual choices remain pending human review. No overall category is confirmed, no need handling is started, and no request is resolved.

Only the source plan is carried forward. Restored proposal identity details say it is a saved unreviewed draft rather than presenting client-supplied metadata as verified model provenance. The original category prediction remains its separate immutable server-generated snapshot.

## Browser walkthrough

1. Enter a message and generate proposals, or build/edit a manual breakdown. An unadopted proposal can be saved directly; adoption is not a prerequisite for preserving it.
2. Choose **Save request + needs draft**. Saving is disabled while generation or breakdown preparation is still running; controls are locked while the save is in flight.
3. Open the saved record. If the proposal is still separate, choose **Use as editable draft**. Adopted or manual choices restore in the editor.
4. Inspect every need, role, category, target, relationship and unknown. The global review checkbox is unchecked on handoff, even if it was checked in New request. Confirm again on the saved request and enter the reviewer label above.
5. Choose **Save grouped review**. This validates the complete human interpretation, archives the initial unreviewed snapshot in that review event's before-state, and removes the pending draft in the same transaction.
6. Continue category review and individual-need handling separately. A request with a pending transferred draft cannot be resolved; its interpretation must first be reviewed and explicitly saved. Existing per-need completion safeguards still apply afterward.

Changes made after opening the saved record are not automatically saved as drafts. Until **Save grouped review**, reloading restores the originally transferred unreviewed snapshot. The workflow indicator labels those later changes **Unsaved changes**. This release does not add background autosave or a separate save-partial-draft endpoint for existing requests.

## Honest workflow states

The **Analysis to saved review** panel shows current state rather than a fabricated completion percentage:

| Stage | Examples | Meaning |
|---|---|---|
| Proposed | `2 AI need(s)` / `No active AI proposal` | The current optional model candidate, not a human decision. |
| Editable draft | `Awaiting adoption` / `2 editable need(s) · adopted` | Whether the proposal has entered the editor, or manual needs exist. |
| Human review | `Review incomplete` / `Confirmation required` / `Ready for explicit save` / `Confirmed` | Validation and human acknowledgment are distinct from selecting prefilled roles. |
| Saved | `Not saved` / `Unreviewed draft saved` / `Unsaved changes` / `Human review saved` | Whether this interpretation is actually durable and in what capacity. |

Fragment counters now say **interpretations selected**. Model-prefilled roles no longer masquerade as completed human reviews. Once a human review is saved, its current interpretation and history are authoritative; the proposal counter does not invent a cumulative model-run history.

## Data and compatibility

Draft envelope schema 1 contains `editable`, `proposed`, `model_draft` and `proposal_adopted`. Editable plans use a separate bounded draft contract. Incomplete decisions are permitted there, while source coverage, exact Unicode ranges, target quotations, unique need IDs and valid existing references remain required. The stricter `NeedReview` contract is unchanged; it still rejects unconfirmed/incomplete human reviews.

`POST /requests` accepts optional `needs_draft`. Its source must match the exact original message. Requests with a draft preserve leading/trailing whitespace so offsets remain correct; existing no-draft requests retain their trimmed-message behavior. The idempotency hash includes the draft. Retrying an unchanged save cannot create duplicate requests or resurrect a draft after human review. Changing the payload while reusing a save key returns 409.

SQLite schema 4 adds `request_needs_drafts` without rewriting existing requests, reviews, progress or history. `GET /requests/{id}` returns `needs_draft` separately from `need_review` and `need_progress`. Creation history records the unreviewed save; explicit review history retains its original before-state. Storage remains the existing plaintext local single-user prototype, with self-reported reviewer labels.

## Learning and checks

This milestone demonstrates atomic transactions, idempotent retries, draft versus committed state, source-offset preservation and honest UI state machines. Try saving an unadopted proposal, reloading it, adopting it and confirming it: each stage should remain distinguishable.

Unit checks cover partial manual data, strict reviewed-plan rejection, exact Unicode evidence, mismatched/forged source, transaction rollback, migration, pending-draft resolution guards and retry behavior after review. The browser check uses declared authored AI responses to test unadopted/adopted proposals, manual partial choices, confirmation reset, reload, explicit human save, blocked saves during generation, and a server write whose first HTTP response is deliberately lost. Phone/desktop layouts and existing proposal/handling safeguards remain covered separately. No additional manual labeling or live-model benchmark is required for this engineering check.
