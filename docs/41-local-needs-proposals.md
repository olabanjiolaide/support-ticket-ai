# Experimental local language-model proposals (0.18.0)

## What this adds

The existing sentence encoder scores categories; it does not generate interpretations. This optional feature connects to a **separate local Ollama language model** to propose goals, account-access obstacles, background, uncertainty, finer evidence boundaries and relationships. It is off by default. The app never substitutes an authored fixture or rule output when the model is missing.

**Release validation covers the integration and interface, not the semantic quality of a real language model. No live local LLM was available in the development environment.** The UI tests use explicit authored model-response stubs. No accuracy improvement, breakthrough or independent benchmark result is claimed.

## Enable on Windows

1. Install Ollama from its [official Windows download](https://ollama.com/download/windows). Start it locally. Choose local downloaded weights, not a cloud model. Ollama's [local-only settings](https://docs.ollama.com/faq#how-do-i-disable-ollamas-cloud-features) describe disabling its cloud features; restart Ollama if you change those settings.
2. An illustrative smaller starting model is `qwen2.5:1.5b`. Its suitability for this task still needs evaluation; larger models may make different errors and require more memory. Check the [official model page and license](https://ollama.com/library/qwen2.5:1.5b). Download it explicitly:

```bat
ollama pull qwen2.5:1.5b
```

3. Stop the app with Ctrl+C. Update the checkout from the Conda base environment, then use the existing working environment:

```bat
conda activate base
git pull --ff-only
conda activate support-ticket-ai
python -m support_ticket_ai.serve --model-dir artifacts/demo-v1/model --semantic-model-dir artifacts/semantic-v1 --proposal-model qwen2.5:1.5b
```

The proposal feature needs neither an OpenAI API key nor a change to the sentence-encoder bundle. `SUPPORT_TICKET_PROPOSAL_MODEL` is the equivalent server environment variable. The adapter only connects to `http://127.0.0.1:11434`, ignores proxy environment variables and does not follow redirects. It requires a matching installed local GGUF model entry. The Ollama installation is managed separately: the app cannot verify the internals of an arbitrary service listening on that local port. Use a trusted local installation and its local-only configuration.

4. Refresh with Ctrl+F5. In **Understand the individual needs**, check the local model status and choose **Generate needs proposals**. Status checks list installed models; they do not generate text or download weights. CPU generation can be slow and has a two-minute server read timeout. One generation per application worker is allowed at a time; the normal single-worker local server remains the intended deployment.

## Review, then save

Generation creates a **separate proposal preview**. It does not replace current editable choices or persist customer messages. Inspect each proposed need, its exact source excerpts, type/category and any proposed relationship. Choose **Use as editable draft** only when you want to replace unsaved grouping choices in that tab. Failed, cancelled or stale responses do not replace the editable review. Cancelling stops waiting in the browser; local generation may still be finishing, so an immediate retry can return Busy.

The draft can split “Please find my order number, but I cannot access my account” into separate exact excerpts for an ORDER goal and an ACCOUNT obstacle. This is a possible interpretation, not a promised result. A `may_block` link is explicitly a **review hypothesis**, not proof of a causal relationship. The model must not invent that cancelling an order caused an account-access failure.

You can correct need titles, goal/obstacle/unclear types, categories, fragment roles and memberships, relationship types/notes and clarification text. Remove an unsupported relationship rather than confirming it. Changing group membership can invalidate relationship evidence; server validation then rejects the save until it is corrected or removed. The UI does not yet support arbitrary manual splitting, shared fragment membership across multiple needs or adding new relationship evidence selections. Model-proposed finer partitions and API-validated editable spans are the first step toward that editor.

Before saving or staging a model-derived draft, check the statement that you reviewed the evidence, roles, categories and relationships against the full message. This is a local review acknowledgment, not authentication. **Save grouped review** is available on a saved request detail page after entering a reviewer label. Main-composer proposals and editable drafts can now be preserved with **Save request + needs draft**. They remain unreviewed on the saved request; see [draft handoff](46-needs-draft-handoff.md).

Saved records remain human-reviewed interpretations. The model identity is inspectable in the proposal preview; model scores or client-provided model fingerprints are not accepted as verified provenance in the human-review API. Use the development pilot report if you need a record of the original generated response and its model/prompt fingerprint. Saving does not change the original category prediction, the overall human category or handling status, and creates no operational tasks.

## Evidence and structural checks

- Schema-constrained generation uses Ollama's [`/api/chat`](https://docs.ollama.com/api/chat) JSON `format`, `stream:false`, temperature 0, seed 42 and bounded generation/context options. See the [official structured-output documentation](https://docs.ollama.com/capabilities/structured-outputs).
- The app computes character offsets from the original message, not model-supplied counts. At most 24 ordered excerpts must preserve every non-whitespace source character. Changed, omitted, repeated-extra or reordered evidence is rejected; spelling and punctuation are not normalized.
- The version-2 review document accepts exact finer source partitions while retaining version-1 review compatibility. Need categories/types are constrained; every current or unresolved request/obstacle needs a group. Background alone cannot create a need.
- Links must connect existing distinct groups and cite valid evidence from both. Dependencies cannot form cycles. Uncertain roles/categories/types and all links require clarification/coordination text. These checks do **not** prove the interpretation or relationship is correct.
- Completed output and matching model identity are required. The local model manifest digest is checked before/after generation and included with the source/prompt SHA-256 hashes. Responses are size-limited. Generation has no tools, action execution or automatic training path.
- Prompt instructions treat the submitted message as untrusted customer data. Schema/evidence validation reduces structural failures; it does not establish resistance to every prompt injection or prevent unsupported semantic claims. Human review remains necessary.

HTTP: `GET /proposals/status`, `POST /proposals` with `{ "text": "..." }`. Missing local configuration/model returns unavailable; busy, timeout and invalid generation return explicit failures with no applied draft. Submitted text and raw model failures are not included in validation/error messages or application logs.

## Run the real-model development pilot

Eight provisional authored cases are bundled in `data/needs_proposals_development.json`. They cover goal/obstacle separation, historical context, independent needs, negation, insufficient context, unsupported requests, conditional alternatives and a resolved background issue. They are **not independently adjudicated ground truth** and are separate from the paused manual-review pilot and locked test splits.

Once local Ollama is available, run a small pilot explicitly:

```bat
python -m support_ticket_ai.proposal_pilot --model qwen2.5:1.5b --limit 3 --output artifacts/proposals-pilot-v1.json
```

The report records valid/failed responses separately, category-set match, need-count match, non-whitespace character-role agreement and relation-kind-set match, plus complete generated drafts and fingerprints. Different boundaries can be compared by character roles; metrics do not require identical sentence splits. Category sets and relation-kind sets do not measure complete grouping/edge correctness. Inspect the actual evidence, errors, unsupported causes and questions rather than treating these coarse diagnostics as deployment approval. Invalid generations are not dropped silently. Model absence aborts without an evaluation result.

Before promotion, independently annotate and freeze a separate evaluation set, assess grouping and link precision/recall, clarification usefulness and false causal claims, and compare representative models/configurations. Keep reused development-case results and engineering tests separate from independent accuracy evidence. No further manual labeling session is needed just to install or try this integration.
