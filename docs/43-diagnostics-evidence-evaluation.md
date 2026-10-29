# Diagnostics, editable evidence and proposal evaluation

Package 0.20.0 adds operational diagnostics, manual evidence boundaries and stronger development metrics. It does not change classifier weights or establish improved live-model accuracy. Manual labeling remains paused.

## Check the application you are running

Open **Application diagnostics** above the workspace. It shows the application version, page/server frontend build identities, loaded word/semantic bundle hashes, request-storage availability and optional local proposal status. **Refresh diagnostics** checks again without sending the customer message. Unavailable diagnostics are explicit; configured-but-unavailable proposals are distinct from unconfigured proposals.

The package and OpenAPI now use `support_ticket_ai/version.py` as their version source. The HTML and its complete relative JavaScript import graph use a content-derived asset URL prefix. Workspace assets and diagnostics receive `Cache-Control: no-store`. A page/server build mismatch asks for a reload; a match establishes build identity, not correct rendering or model quality. Diagnostics do not expose local filesystem paths or saved tickets. They remain part of the existing unauthenticated, local single-user demo.

## Split or merge evidence yourself

1. Enter a message and choose **Break down message**, or open a saved request's breakdown.
2. Expand **Edit evidence boundaries**. Choose the fragment, then place the cursor inside it in the read-only original message. Choose **Split at cursor**. The position is shown in original Unicode characters.
3. To combine adjacent fragments, choose the first one and **Merge with next fragment**. Original whitespace between fragments is retained.
4. Review the changed fragments again, attach them to needs, and select human categories. No text is rewritten. Unchanged fragments retain their choices; changed fragments reset to Not reviewed and lose their assignments/categories. Relationships involving changed evidence are removed instead of being guessed. Existing need definitions remain editable, including empty needs that must be repaired or removed before saving.
5. **Undo boundary edit** restores the entire draft from before the last boundary edit, including its review choices. Review changes made after that edit are also replaced. Up to 20 local edit snapshots are retained; changing the source, rebuilding the preview, adopting a proposal, reloading or leaving the request clears them.
6. A saved request changes only after **Save grouped review**. The original message, overall category and handling status are unchanged. Adopted model drafts still require the review checkbox; boundary edits clear that confirmation. New-request drafts remain temporary and do not automatically transfer when creating a saved request.

Example: `Find my order number but I cannot access my account.` can be split before `but`, allowing an ORDER goal and ACCOUNT obstacle to be reviewed independently. This is a reviewer-authored interpretation, not an automatically verified dependency or a new model prediction.

## Measure proposal errors beyond category sets

The existing command remains:

```bat
python -m support_ticket_ai.proposal_pilot --model qwen2.5:1.5b --limit 3 --output artifacts/proposals-pilot-v2.json
```

It requires an explicitly configured local Ollama model. If unavailable, it exits with **No evaluation was performed**. No new labeling is required; the eight existing authored development examples remain provisional, with protected tests and the private review pilot unused.

Metric version 2 adds:

- One-to-one need matching by active, non-whitespace source-character intersection-over-union (IoU >= 0.5). Matching maximizes match count, then overlap; category and kind are deliberately ignored during matching and checked afterward.
- Missed/extra needs, wrong categories and goal/obstacle/unclear kinds for matched needs. Extra needs are an evidence-based mismatch count, not a definitive semantic hallucination judgment.
- Role confusion counts by source character, including negated or resolved text incorrectly marked active.
- Missing/extra relationship edges using matched endpoints, relationship type and direction. Alternative links are symmetric; dependency/blocking links are directed. For matched edges, original evidence-character sets are compared separately.
- Elapsed seconds per attempt, mean and nearest-rank p95 including failures. Small development-run timings are diagnostics, not a controlled hardware benchmark.
- Explicit attempted/valid/failed counts. Quality totals cover valid structured responses only; structural success uses all attempts. Failures never silently become correct results.

Reports retain the original four comparison fields and include application version, fixture SHA256, selected model identity/digest, prompt identity in successful proposals, matching rule and limitations. Evidence overlap and exact text validity do not prove correct meaning. Clarification usefulness, equivalent alternative decompositions and relationship explanations still need inspection; no automatic promotion threshold is introduced.

## Practical learning

- **Web delivery:** change a frontend file and compare its build identity after restart. Understand why versioned module URLs avoid mixing assets from different releases.
- **Data contracts:** split a message containing emoji, then inspect the explicitly saved review. Python source slices must reproduce every stored fragment exactly.
- **ML evaluation:** swap categories between two correctly counted needs. Category-set agreement can stay perfect while evidence-aligned category errors increase.

## Verification

API checks cover version consistency, content-addressed assets, no-store headers and omission of private paths. Node checks cover source preservation, Unicode offsets, invalid splits and conservative relationship invalidation. Python metric regressions cover swapped categories, missing/extra needs, relationship direction, exclusion errors and failure denominators. The real-browser evidence check covers diagnostics mismatch/retry, split/merge/undo, explicit save/reload, unchanged parent handling and 320/390/1440-pixel layouts. Installed-wheel browser checks run in CI. No live language-model quality result is asserted by these checks.
