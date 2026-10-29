# Visible proposal actions and validation recovery

Version 0.22.0 makes local needs generation easier to find and its failures easier to diagnose. It retains exact evidence validation and explicit adoption/review/saving. This is an engineering update; success with the user's live local model and semantic accuracy remain unverified.

## What the reported failures establish

The three supplied browser exports showed a configured local model and the same generic evidence/structure validation failure. They did not contain the raw generated plan or identify a failed field. Consequently they establish rejected output, not a unique root cause. Category prediction mode and its optional separate-request checkbox do not select or change the local proposal model.

## Find and use generation

A full-width **Generate needs proposals** action now appears beside the message composer. It opens the existing local proposal panel and starts generation when that model is available. It works independently of whole-message category readiness. If local generation is unavailable, it opens setup details and focuses **Check local model** instead.

The needs panel repeats generation as its primary action, shows an availability/generation/draft/error badge, and gives **Check local model**, cancellation, retry and error-copy controls distinct button styles. On phones the action buttons fill the available width. Keyboard focus outlines remain visible, reduced-motion preferences disable spinner animation, and status announcements do not repeat every second. A separate visible elapsed timer has no invented completion percentage.

Buttons remain hidden in printed PDFs. Error descriptions and safe diagnostic codes remain printable. Use the browser for interaction.

## Bounded regeneration

Prompt version 2 spells out required fields, null references, group IDs, optional empty relationship lists and exact evidence. It includes one authored example of distinct needs sharing a category. This is prompt guidance, not proof the model understands those distinctions.

Generation keeps a two-attempt maximum within one 120-second server time budget. Only an invalid generated JSON/plan triggers a second complete generation. The second request contains the same original customer message and an application-owned validation code/hint. The previous raw model response is not added to the retry request. A valid first response needs no retry.

Both attempts must pass the same schema, source coverage, quotation, group membership and relationship checks. There is no punctuation normalization, dropped evidence, invented default plan, fallback prediction or automatic adoption. Network errors, changed model identities and incomplete generations are rejected rather than repeatedly retried. The browser allows a short response margin and discards late replies after cancellation or source editing. Cancelling in the browser may leave the local model finishing the server request.

## Error codes and next steps

| Validation code | What it identifies | Next step |
|---|---|---|
| `invalid_json` | Generated content could not be parsed as JSON. | Retry; inspect repeated failures before changing models. |
| `schema_invalid` | Required fields, types, enum values or reference syntax failed schema validation. | Copy the diagnostic code and attempts for investigation. |
| `evidence_mismatch` | An excerpt changed, omitted or reordered original text. | Preserve the original; retry or use the manual evidence editor. |
| `unassigned_need` | A current or unresolved fragment has no need assignment. | Regenerate with explicit group membership. |
| `duplicate_need` | Two groups use the same need ID. | Regenerate unique group IDs and consistent references. |
| `unknown_need` | A fragment refers to a need absent from the plan. | Regenerate a consistent plan; no dangling references are accepted. |
| `empty_need` | A group lacks a current or unresolved request/obstacle. | Regenerate or interpret the message manually. |
| `relationship_invalid` | Relationship endpoints, evidence or dependency structure failed validation. | Review whether the proposed relation is warranted. |
| `clarification_missing` | Unclear/conditional/alternative evidence or a relationship lacks its required clarification/note. | Regenerate or write the focused question manually. |
| `interpretation_invalid` | Another reviewed-plan consistency check failed. | Copy diagnostics; do not assume the meaning is correct. |

The outer failure code remains `invalid_output` for invalid model output. HTTP responses add `validation_code`, `attempts` and `prompt_version`. Other outer codes distinguish timeout, busy, local unavailability and identity mismatch. **Copy error details** includes only codes, attempt count, model name and prompt version; it excludes the customer message, generated excerpts and raw validation inputs. Existing CLI pilot failure records include stage and attempt counts too.

Successful proposals record `generation_attempts` and `recovered_from_validation` alongside prompt/model/source identity. A passed structural check does not establish correct categories, targets, causality or clarification usefulness.

## Learning and checks

The practical lesson is to distinguish a model being installed from its output being valid, and structural validity from semantic correctness. A clear failure is preferable to silently converting a malformed interpretation into an apparently successful result.

Unit checks cover valid first responses, repair of altered evidence, repeated schema rejection, distinct group/relationship/clarification failures, the shared time budget, lock reuse and omission of customer text from HTTP errors. Browser checks use declared authored responses to verify the composer shortcut, prominent primary controls, safe diagnostic copying, retry/progress/cancellation, unsaved-draft preservation, zero implicit saves, five widths, two themes and reduced motion. They are integration checks, not live-model accuracy results. The installed-package workflow runs these checks and retains screenshots.
