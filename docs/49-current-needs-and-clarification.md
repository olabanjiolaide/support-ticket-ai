# Current needs and useful clarification (v0.26.0)

## Observed constraint

The user's three PDF exports show numbered evidence working but a structurally valid interpretation missing the REFUND goal. The model labels “and also check if the refund had been made for my cancelled ordered.” as context under ORDER. It also asks the customer to provide the order number and refund status they requested. These are semantic errors; passing exact evidence checks did not establish completeness.

Three options were considered: strengthen interpretation instructions with contrasting examples; add lexical rules that reject suspected omissions; or add another model pass. This release selects the first as the smallest measurable intervention. Keyword rejection could misread historical and negated refunds, and another model pass adds latency without independent evidence of quality. No semantic improvement is claimed before a live comparison.

## Change

Numbered-fragment prompt version 4 explicitly distinguishes current requests about past events from background, recognizes status questions as requests, preserves negation and conditions, and separates independently answerable outcomes. Contrasting examples cover current refunds for cancelled orders, historical cancellation, negated refunds, conditional refunds and genuinely unclear targets.

Clarification should ask about ambiguous meaning, not ask customers to supply the answer they requested or invent identity requirements and business policies. When intent is understood and only its answer is unknown, an empty clarification is appropriate. These instructions are not semantic validators: a model can still ignore them. Evidence, structural checks, two-attempt budget and human review remain unchanged. No rule silently adds a refund need or edits a model's interpretation.

The regression suite now contains eight authored development cases. It includes the reported sentence and examples used in prompt development, so results are debugging evidence only, not an independent generalization estimate. Automated diagnostics count missed/extra needs, matched category errors, and unexpected/missing clarification presence relative to the authored reference. Presence does not establish clarification usefulness; inspect its wording. Reports use metric version 3.

## Compare on the PC running Ollama

Both commands use identical evidence, model, decoding settings and suite, changing only the prompt. The first preserves version 3 for comparison; normal server startup defaults to version 4. Run while no other generation is active:

```bat
python -m support_ticket_ai.proposal_pilot --model qwen2.5:1.5b --suite evidence-regressions --fragment-prompt-version 3 --output artifacts/needs-prompt-v3.json
python -m support_ticket_ai.proposal_pilot --model qwen2.5:1.5b --suite evidence-regressions --fragment-prompt-version 4 --output artifacts/needs-prompt-v4.json
```

Compare failures, missed needs, extra needs, matched category errors, role confusion, clarification presence and elapsed time. Inspect every clarification and conditional interpretation. A valid response that omits REFUND remains a failure of interpretation. Repeat in reversed order before interpreting latency, since loading and caching affect it. The broader eight-case suite is also available with `--suite development`.

Tests use authored/mocked outputs to verify prompt selection, distinct hashes, identical source payloads, unchanged structural acceptance, the observed omission diagnostic, and fixture validity. Ollama is unavailable in the implementation workspace; live Qwen accuracy and latency remain unmeasured here.
