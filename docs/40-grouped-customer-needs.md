# Group related fragments into customer needs

Version 0.17.0 adds **human-authored groups**, not automatic semantic extraction. A message with three sentences can describe one current goal. The original category suggestion remains independent of this review.

## Try the workflow

Use a message such as:

> My order was cancelled last week. I cannot find the item again. Is it out of stock?

1. Choose **Review individual needs** after a prediction, or **Break down message** directly. This also works when the model withholds its overall category.
2. Choose **+ Add customer need** and enter a title such as “Locate the item and check availability.” Select the need's human category, Outside current categories or Unclear. ORDER is a possible broad routing choice here; it does not establish actual stock availability.
3. In the expandable fragments, mark the first sentence **Background / context** and the other two **Current request**. Attach all three to the same need. You may leave unrelated background unassigned. Creating a group does not infer a relationship: you choose the membership.
4. Optionally choose **Suggest category using need evidence**. The existing selected model receives the assigned original excerpts in source order, joined with newlines. It retains the existing thresholds. Its hypothesis does not change the human category.
5. Ask for the product name or link in the clarification field if those details are needed. The placeholder is now generic; no automatic question generator or inventory lookup is claimed.
6. To persist a structured review, first save the request and perform the grouping on its detail page. Enter the reviewer label above and choose **Save grouped review**. Main-composer groups are temporary and do not transfer automatically when saving a new request.

Grouped fragments use the need's category. Their separate category controls and prediction buttons are hidden to avoid asking for duplicate classification. The summary reports the number of needs **drafted by you**, background fragments and review progress. Saved groups reopen with the fragment details collapsed; expand them to inspect or edit the evidence. Removing a group unassigns its fragments rather than deleting their source evidence.

## What is saved

The local database stores exact original text and character spans, reviewer roles, group membership, reviewer-written goal titles, human need categories and a clarification/relationship note. Each fragment currently belongs to at most one group; attaching one background fragment to several needs is not supported yet. A group can combine non-adjacent fragments. Negated, historical or completed material must not be mistaken for a new task: roles are decisions made by the reviewer.

Each save appends a **Customer needs reviewed** history event with both previous and new structured snapshots. The latest review reloads after page refresh and server restart. Original message/prediction and the overall human category, review state and handling status stay unchanged. Group reviews do not create operational tasks, change overview/category counts or become training ground truth. Reviewer labels remain self-reported.

Optional machine hypotheses are transient and are not accepted as verified model provenance in the structured review API. The existing optional **Add reviewed breakdown to note draft** path remains available; it is a separate narrative note, explicitly saved with Add note. Structured saving neither clears nor implicitly saves that external note draft.

If another tab updates the request, saving a stale grouped review returns a conflict and keeps the draft. **Reload saved request** explicitly replaces unsaved grouped edits with the latest saved review; it preserves the separate handling-note draft. Resolved requests must be reopened before saving new grouped reviews. A timed-out save may have completed on the server: reload to inspect the recorded version before retrying.

## Service and migration

`POST /requests/{id}/needs-review` accepts `version`, `actor` and `review`. The document contains `schema_version: 1`, unchanged `source_text`, `parts`, `groups` and `clarification`. `support_ticket_ai/need_review.py` defines the strict schema and cross-field validation. Every source fragment must be present once with exact text and Unicode code-point offsets. Current or unresolved requests must be assigned to a group. Every group needs a title/category and at least one current or unresolved request; background alone cannot create a need. Unresolved roles or an Unclear need category require clarification text.

Saving is a transaction guarded by the request version. Source mismatches, stale revisions and resolved-request edits are rejected. Input validation does not echo customer text. The SQLite schema upgrades additively from version 1 to 2 by adding the grouped-review table; existing request records and events are preserved. Older app versions cannot open schema 2 for request storage, so retain a database backup before any intended downgrade. Nothing is exported or committed from the user's database.

## Validation and remaining NLP work

Tests cover grouping integrity, omitted/duplicated/forged evidence, unknown/empty groups, strict categories, unresolved relationships, source mismatches, old-schema migration, atomic competing writes, lifecycle preservation and history. Browser checks use a synthetic fixture and real word-model inference for grouped evidence, plus explicit save, refresh/restart persistence, conflicting tabs and desktop/mobile light/dark layouts. They do not establish semantic-model accuracy or an improvement in intent extraction.

This is the representation and review workflow needed before evaluating a learned extractor. It does not automatically infer that a cancellation was historical, resolve “it,” propose a goal, predict a primary objective or determine whether an item is available. Concatenating selected evidence is not a context-trained classifier. Boundaries can still split related text incorrectly or leave several needs in one fragment; reviewers can group several fragments but cannot yet split a fragment manually. Next compare learned proposals against independently annotated goals, roles, memberships and evidence. Keep those evaluation results separate from engineering test counts and reused examples.
