# Classification-only development pilot

The staged live run returned two valid plans out of eight, with four relationship failures and two consistency failures. It does not establish an improvement. This release isolates its unchanged first-pass prompt and schema in a CLI evaluation, without grouping, relationships or clarification. Server behavior remains unchanged.

```bat
python -m support_ticket_ai.fragment_pilot --model qwen2.5:1.5b --output artifacts/needs-fragment-classification.json
```

Each result retains the original numbered evidence, first-pass role/category output, verified model digest, expected labels, elapsed time and prompt/fixture identity. The eight reused authored cases have aligned evidence boundaries. Failed responses are reported separately. Categories are scored for every expected active fragment even when a model demotes it to background; background category labels are ignored. Counts are fragment diagnostics, not a count of customer needs or general accuracy. This experiment cannot evaluate grouping, clarification or action targets. It uses the same local endpoint, size cap, identity verification and 120-second budget, with one classification attempt per case. No generated plan enters the UI.

Staged failures now inherit their actual outer attempt count instead of defaulting to zero after generation. Existing uploaded reports are unchanged. Neither mode has been shown to improve live semantic quality. Contract tests use authored responses; run the command on the machine with Ollama and inspect the resulting report before changing models or the default interpreter.
