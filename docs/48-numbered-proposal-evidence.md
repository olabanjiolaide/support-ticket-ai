# Numbered evidence for local needs proposals

The reported order-number/refund example failed the exact-copy generator with `evidence_mismatch` after two attempts. The reports do not contain raw generated output, so they do not establish which character changed or whether all failures had the same cause.

We compared three designs: improve the copying prompt, assign numbered source fragments, or select finer source ranges. Numbered fragments remove text copying from the model's task while retaining the existing evidence and human-review contracts. Range selection remains a future comparison; this release does not implement it.

## Numbered evidence behavior (introduced with prompt version 3)

Python creates at most 24 ordered excerpts using punctuation and selected English coordination boundaries. The original message and each numbered excerpt are supplied to the local model as untrusted data. The model returns a role and need assignment for every fragment ID. It does not supply evidence text or offsets.

The server rejects missing, repeated, reordered or unknown IDs. It reconstructs text from the original message, then applies the same exact coverage, category, group membership, relationship, clarification and cycle validators used by the exact-copy path. It does not repair invalid assignments or synthesize a successful fallback.

The response remains a schema-2 unreviewed proposal compatible with adoption, boundary editing and saved drafts. Additional metadata identifies `evidence_mode`, prompt version, source hash, model digest and the deterministic excerpt method. Prompt identity includes the versioned boundary specification. A restored draft does not claim verified model provenance.

The shared two-attempt/120-second budget, fixed loopback endpoint, local GGUF identity checks, response limit and human confirmation remain in place. Source text and raw model output are not added to error diagnostics. No customer action executes and no category is automatically confirmed.

## Boundaries and limitations

Excerpts are not detected intents. A fragment can contain multiple needs, especially for noun lists, implicit requests, unfamiliar syntax or other languages. The prompt asks for an unclear interpretation when the boundary prevents a faithful assignment. That instruction is not a guarantee of detection. Reviewers can adopt a draft, edit evidence boundaries and correct group memberships.

The regression sentence is split before `and also`, preserving its spelling and conjunctions. That makes two assignments possible; it does not prove the model selects ORDER and REFUND correctly. A structurally valid response can still omit a need, choose the wrong category, invent a relationship or misread a historical event.

## Reproduce on the machine with Ollama

The ordinary serve command now uses numbered fragments by default. To explicitly select the old generator for comparison, add `--proposal-evidence-mode excerpts`. Use `--proposal-evidence-mode fragments` for the new generator. Both use the same installed model; the word/semantic category selector does not change the proposal model.

The original evidence-regressions suite contained three provisional authored cases: the reported coordination/spelling example, a Unicode variant and two ORDER goals with different targets. It does not use the paused private review pilot or protected test data.

Run both commands from the project directory in the working environment, preferably while no other proposal is running:

```bat
python -m support_ticket_ai.proposal_pilot --model qwen2.5:1.5b --suite evidence-regressions --evidence-mode excerpts --output artifacts/evidence-excerpts.json
python -m support_ticket_ai.proposal_pilot --model qwen2.5:1.5b --suite evidence-regressions --evidence-mode fragments --output artifacts/evidence-fragments.json
```

Compare valid responses, failures and attempt counts, missed/extra needs, category and kind errors, evidence roles, relationship errors and elapsed time. The reports retain the denominator including failed generations. Inspect interpretations as well as aggregate scores. The existing eight-case development suite remains available with `--suite development`.

These reused cases are a debugging comparison, not independent evidence of generalization. Model loading, run order and caching can affect elapsed time. Repeat in reversed order before interpreting latency differences. Reviewer correction time is not automatically measured.

## Validation for this release

Unit tests exercise exact spelling, Unicode offsets, repeated text, the fragment limit, ID coverage failures, forbidden model text/offset fields, unchanged relationship checks, bounded recovery, safe API errors, mode identities and all three authored regression plans. Mocked model responses exercise contracts, not Qwen accuracy. Browser checks use authored responses to verify proposal presentation and the existing explicit adoption/review/save behavior.

Live Qwen generation was not run in the implementation workspace because Ollama was unavailable. No live accuracy or speed improvement is claimed. Run the comparison above before concluding that this change improves proposal quality for the installed model.

## Subsequent interpretation update

v0.26.0 defaults to fragment prompt version 4 and expands the regression suite to eight cases. See [Current needs and useful clarification](49-current-needs-and-clarification.md) for the observed semantic failure, limitations and reproducible version-3/version-4 comparison. The evidence adapter is unchanged.
