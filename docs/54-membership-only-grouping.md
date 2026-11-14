# Membership-only second-pass experiment

The focused full grouping run accepted 7/14 development cases. It still rejected order-number/refund inputs, merged cancel/keep instructions, and omitted clarification. This experiment removes redundant role/category predictions from the second pass. It does not claim those failures are fixed before a live comparison.

The first pass is unchanged. In memberships mode the second pass returns only ordered fragment-to-group assignments, group IDs/titles and clarification. Python carries forward the classified roles and derives each need's category from its active classified evidence. Active fragments in a group must have one non-null common category. Kind is derived as obstacle when all active evidence is obstacle, unclear when any is unclear, otherwise goal. Groups containing excluded evidence only are rejected; excluded-only messages can return no needs. Existing evidence, membership and clarification validators still apply. No fallback repairs model output. Bad first-pass labels and bad same-category grouping can still pass.

This experiment emits no inferred relationships (relations=[]). It cannot measure relationship extraction quality. This is a narrower task than the full second pass; compare its practical tradeoff, rather than treating structural success as semantic equivalence. Explicit action targets and executable operations remain outside this experiment. The web server is unchanged.

```bat
python -m support_ticket_ai.proposal_pilot --model qwen2.5:7b --interpretation-mode staged --role-prompt focused --grouping-contract memberships --suite role-contrasts --output artifacts/grouping-7b-memberships.json
```

Compare with grouping-7b-focused.json on the same 14 reused cases: failures, omissions, merged goals, category/kind errors, negative/conditional evidence, clarification wording and time. Prompt version 6 and grouping_contract=memberships identify the new output. Existing full mode defaults and report files are retained. This is prompt-informed development evidence, not an independent generalization result. Live improvement is unverified. Tests use authored responses for contract validation and explicitly demonstrate that an incorrect merge can still pass structure.
