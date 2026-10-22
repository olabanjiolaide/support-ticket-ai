# Human-assisted request breakdown (0.16.0)

## Problem and behavior

A withheld whole-message category gives a reviewer no fragment-level assistance. The optional separate-request guard also stops when the outer prediction already abstains. The new preview runs independently: **Break down message** is available on New request and every saved request detail page, even without a loaded model. The existing whole-message prediction and guard are unchanged.

This release adds a review tool, **not a learned intent extractor or evidence of improved prediction accuracy**. It proposes punctuation/coordination boundaries. Every fragment starts **Not reviewed**. A sentence is not automatically a need, and a category mentioned in text is not automatically requested.

## Try it

1. Update the repository, restart the existing server and refresh the browser.
2. Enter a message or open a saved request through Review queue. Choose **Break down message**.
3. Read the full message and each exact text fragment. Choose Current request, Background / context, Unclear, Conditional, Alternative, Not requested or Already resolved.
4. For a current request, choose a human category, Outside current categories or Unclear. Optionally ask the selected model for a **fragment-only hypothesis**. This calls the existing `/predict` endpoint independently of the whole-message result. It retains the existing model cutoffs and never automatically fills the human category. A missing model or failed prediction still allows manual review.
5. On a saved request, enter a clarification/coordination note where needed and choose **Add reviewed breakdown to note draft**. Existing draft text is preserved; the combined 2,000-character limit is checked without silently truncating.
6. Enter a reviewer label and use **Add note** to persist the reviewed interpretation. This preserves original message and model snapshot, appends the lifecycle history and does not confirm an overall category, resolve the request or create tasks. Use Needs clarification separately if handling should wait for an answer.

For the special-offers example, a human can mark the offers question as a request outside the taxonomy, pending deliveries as background, and ambiguous order-history wording as unclear. Ask whether the order history disappeared; do not silently change “I have see” into “I cannot see.” This is an example of reviewer judgment, not an automatically inferred result.

## API and evidence contract

`POST /breakdown` accepts only `{ "text": "original message" }` (nonblank, at most 2,000 Unicode code points). It does not require a database or model, perform inference, log customer text or save data. The response carries method/version, unchanged source, exact half-open character offsets, original fragment text and `role: unconfirmed`. Offsets count Unicode code points, not JavaScript UTF-16 units. The browser uses returned fragment text rather than slicing with UTF-16 offsets.

Rules propose boundaries after sentence punctuation/semicolons/newlines and before selected “and + subject” patterns. They retain punctuation and conjunctions and skip only whitespace. At most 12 fragments are returned; the final fragment groups **all** remaining text and a warning is displayed. No non-whitespace evidence is dropped. Condition/alternative cues are prompts for inspection, not semantic decisions. Abbreviations, decimals, quotes, causal links and cross-sentence references can produce poor boundaries. Review them against the original.

Fragment classification is allowed only after the reviewer marks Current request. The full message may still change its interpretation; isolation can lose negation, alternatives, reference and scope. Current safeguards cannot prove independence or discount eligibility. A single fragment can contain multiple needs. No automatic semantic reconstruction or invented answers are produced.

Notes store reviewer roles/categories by evidence range, any separately requested model hypothesis and its fingerprint, plus clarification text. They are inspectable narrative history, **not structured task records or training ground truth**. Previews and drafts do not survive navigation/reload; only explicitly saved notes persist. New-request preview edits do not transfer automatically when saving the request; generate a fresh preview on the saved detail page.

## Validation and next research step

Service tests check Unicode evidence, complete coverage, bounded tail grouping, validation/privacy and independence from models/storage. Browser checks cover source-edit invalidation, real word-model fragment prediction, manual category separation, explicit note persistence, unchanged lifecycle, model-unavailable fallback, HTML-safe rendering and 320/390/1440-pixel layouts in both themes. Browser fixtures are synthetic; semantic model inference is not claimed as tested here.

Next evaluate a learned proposal generator using the existing ActionPlan validation contract, with independently annotated needs, evidence spans and request/context/relationship labels. Compare against this human-assisted boundary baseline. Measure intent precision/recall, background false positives, reference/condition errors, unsupported subrequests, clarification usefulness, single-request regression and latency. Existing reused development cases can guide debugging but cannot establish independent improvement. Reviewed needs need a structured persistence contract and explicit confirmation before becoming linked tasks. No new labeling session is required for trying this release.
