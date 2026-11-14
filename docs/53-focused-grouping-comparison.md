# Focused first pass in the full experimental grouping evaluator

The focused 7B classifier produced one role error across 21 fragments on the 14 authored contrast cases, compared with six for the baseline. The remaining explicit either/or case was labeled request rather than alternative. These are reused prompt-informed development results; grouping and clarification were not tested by that classifier-only report.

The proposal pilot now accepts --role-prompt focused for staged mode and --suite role-contrasts. These select the already evaluated first-pass instructions and the same 14 cases, followed by the existing grouping pass. The ordinary server is unchanged. No grouping repairs or relaxed validation were added. Full reports retain failures in the denominator, record the chosen role prompt and preserve the two-pass prompt hash. Existing output paths are rejected to preserve previous reports.

```bat
python -m support_ticket_ai.proposal_pilot --model qwen2.5:7b --interpretation-mode staged --role-prompt baseline --suite role-contrasts --output artifacts/grouping-7b-baseline.json
python -m support_ticket_ai.proposal_pilot --model qwen2.5:7b --interpretation-mode staged --role-prompt focused --suite role-contrasts --output artifacts/grouping-7b-focused.json
```

Inspect grouping, omissions, extra needs, categories, conditions, alternatives, relationships and clarification wording. Clarification presence is a proxy only, not correctness. Negated-only cases should create no active need. Failed responses must not be read as zero semantic errors. Classification-only and full-proposal reports have different tasks and metrics. Repeat in reverse order before interpreting timing. This CLI evaluation does not verify UI adoption, saving or human review. Live full-pipeline improvement remains unverified.
