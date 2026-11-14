# Experimental staged interpretation

The uploaded v4 live development report returned eight structurally valid outputs, but missed refund goals in both coordinated requests and confused historical, resolved and conditional roles. This experiment separates role/category classification from grouping. It is available only in the local evaluation runner; ordinary server behavior continues to use prompt v4.

Pass 1 classifies every numbered original excerpt. Pass 2 groups its active needs, with access to the full source and the provisional classifications. The server rejects missing IDs, changed roles or active categories between passes. Original evidence and existing review validators still apply. The shared 120-second budget covers both passes; model identity is checked before and after. Classification errors are not automatically corrected. Model output remains untrusted and requires human review. First-pass or cross-pass validation failures terminate the experiment rather than generating a canned replacement.

Run the same authored cases on the same local model:

```bat
python -m support_ticket_ai.proposal_pilot --model qwen2.5:1.5b --suite evidence-regressions --interpretation-mode single --output artifacts/needs-single-comparison.json
python -m support_ticket_ai.proposal_pilot --model qwen2.5:1.5b --suite evidence-regressions --interpretation-mode staged --output artifacts/needs-staged-comparison.json
```

Staged output identifies prompt version 5 and interpretation_mode=staged. The ordinary single-pass generator remains version 4. The two passes increase model calls and may increase latency; elapsed time includes both passes. generation_attempts counts outer attempts, not model calls. Invalid stage outputs are reported as failures, not successes. Compare omissions, category/kind errors, role confusion and clarification wording, not merely structural success. Repeat in reverse order before interpreting latency. These reused development cases are not an independent accuracy estimate.

Mocked contract tests verify two-pass evidence preservation, data handoff, ID rejection, role/category drift rejection and the possibility that incorrect first-pass meaning still survives. No live Qwen improvement has been established in the implementation workspace, where Ollama is unavailable. The uploaded report is not published in the repository.
