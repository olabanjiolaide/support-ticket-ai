# Focused role definitions: experimental comparison

The 7B classification-only run improved over 1.5B on the eight reused cases, but treated a negative refund instruction as active and keeping a second order as an alternative. This release adds a focused role prompt only to the classification evaluation runner. Baseline remains the default. The server and staged evaluator retain their prior prompts.

The variant distinguishes a prohibited action from a reported problem (“cannot log in”), simultaneous instructions on different orders from either/or choices, and resolved facts from current requests. No lexical rule overrides model output. Six additional authored contrast cases supplement the original eight unchanged cases; the combined suite is named role-contrasts. Both prompts must be run on that same suite:

```bat
python -m support_ticket_ai.fragment_pilot --model qwen2.5:7b --role-prompt baseline --suite role-contrasts --output artifacts/roles-7b-baseline.json
python -m support_ticket_ai.fragment_pilot --model qwen2.5:7b --role-prompt focused --suite role-contrasts --output artifacts/roles-7b-focused.json
```

Compare valid responses, role errors, active category errors, demoted requests, promoted excluded evidence and elapsed time. Reports identify the selected prompt, suite and their hashes. Model, decoding, original source and schema are unchanged. This remains a small prompt-informed development comparison, not a held-out accuracy result. Repeat in reverse order for latency interpretation. A classification-only experiment cannot establish grouping, clarification or end-to-end readiness. Live results remain pending; automated tests validate fixtures and prompt selection, not Qwen's semantic quality.
