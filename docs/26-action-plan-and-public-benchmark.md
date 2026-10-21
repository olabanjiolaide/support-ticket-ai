# Action-plan contract and public multilabel benchmark

This milestone implements the first step of the [research roadmap](25-public-repository-review.md): a validated output format for proposed support actions and a reproducible importer for a public multilabel benchmark. It trains no model and changes no live prediction behavior. It requires no additional user labeling.

The subsequent [first multilabel baseline](27-first-multilabel-baseline.md) uses the training and selection partitions only; preparation itself remains independent of training.

## Two separate tasks and vocabularies

The proposed action-plan contract uses our existing **11 Bitext support categories**. BlendBanking77 uses its native **77 banking intent labels**. No mapping or automatic interchange between these vocabularies is introduced.

BlendBanking77 can support training/evaluation of intent sets. Its intent labels cannot, by themselves, validate action descriptions, source offsets, conditions, negation scope, or relationships. That richer problem remains distinct from multilabel classification.

## Validated action-plan format

`support_ticket_ai.action_plan` defines strict Pydantic models. The [generated JSON Schema](../data/action_plan_schema.json) publishes their structure. The [authored example](../data/action_plan_example.json) shows two proposed actions for `Change my account email and refund my last purchase.`. It is marked `authored_example`, not represented as model output.

Each action has an ID, description, category if resolved, source evidence, status, and disposition:

| Status | Required disposition | Meaning of the representation |
|---|---|---|
| requested with known category | review | Proposed affirmative action; a human must confirm it |
| requested with unresolved category | clarify | Routing remains unresolved |
| conditional | clarify | Condition evidence is mandatory; do not treat it as unconditional |
| unclear | clarify | Further information is required |
| negated | excluded | Recorded for inspection, excluded from proposed affirmative actions |
| context | excluded | Background information, excluded from proposed affirmative actions |

Source offsets use Python/Unicode **code points**, start inclusive and end exclusive, in the unchanged original message. Every span must reproduce the exact source substring. JavaScript uses UTF-16 code units for ordinary string indexing; a future browser integration must convert or use code-point-aware indexing before displaying spans.

The validator rejects unknown categories, extra fields, invalid/forged offsets, duplicate action IDs, unknown/self-referencing relations, duplicate relations, dependency cycles, nonfinite scores, and incompatible statuses/dispositions. Conditional actions require condition evidence. Unresolved coordination or alternatives require a clarification outcome/question in this initial conservative contract. A `model_proposal` requires a model fingerprint; authored examples cannot attach one. Human review must be explicitly true.

The JSON Schema does not express every cross-field/span constraint. Use the Python validator for those checks. Structural validation does **not** establish that the text supports a category, that a condition was interpreted correctly, or that an action description is faithful. A valid-looking model fingerprint is not authentication. This module performs no inference or actions and is not an HTTP endpoint.

```bat
python -m support_ticket_ai.action_plan --file data/action_plan_example.json
python -m support_ticket_ai.action_plan --schema
```

The example returns `valid: true`, two actions, and mandatory human review. There are no action cards or automatic request-planning predictions in the current browser.

## Chosen public benchmark

We selected **BlendBanking77**, the English Banking77-derived subset in [HYU-NLP/BlendX](https://github.com/HYU-NLP/BlendX), at revision `8828e46ea6b5b30d7a9a9c34a4f0f499e7d74efa`. Its publisher source path is `v1.0/BlendX/BlendBanking77.json`.

Despite its `.json` filename, the pinned source is JSON Lines: each line contains `domain_id`, `split`, `utterance`, and an `intent` string containing a Python-style list of labels. The importer uses `ast.literal_eval` for that list and validates the result; it never uses `eval`. Label spellings and capitalization are preserved rather than normalized to our app categories.

The [pinned source configuration](../data/blendbanking77_source.json) records URLs, exact sizes, SHA-256 checksums, revisions, and publisher/underlying license metadata. The publisher README states GPL-2.0 for its repository and contents. The underlying BANKING77 repository supplies CC-BY-4.0 attribution terms. Preparation retains both license texts, the BlendX README, attribution, and source fingerprints under the ignored artifact directory. This records the observed source notices; it does not treat a repository license as a universal license for every downstream use.

No third-party dataset rows, trained weights, or copied implementation are committed to this repository. The checked-in manifest contains preparation metadata, label names, and aggregate counts.

## Development partitions and findings

The publisher file contains 36,390 train, 2,009 dev, and 2,021 test row prefixes. Only train and dev payloads are decoded for this preparation. Train/dev exact-text groups are normalized using NFKC, case folding, and whitespace collapse. Matching text is deduplicated; conflicting label sets would be quarantined rather than voted on. When identical text appears in both train and dev, the dev representative is retained and matching training copies are removed.

The import found **870 duplicate development rows**, **three train/dev overlap groups**, and no exact-text label-conflict groups. These counts are an audit of this pinned source, not a general judgment of dataset quality.

Publisher dev becomes selection data. A fixed seed-42 hash reserves approximately 20% of the retained publisher-train exact-text groups for future calibration/conformalization before any training occurs. It is not a stratified split; label coverage is checked and the tool fails instead of reshuffling if coverage differs.

| Prepared partition | Requests | Future purpose |
|---|---:|---|
| train | 28,338 | Fit a multilabel baseline |
| calibration | 7,183 | Separate probability calibration or conformalization experiments |
| selection | 2,008 | Compare fixed candidate settings |
| sealed publisher test | 2,021 raw records | Future locked evaluation after protocol/leakage review |

All three decoded learning partitions cover the 77 native labels and contain requests with one, two, or three labels. No classifier, calibration method, threshold selection, or final evaluation has run on these data in this milestone. If both probability calibration and conformalization are later fitted, reserve separate subsets or explicitly justify a valid reuse procedure; this reservation is not automatic permission to reuse calibration labels for arbitrary tuning.

The [recorded preparation manifest](../reports/blendbanking77-v1/preparation_manifest.json) includes partition hashes, per-label and label-cardinality counts, transformation details, and known limits.

## What “sealed test” means here

The public download necessarily contains the complete upstream file. The importer recognizes the leading ID/split metadata and copies test lines byte-for-byte into `sealed_test.jsonl`. It hashes those bytes and counts row prefixes, but does not JSON-decode the test utterance/intent payloads, inspect their labels, transform them into training targets, or score predictions on them.

This is an auditable workflow boundary, not access control. The raw source also remains in the local artifact for provenance. Test payload JSON validity and train/test text overlap have not been audited. Original component-utterance IDs for generated combinations are not supplied in these rows, so exact-text groups cannot establish independent composition families. Those leakage questions must be addressed before a conclusive external benchmark claim.

The existing Bitext held-out test and the paused private/reserved review collections remain unused. These public benchmark labels are not extra manual-review tasks for the user.

## Reproduce preparation

From the updated source checkout:

```bat
python -m support_ticket_ai.benchmark_prepare artifacts/blendbanking77-v1
```

This downloads about 9.6 MB of pinned source plus notices, verifies all four source/license files, writes new learning partitions and an opaque test copy, and records the manifest. Existing output directories are never overwritten. A local directory of the exact files can be supplied with `--source-dir` for offline reproduction.

The manually triggered **Prepare public multilabel benchmark** Actions workflow validates the contracts/tests and uploads the prepared artifact with source notices. Its later-added `run_baseline` option runs the [fixed train/selection experiment](27-first-multilabel-baseline.md) by default; turn it off for preparation only. It does not host a model. The wheel includes the contract schema/example and pinned source configuration; the checked-in aggregate preparation manifest is repository documentation.

## Validation and next experiment

Tests cover Unicode offset handling, source-text preservation, human-review requirements, model-proposal provenance, action/relation consistency, source checksums, duplicate/conflict handling, row-order-independent partitioning, non-executing intent-list parsing, and preservation of existing outputs. A deliberately non-decodable test payload fixture proves preparation never JSON-parses held-out payloads.

The subsequent native-taxonomy [multilabel baseline](27-first-multilabel-baseline.md) reports exact-set accuracy and micro/macro-F1 before attempting richer action extraction. A public intent benchmark is a reproducible learning step, not evidence that the proposed planner is already implemented or scientifically novel.
