# Broader ambiguity review collection

## What this milestone prepares

`data/ambiguity_review_cases.csv` contains 72 new, assistant-authored English requests in 18 author-assigned scenario families. It contains case IDs, family IDs, and text only: **there are no preferred answers or model predictions**. Human labels are pending. This collection has not been used for fitting, cutoff selection, or model scoring.

It broadens the earlier pilot with negation, alternatives, contextual details, indirect phrasing, references to missing context, requests for a human agent, and tasks that mention support vocabulary but request something else. Related requests are grouped before training so variations from one author-assigned scenario stay together.

A normalized exact-text check found no matches against the source training split or earlier project development collections, including the 40-case review pilot. Source validation/test were not opened for that check. Template and semantic similarity can still exist.

## Reserve families before training

The versioned `data/ambiguity_review_manifest.json` reserves:

| Partition | Scenario families | Requests | Future purpose |
|---|---:|---:|---|
| Train | 12 | 48 | Fit a candidate request-type model after review |
| Selection | 3 | 12 | Select development settings and thresholds |
| Audit | 3 | 12 | Evaluate the frozen candidate once |

Assignment uses a fixed seed and hash ordering over family IDs. It does not inspect any labels or model scores. The canonical collection hash is stable across CSV row order and Windows/Linux newline conversions. Editing text, IDs, family assignments, or reservations causes verification to fail.

This is a small **reserved audit partition**, not an established independent benchmark. Labels, class balance, category coverage, and a second review are pending. Author groups can share linguistic patterns across partitions. Inspect label coverage before deciding which experiments are supportable; do not repeatedly reshuffle the audit to obtain more favorable scores. Future fitting code must explicitly use only the reserved training IDs; the manifest is an auditable assignment, not a physical access-control mechanism.

Verify the shipped reservation:

```bat
python -m support_ticket_ai.freeze_review data/ambiguity_review_cases.csv data/ambiguity_review_manifest.json --verify
```

The generic freeze command can create a new versioned reservation for a separately authored collection, but never overwrites an existing manifest. Pre-scoring status is an author declaration; the tool cannot observe other experiments.

## Review the first five cases

Use Anaconda Prompt in the updated project directory. The existing review tool loads no model and needs no semantic packages:

```bat
python -m support_ticket_ai.review_cases artifacts/ambiguity-review-ola-v1.json --cases data/ambiguity_review_cases.csv --reviewer ola --limit 5
```

Continue later:

```bat
python -m support_ticket_ai.review_cases artifacts/ambiguity-review-ola-v1.json --cases data/ambiguity_review_cases.csv --reviewer ola --limit 5 --resume
```

Keep this progress file separate from the original 40-case review and its reconciled version. Each completed answer saves automatically. `s` skips an unresolved case and leaves it for later; it is **not** the label for an unrelated request. `4` records an unsupported task. `q` stops the session. There is no requirement to finish all 72 in one sitting.

Reviewers see text and annotation rules, without model outputs or suggested labels. The underlying progress file continues to use the generic pilot/non-adjudicated status until review and reconciliation are explicitly completed. It stays under ignored `artifacts/` and is not automatically published.

## Apply the refined rules consistently

- Label the **requested outcome**, not every topic mentioned. A background purchase or prior return does not automatically add ORDER to a refund-progress request.
- The word **and** alone does not establish multiple routing intents. Several details or actions can belong to one routing category.
- **Negated requests** should not add an intent: identify what the person actually wants performed.
- **Alternatives** are not automatically simultaneous requests. If the intended outcome is unresolved, use insufficient context or skip for contract discussion.
- When **account access** is the task and an agent is the preferred way to obtain help, use the account routing category and mention the human preference in the optional note. A standalone request to reach customer care remains CONTACT.
- Missing an order number does not by itself make a clearly stated intent ambiguous. Missing the actual requested action or its referent can require clarification.
- A creative, translation, schoolwork, or coding task can be unsupported even when it contains a support category name.

Use the category vocabulary in [the human-review guide](16-human-label-review.md). If a request combines a supported and unsupported task, or exposes an unresolved policy distinction, skip it rather than force a convenient label. Record the case ID for discussion. Human disagreement is evidence that the task definition needs attention, not a reason to silently replace a reviewer answer.

## What follows review

Preserve original annotations. Compare a second review without exposing the first answers, adjudicate disagreements with a change log, and retain any assistance provenance. Keep the audit's model outputs uninspected until candidate choices are frozen. Human labeling an audit before evaluation is allowed; fitting, threshold selection, or example-specific tuning on its labels is not.

Only after sufficient reviewed coverage exists should we fit an explicit request-type baseline and consider task-specific encoder fine-tuning. This milestone creates that preparation and partition discipline; it does not train ambiguity handling, improve accuracy by itself, alter the running app, or justify autonomous routing.
