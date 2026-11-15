# Frozen follow-up evaluation

The reused-constrained combined run matched all 16 authored needs and produced no unexpected or missing customer questions across 14 reused inputs. The first pass still labeled an explicit alternative as a request; its question also confused an action with an order identifier. The model omitted a condition note, while deterministic source preservation retained the conditional fragment. These are development observations, not independent accuracy estimates.

Version 0.38 adds 12 new authored messages with provisional labels established before observing their live outputs. They cover multiple services, separate order targets, prohibitions, access/payment obstacles, completed/history evidence, two conditional instructions, two alternative choices, and one ambiguous referent. They are informed by known failure families and several are close paraphrases: do not describe this as an independent held-out or representative benchmark. A human should review the provisional labels and question wording.

The prompts, schemas and model settings are unchanged. This release adds a suite selector; the previous suite remains the default. The website defaults remain unchanged. Snapshot hashes of the selected prompts (UTF-8 SHA-256):

- focused role prompt: `08748c057b8c80bc60ce6fe91d33212dc4e9d4b75d80bfae5d0946b1e3b4cdcc`
- group prompt: `7917da644bd8515addc3223a342c70abb5b85136affd6710db75d8b2d35dcb9a`
- constrained clarification prompt: `be100187d533ae416325a979980ac8a5153c93dbf23498db9b1640383647e3a8`

Run once with the existing 7B model:

```bat
python -m support_ticket_ai.combined_pilot --model qwen2.5:7b --question-contract reused-constrained --suite frozen-followup --output artifacts/combined-7b-frozen-followup.json
```

Inspect every output before deciding on UI integration. Report structural failures separately; examine role confusion, missed/extra needs, questions that contradict negation, action/object wording, and exact conditional evidence. The two conditional notes are scored as notes in raw clarification metrics and as none in customer-question metrics; preserved evidence is scored separately. Do not silently relabel cases or tune prompts after inspecting results and continue calling the same suite unseen. Any changes should be documented as development, with another fresh evaluation reserved for later.

No live results are available for this suite yet. Automated checks validate fixture alignment, clarification contracts and disjoint input text, not semantic correctness of the provisional labels.
