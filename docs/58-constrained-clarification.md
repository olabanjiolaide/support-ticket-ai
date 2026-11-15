# Constrained clarification comparison

The original clarification-only run returned 9/14 structurally valid outputs, including four unexpected questions/notes. Five failed generic schema validation. This release retains baseline mode and adds --contract constrained. Neither mode enters the website or changes the anchored grouping candidate.

The new anyOf schema defines complete separate object branches: none permits only reason none and empty text/evidence; ask permits ambiguity reasons and requires supported nonblank text; note permits only conditional_instruction and requires supported nonblank text. Runtime coherence and evidence checks independently remain in force. This schema does not establish that the reason is true or the question is useful.

The accompanying prompt distinguishes two simultaneous requests from an explicit choice, and a real conditional instruction from negation or consecutive statements. A model may still ignore these distinctions. No lexical override, fallback question or silent output repair is added. Because prompt and schema both change, this experiment measures the combined intervention and cannot attribute gains to either one alone.

Rejected decisions now include safe rule-level diagnostics for none_payload, missing_support, note_reason, ask_reason or field_shape. Extra model-supplied field names, raw output, customer text and validation input are not echoed. Previous report files are preserved.

```bat
python -m support_ticket_ai.clarification_pilot --model qwen2.5:7b --contract constrained --output artifacts/clarification-7b-constrained.json
```

Compare with clarification-7b.json: failures/diagnostics, decision and reason errors, unnecessary questions/notes, missed questions and actual text. Wording usefulness still requires inspection. The same 14 provisional authored development cases are reused; this is not independent accuracy or an end-to-end evaluation. Prompt version 2 identifies the new intervention. Live improvement is unverified until local evaluation. Automated checks cover branch shape, safe diagnostics and the existing transport/evidence behavior.
