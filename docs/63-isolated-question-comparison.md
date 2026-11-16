# Isolating the clarification comparison

The meaning-focused regression run returned 14 valid responses with no unexpected/missing customer questions. Its cancellation-choice question preserved both actions. The follow-up run returned 11/12 valid responses; the two-services case failed during unchanged grouping before reaching the question pass. The unresolved order reference was still missed and delivery-choice wording remained awkward. Alternative role and cancellation category errors remain upstream issues.

Version 0.41 adds question_comparison, a CLI-only evaluator. It reads every saved original message from a complete combined report and runs only the clarification stage for reused-constrained and meaning-focused. It does not reuse generated groups, predicted roles or expected labels. A report missing any source message is rejected before any model call rather than silently dropping failed cases. Use the earlier complete frozen-followup report, which includes all 12 source messages, not the latest report missing the two-services source.

```bat
python -m support_ticket_ai.question_comparison --model qwen2.5:7b --input-report artifacts/combined-7b-frozen-followup.json --output artifacts/questions-7b-paired-followup.json
```

This runs 24 chat generations for 12 messages: one per variant per message with no retries or grouping/classification. Each generation has the existing 120-second deadline. Both prompts receive identical message text, numbered fragments, constrained schema and model settings. The report records source-report, payload, schema and prompt hashes. Variant order alternates by case; this is not a repeated crossover experiment and does not establish a timing advantage. Per-generation digest checks and comparison with the starting digest reject changed model identities.

Every variant failure remains visible; the summary distinguishes all attempted pairs, pairs where both outputs validated, and each variant's failures. No label score, inferred human rating or improvement claim is produced. Inspect original messages and raw decisions/questions side by side. These cases are already observed development inputs. Website behavior and prompts are unchanged by this release; the experiment cannot resolve upstream role or category errors. The existing question_review command accepts combined reports, not this new paired format.

Automated transport checks verify two chat calls per input, identical payload/schema/options, alternating prompt order and failure accounting without retry. They do not measure live model meaning. Live paired results remain pending.
