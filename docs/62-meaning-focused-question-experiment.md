# Meaning-focused question experiment

The assistant-guided review, confirmed by Dr Ola, covered all 12 follow-up cases: nine passed applicable wording checks; two failed ambiguity/action-preservation checks; one failed because a needed referent question was omitted. These judgments were proposed by the assistant and confirmed in chat, not independently collected blinded ratings. They concern interpretation questions, not the correctness of all role/category/grouping decisions.

Version 0.40 adds the explicit meaning-focused question contract. It extends the existing constrained clarification prompt with guidance to preserve both action alternatives on a known object, resolve demonstrative references using the complete message, and distinguish interpretation ambiguity from later fulfilment details. The previous ask-only default and reused-constrained option remain available.

Only the third pass system prompt changes relative to reused-constrained. The full none/ask/note schema, first-pass focused classifier, grouping prompt, evidence preservation, model settings, three-call count and shared deadline remain unchanged. The new variant uses prompt_version 3 and a distinct prompt hash. No repair, automatic rewriting or extra model call is added. Structurally valid but semantically wrong questions can still pass validation and must be inspected.

Known cancellation category and alternative-role errors remain outside this isolated change. Do not interpret an improved question as correction of the first-pass role. No website default is changed.

Run both observed suites as development regression checks:

```bat
python -m support_ticket_ai.combined_pilot --model qwen2.5:7b --question-contract meaning-focused --suite role-contrasts --output artifacts/combined-7b-meaning-focused-regressions.json
python -m support_ticket_ai.combined_pilot --model qwen2.5:7b --question-contract meaning-focused --suite frozen-followup --output artifacts/combined-7b-meaning-focused-followup.json
```

Compare against the previous reused-constrained reports. Check the original simultaneous-request and negation cases for renewed unnecessary questions, as well as both alternative questions and the unresolved order reference. Automated decision/reason/evidence metrics still do not assess wording; create another question-review worksheet for the new report if needed. Existing worksheets are bound to their original report and cannot be reused for different model outputs.

No live quality improvement is claimed before these runs. The follow-up suite name is retained for compatibility; its cases have now informed prompt development and are not unseen data. A later new collection is required for further generalization evidence.

Automated transport tests compare the first two requests and third-pass schema/input with the prior contract and ensure only the third-pass system differs. They also verify that even an authored bad question and wrong request role remain visible rather than being silently corrected. Such tests establish composition behavior, not model understanding.
