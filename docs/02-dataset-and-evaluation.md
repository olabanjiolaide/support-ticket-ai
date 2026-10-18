# Milestone 2: dataset selection and evaluation design

Decision recorded: 2026-10-18. Status: source reviewed; download, data audit, importer, and training are still pending.

## Selected source

Use Bitext's Customer Support LLM Chatbot Training Dataset as the first candidate for an educational routing model.

- Publisher repository: https://github.com/bitext/customer-support-llm-chatbot-training-dataset
- Dataset card: https://huggingface.co/datasets/bitext/Bitext-customer-support-llm-chatbot-training-dataset
- License metadata: CDLA-Sharing-1.0. Preserve the publisher's license and attribution with any distributed data or transformed dataset. This project's code licensing must be treated separately.
- Origin: hybrid synthetic customer-service requests, not a collection of production support tickets.
- The card describes roughly 27,000 examples and 27 intents. The documentation's category count is inconsistent with its displayed category listing; actual counts must be computed from a pinned download.

No external dataset has been copied into this repository yet. Record the exact source revision, filename, SHA-256, download date, and license text before running experiments.

## Scope adjustment before implementation

The first milestone's billing/account/technical labels are demonstration labels. Bitext's categories include ACCOUNT, INVOICE, PAYMENT, REFUND, ORDER, and others; it does not provide a matching general technical category.

Use the source categories for the first trained model, after inspecting their actual values. Do not relabel unrelated requests as technical or claim the resulting model handles software troubleshooting. Extend the loader to accept an explicit category vocabulary while keeping the existing demo behavior and tests.

## Field mapping

| Source field | Use |
| --- | --- |
| instruction | Prediction input text |
| category | Classification target |
| intent | Audit metadata only |
| response | Exclude from model features |
| flags | Audit metadata only |

Generate stable record identifiers during import. Do not include IDs, source labels, responses, intents, or generation flags as predictive features.

## Evaluation protocol to implement

1. Audit missing values, label frequencies, exact duplicates, and conflicting labels.
2. Normalize text with a documented conservative rule for duplicate grouping. Keep matching normalized requests in one split; quarantine conflicting-label groups.
3. Create reproducible, approximately stratified train/validation/test partitions targeting 70/15/15 percent. Save record assignments, seed, source revision, and checksum. Reject partitions missing a category.
4. Fit text features and model parameters on training data only. Use validation data for hyperparameters and later review thresholds.
5. Compare a majority-class predictor with TF-IDF plus logistic regression. Report macro-F1, per-class precision/recall/F1, class counts, and confusion matrix.
6. Freeze the chosen pipeline before opening held-out test results. Record any later experiment as a new evaluation version.
7. Inspect template and near-duplicate overlap. Exact duplicate grouping alone cannot establish independence for synthetic paraphrases.

Held-out performance on this source measures performance on this synthetic distribution. It does not establish production reliability.

## Phone learning exercise

Why is response excluded from the input? It is an answer written for the request and would not be available when a new ticket arrives. Feeding it to the model would evaluate an easier task than the deployed system actually faces.

Explain the split roles in one sentence: training fits the model, validation guides development, and test estimates performance after the choices are frozen.

## Next implementation checkpoint

Build and test the importer and duplicate-aware split preparation before training. Commit the manifest and audit report, not an unlicensed or undocumented data copy.
