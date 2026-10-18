# First baseline: validation results

Run date: 2026-10-18. Evaluation: validation only. No hyperparameter search was performed. The test set has not been evaluated.

## Data audit

Source: Bitext customer-support dataset, GitHub revision `72ea2203180d14a416b579c657033ecd21e59a11`, file `data/Bitext_Sample_Customer_Support_Training_Dataset_27K_responses-v11.csv`.

Downloaded on 2026-10-18. The local source was renamed `bitext.csv`. The publisher's LICENSE.txt identifies CDLA-Sharing-1.0; its exact copy accompanies the report. Dataset terms are separate from project code terms.

| Check | Result |
| --- | ---: |
| Source rows | 26,872 |
| Normalized duplicate rows removed | 2,598 |
| Conflicting-label groups | 0 |
| Retained unique requests | 24,274 |
| Categories | 11 |
| Train requests | 16,990 |
| Validation requests | 3,642 |
| Reserved test requests | 3,642 |

The observed categories are ACCOUNT, CANCEL, CONTACT, DELIVERY, FEEDBACK, INVOICE, ORDER, PAYMENT, REFUND, SHIPPING, and SUBSCRIPTION. These are the actual file values, which differ from some labels in the publisher's documentation.

## Validation comparison

| Model | Macro-F1 | Accuracy |
| --- | ---: | ---: |
| Majority-class predictor | 0.0329 | 0.2208 |
| TF-IDF + logistic regression | 0.9984 | 0.9978 |

TF-IDF uses word unigrams and bigrams, up to 50,000 features, and sublinear term frequency. Logistic regression uses C=1.0, no class weighting, and a maximum of 1,000 iterations. Feature fitting and model fitting use training data only. The manifest seed is 42. See the JSON report for exact values, dependency versions, class metrics, confusion matrix, and checksums.

## Interpretation and limitations

This is a functioning engineering baseline on a synthetic dataset. The high score does not demonstrate production support-ticket accuracy. Exact deduplication cannot eliminate related templates or paraphrases across partitions. This run has not measured template-family separation, out-of-distribution performance, calibration, or multiple-seed uncertainty.

Do not put “99.8% real-world accuracy” on a CV or project page. A defensible description is: “Built a reproducible text-classification pipeline with duplicate-aware splits, validation reporting, and automated leakage checks.”

## Reproduce

Use Python 3.11–3.13 and install `requirements.txt`. Obtain the source CSV and publisher license from the exact pinned GitHub revision above; place them at `artifacts/source/bitext.csv` and `artifacts/source/LICENSE.txt`.

```bash
python -m pip install -r requirements.txt
python -m support_ticket_ai.prepare artifacts/source/bitext.csv artifacts/bitext-v2 --source-revision 72ea2203180d14a416b579c657033ecd21e59a11 --license-file artifacts/source/LICENSE.txt
python -m support_ticket_ai.train artifacts/bitext-v2 artifacts/baseline-v1
python -m unittest discover -s tests -v
```

Choose fresh output paths when repeating runs. Never load joblib files from untrusted sources. Raw data and the model file are ignored artifacts; committed reports contain aggregate results and provenance, not request text.

## Learn from your phone

Open `support_ticket_ai/train.py` and find `model.fit(texts, targets)`. Those are training examples. `model.predict(val_texts)` evaluates separate validation examples without refitting the vectorizer.

Macro-F1 gives each category equal weight when averaging its F1 score. This makes weaker small categories easier to notice than accuracy alone.

Next: inspect template overlap, add a prediction interface, and handle unsupported requests before considering a final held-out evaluation.
