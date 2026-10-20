# Human review pilot for intent and ambiguity

## Purpose

Before more NLP fine-tuning, collect human interpretations of new examples without showing a model's predicted category or suggested answer. This milestone supplies 40 assistant-authored, unlabeled English requests grouped into 20 author-assigned scenario families. It supplies **no gold labels**, performs no model inference, and does not modify the app.

The pilot is for checking the annotation contract and identifying disagreements. It is not a completed benchmark, independently adjudicated ground truth, or a reserved final audit. Its authorship and possible scenario similarity to existing data must remain documented. An exact normalized-text check found no matches against source training tickets or the existing challenge, broader probes, or scope negatives. No source test data was opened; semantic/template overlap has not been certified absent.

## Start with five requests

Use Anaconda Prompt from the updated repository folder. This step happens in the terminal, not on the prediction webpage. No new packages or model download are needed; the review command uses the Python standard library.

If the server is running in that terminal, stop it with Ctrl+C. In this user's Windows installation Git works in the base environment:

```bat
conda deactivate
git pull --ff-only
conda activate support-ticket-ai
python -m support_ticket_ai.review_cases artifacts/review-ola-v1.json --reviewer ola --limit 5
```

If you are already in `(base)`, begin with `git pull --ff-only`. Keep the terminal in `C:\Users\User\support-ticket-ai`.

For each case:

1. Read the displayed request.
2. Enter `1`, `2`, `3`, or `4` for its intent type, using the rules below.
3. If it has one or multiple routing intents, enter category names. Separate multiple categories with commas. The tool displays the allowed vocabulary.
4. Add a short reason or disagreement note if useful. Press Enter to leave the note blank.

The tool does not grade your answer or display its own preferred answer. It validates category names and structural consistency only. Use `s` to skip a case you cannot confidently label. Use `q` at the intent-type prompt to quit; Ctrl+C also stops safely. Previously saved answers remain available. Five completed answers end the default session; skips do not count toward that limit.

Continue later with the same reviewer and collection:

```bat
python -m support_ticket_ai.review_cases artifacts/review-ola-v1.json --reviewer ola --limit 5 --resume
```

The tool checks the collection fingerprint and reviewer before resuming, skips completed cases, and refuses to overwrite an existing session without `--resume`. Changing the CSV requires a separately versioned session. Answers are saved after each completed case using an atomic file replacement. The progress file is under ignored `artifacts/` and is not automatically published or sent anywhere.

## Annotation rules

| Choice | Intent type | Use when | Category entries |
|---|---|---|---|
| 1 | One clear routing intent | There is enough information to choose one support category. Missing an order number alone does not make the intent unclear. | Exactly one |
| 2 | Multiple routing intents | The request contains distinct supported needs requiring different categories. | Two or more distinct categories |
| 3 | Insufficient context | The text does not establish a sufficiently clear supported need or route. Do not invent context from an earlier conversation. | None |
| 4 | Unsupported | The requested task falls outside this customer-support service, even if it mentions support vocabulary. | None |

Here, “multiple intents” means **multiple routing categories**. Two actions within the same category can still have one routing label. This is an annotation contract for this pilot, not a complete linguistic decomposition of user intent.

If a request combines a supported and unsupported task, or does not fit these four types cleanly, skip it and record the case ID separately for a contract discussion. Do not force a label to make the dataset look complete. The note field can record disagreements on completed cases; it does not replace an unresolved-case workflow.

### Source category contract

| Category | Intended request |
|---|---|
| ACCOUNT | Customer account access, creation, deletion, or profile changes |
| CANCEL | Cancellation-fee questions; an actual order cancellation is ORDER |
| CONTACT | Reaching customer service or an agent |
| DELIVERY | Delivery options and expected service times |
| FEEDBACK | Complaints, compliments, or service reviews |
| INVOICE | Retrieving or requesting billing documents |
| ORDER | Placing, changing, cancelling, or tracking a purchase |
| PAYMENT | Payment methods, failed transactions, or disputed charges |
| REFUND | Refund eligibility, requests, or progress |
| SHIPPING | Setting or correcting destination addresses |
| SUBSCRIPTION | Newsletter subscription preferences |

Use these definitions consistently; do not infer a different definition from the everyday category name. If a rule conflicts with intended product behavior, document that disagreement before changing the ontology or model.

## What the saved file means

The JSON records the collection hash, reviewer name or pseudonym, case and family IDs, chosen type, category list, optional note, and UTC timestamp. It records that this tool showed no model predictions. The file's status remains `human_annotation_pilot_not_adjudicated`, including after all 40 cases are filled in. The tool cannot verify who supplied an answer or certify reviewer independence.

To check consistency later, a second reviewer should create a different output file and label the same requests without seeing the first review. Compare disagreements by case ID and adjudicate them with reasons. Keep both original reviews unchanged. A single review, or agreement after seeing proposed answers, is not independent adjudication.

Author-assigned family IDs preserve pairs of related scenarios. They are not independently verified semantic clusters. Do not randomly split paraphrases into fitting and audit data. After this pilot clarifies the rules, obtain separately authored cases and reserve complete scenario families before fitting or selecting thresholds. Keep the final audit unscored until candidate choices are frozen.

## Practical learning

This step teaches **data annotation and task definition**: deciding what a system should predict before choosing a more powerful model. Completed labels can guide development of single-intent, multi-category, clarification, and unsupported-request handling. This milestone does not train those capabilities, establish their accuracy, or promote the semantic candidate to the live app.
