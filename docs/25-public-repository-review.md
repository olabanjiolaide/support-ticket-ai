# Public repository review and a direction for original work

Initial review: 20 October 2026. This is a review of selected official repository documentation, selected implementation code, and associated paper abstracts. It is not an exhaustive literature survey, a security audit, or a reproduction of published benchmark results. No external model has been installed or benchmarked in this milestone.

## Conclusion

Support Ticket AI is a working engineering foundation with reproducible experiments, a local API, and browser checks. Sentence embeddings, logistic classification, multi-intent prediction, request splitting, conformal uncertainty, and clarification questions are established methods. Adding these components alone does not establish algorithmic novelty.

A useful next direction is to represent all requested support actions with their supporting text, distinguish requests from context/negation/conditions, and decide when an agent needs clarification. This is a proposed direction, not an established gap or a validated new method. The closest work below must inform its design and evaluation.

## Repositories to learn from

The rightmost columns are our proposed applications and assessments, not claims that the repositories lack those capabilities.

| Official repository | What the inspected material establishes | What to investigate for this project | Important boundary |
|---|---|---|---|
| [huggingface/setfit](https://github.com/huggingface/setfit) | Sentence-transformer body with classification heads; explicit support for multilabel strategies. | A reproducible multilabel baseline that can predict ACCOUNT and REFUND together. Inspect contrastive training as a separate baseline from our one-epoch cross-entropy pilot. | Support for few-shot training does not guarantee improvement on our data. Multilabel training needs appropriate target sets; Bitext single-category labels do not supply those by themselves. |
| [aurelio-labs/semantic-router](https://github.com/aurelio-labs/semantic-router) | Configurable routes and encoders; the current README describes indexed routing and calibration for rejection. | Separate route configuration, encoder adapters, and confidence/rejection policy from the HTTP layer. | This is an engineering reference, not proof of multi-intent task understanding. Its current main branch describes a different API line from older tutorials. |
| [VinAIResearch/MISCA](https://github.com/VinAIResearch/MISCA) | Joint multiple-intent detection and slot filling using intent-slot co-attention. | Study supervision and evaluation for multiple intents and the entities attached to them. | Joint intent/entity prediction already exists. Published dataset metrics cannot be compared directly with our 11-category development probes. |
| [HYU-NLP/BlendX](https://github.com/HYU-NLP/BlendX) | A multi-intent dataset suite with more diverse blended patterns, including omissions; construction includes rule-based and generative combinations of existing datasets. | Evaluate beyond splitting text on "and" and use available public multilabel targets to reduce dependence on fresh manual labeling. | Generated/composed examples are not independently collected live support traffic. Source taxonomy, inherited data terms, versions, and overlap need auditing before use. |
| [MrZhengXin/multi_intent_2022](https://github.com/MrZhengXin/multi_intent_2022), associated with DialogUSR | The associated paper splits and reformulates complex utterances while recovering references and omitted information. | Compare context-preserving decomposition with our narrow fragment check. | Splitting a request into sub-requests is not a new contribution by itself. Language and domain compatibility must be checked before transfer. |
| [florisdenhengst/cicc](https://github.com/florisdenhengst/cicc) | Code associated with conformal intent classification and clarification; the paper combines uncertainty, targeted questions, and out-of-scope handling. | A direct comparison for deciding between a category suggestion and a clarification question. | Conformal clarification already exists. We must identify a narrower contribution than adding uncertainty to a classifier. |
| [scikit-learn-contrib/MAPIE](https://github.com/scikit-learn-contrib/MAPIE) | Prediction sets and risk-control tools with scikit-learn-compatible estimators; documentation discusses exchangeability requirements. | Study uncertainty at each action and at the whole-request level, with held-out conformalization data and explicit assumptions. | A single-label prediction set of possible categories is not automatically a set of simultaneous requested actions. Coverage assumptions do not automatically survive domain shift or request decomposition. |
| [clinc/oos-eval](https://github.com/clinc/oos-eval) | A public intent benchmark with explicit in-scope/out-of-scope data; its README states the examples are single-intent. | A separate external benchmark for scope rejection. | Its 150-intent taxonomy differs from Bitext. It cannot validate our multi-intent capability or be treated as entirely unsupported relative to our categories without inspecting the scope definition. |

Specific implementation material inspected includes [SetFit multilabel configuration](https://github.com/huggingface/setfit/blob/main/docs/source/en/how_to/multilabel.mdx) and [its modeling implementation](https://github.com/huggingface/setfit/blob/main/src/setfit/modeling.py). The latter separates sigmoid/BCE multilabel heads from softmax/cross-entropy single-target heads. This is a modeling difference from our current single-category classifier; returning its top two scores would not implement a learned multilabel model.

No third-party source code or dataset is copied by this review. Before any integration, record exact revisions and inspect the relevant code, model, and dataset licenses separately. Repository documentation is an entry point, not a complete compatibility review.

## Closest prior work that limits novelty claims

1. [DialogUSR, Findings of EMNLP 2022](https://aclanthology.org/2022.findings-emnlp.234/) already studies splitting complex requests and recovering omitted/coreferred information. Request decomposition and reformulation therefore need to be treated as existing baselines.
2. [CICC, Findings of NAACL 2024](https://aclanthology.org/2024.findings-naacl.156/) already studies conformal intent classification with clarification and an extension for out-of-scope detection. Calibrated uncertainty plus clarification is not an unclaimed idea.
3. [GL-GIN, ACL 2021](https://aclanthology.org/2021.acl-long.15/) already uses graph interactions for multiple-intent detection and slot filling. Merely adding a graph is insufficient evidence of novelty.
4. [Scaling Intent Understanding, EACL Industry 2026](https://aclanthology.org/2026.eacl-industry.14/) studies lightweight language models for intent classification and clarification, including evaluation of question timing/quality. Small-model clarification and deployment cost also have close prior work.

These findings do not rule out a useful new contribution. They rule out broad first-of-its-kind claims on components that have already been studied. No state-of-the-art or priority claim is made for our project.

## A concrete proposed product behavior

For `Change my account email and refund my last purchase.`, the current optional guard withholds one category. A later planner could instead propose two separately reviewable actions:

| Source text | Proposed action | Category | State |
|---|---|---|---|
| `Change my account email` | Update account email | ACCOUNT | Requires human confirmation |
| `refund my last purchase` | Request refund | REFUND | Requires human confirmation |

Those are design examples, not current model outputs. Showing the source span makes it possible to inspect what supports a proposed action; it does not prove that action was understood correctly.

The design must distinguish cases such as:

| Example | Proposed interpretation to test |
|---|---|
| `Do not cancel my order; just send my invoice.` | One affirmative invoice request; cancellation is explicitly rejected. |
| `My card was charged twice and I want a refund.` | One explicit refund request with payment context; do not automatically invent a second action. |
| `If it has not shipped, cancel it; otherwise send the tracking details.` | Conditional alternatives with unresolved shipment state, rather than two unconditional actions. |
| `Change my account name and reset my password.` | Two actions that share ACCOUNT; a category set alone loses this distinction. |
| `I cannot log in and my checkout payment was rejected.` | Two reported problems requiring investigation; our current explicit-request rules miss this pattern. |

Conditional/negation interpretations are proposed evaluation requirements. The reviewed repositories' capabilities on these particular examples have not been tested. These examples must not later be presented as an unseen benchmark.

## Where innovative design might be needed

The candidate research question is:

**Can a system that preserves text evidence and relationships between requested actions reduce omitted actions and harmful routing errors, at a comparable review rate and CPU latency, relative to multilabel classification and decomposition-plus-clarification baselines?**

Potential work is in the representation and decision policy: distinguishing simultaneous actions from uncertain alternatives, representing conditions and exclusions without inventing actions, and propagating uncertainty from text extraction to individual routes and the complete plan. Existing component methods provide baselines; a specific new mechanism, proof, or reproducibly better operating trade-off would need to be established.

A useful technical distinction is between two kinds of sets:

- A classifier's uncertainty set can mean "one of ACCOUNT or REFUND may be correct."
- A multi-action request can mean "both ACCOUNT and REFUND actions are requested."

These semantics must not be conflated. Standard single-label conformal sets do not by themselves solve simultaneous-action discovery. Likewise, category labels alone cannot identify two distinct actions within ACCOUNT.

MAPIE's [exchangeability guidance](https://mapie.readthedocs.io/en/stable/generated/exchangeability_testing/1-quickstart/plot_exchangeability_online/) explicitly ties conformal/risk-control guarantees to calibration and future data assumptions. Whether an action-level or whole-plan guarantee is valid after a learned decomposition is a question to analyze, not a property inherited automatically from a library.

## Development sequence and learning outcomes

| Step | Concrete result | Practical learning |
|---|---|---|
| 1. Define outputs and evaluation before training | A schema for actions, source offsets, category, request status, and unresolved conditions; benchmark/split manifests. | Task formulation, data provenance, and why a category set is insufficient for an action plan. |
| 2. Reproduce a public multilabel baseline | A pinned SetFit or frozen-embedding one-vs-rest baseline on an appropriate public multilabel dataset. | Sigmoid/BCE or binary heads, exact-set accuracy, micro/macro-F1, and false extra labels. |
| 3. Compare decomposition methods | Current rules versus a context-preserving splitting/reformulation baseline, with source-span validation. | Negation, ellipsis, references, and measuring invented or omitted actions. |
| 4. Add an explicit decision policy | Compare suggestion, clarification, and human review using separate calibration/conformalization partitions. | Risk versus coverage, uncertainty assumptions, and limits of label-free evaluation. |
| 5. Test the proposed contribution | Frozen comparisons and ablations that remove relationships, evidence checks, or uncertainty propagation. | Experimental controls, failure analysis, and reporting the effect of each mechanism. |
| 6. Integrate a successful candidate | Optional action cards in the existing local browser with checked model/decision provenance. | API design, user review, and end-to-end ML engineering. |

The immediate next implementation should be the output contract and a benchmark importer/manifest, before another model change. This review does not authorize claims of measured improvements on the external datasets: none have been run yet.

## Evidence needed before calling it a research contribution

- Keep each public benchmark in its native taxonomy unless an explicit reviewed mapping is justified. Do not directly compare MixATIS/BlendX performance with the current 11-category Bitext scores.
- Pin data versions and audit source-example reuse, duplicates, and composition families. Reserve train, model-selection, calibration/conformalization, and final evaluation data before scoring candidates. The existing Bitext held-out test stays closed.
- Treat the existing 98 authored cases as regression/development diagnostics. Do not rename them an independent test set after repeated use.
- Evaluate intent-set exact match and micro/macro-F1 where the public targets support them. A benchmark with only intent labels cannot establish action-span, negation, or condition correctness without appropriate additional annotations.
- Measure omitted actions, invented actions, inappropriate affirmative treatment of negation/conditions, and incorrect routes using appropriately labeled data. Public labels can reduce annotation needs; synthetic controls do not remove the need for trustworthy evaluation.
- Compare accepted-request error at comparable coverage/review rates, not only at the same numerical threshold. Keep scope rejection, unclear-request handling, and multi-intent completeness separate.
- Report CPU p50/p95 latency and resource use. Review rate and question count are proxies for effort; actual human-time claims require a user study.
- Use multiple seeds where training randomness matters and show ablations. Confirm against the closest literature beyond this initial review before claiming novelty.

The labeling pause remains in force. Public data, protocol design, and reproducible baselines can be developed without assigning more review work to the user. A future claim about richer action/condition outputs may require additional independently checked annotations; that remains a research dependency rather than completed evidence.

## Current status

The local app and trained bundles remain at the existing validated implementation. This milestone adds a comparison and a proposed roadmap only. A distinctive applied portfolio project is already feasible; whether a particular extension is a new scientific contribution remains unestablished.
