# Broader development diagnostics

## What this milestone adds

The first abstention audit had one supported request per category. This milestone adds 98 different, assistant-authored stress probes: 66 supported requests (six per category), 24 unrelated tasks, and eight underspecified or multi-intent requests. Every label is **provisional**. These are diagnostic examples, not an independent benchmark, representative customer traffic, or a replacement for the final held-out test.

The existing classifier and the 0.70 cutoff were frozen before scoring these probes. There is no threshold search, retraining, policy installation, or live behavior change. `--threshold` evaluates a supplied cutoff only; repeatedly trying cutoffs turns these examples into tuning data, not independent evidence.

## Reproduce locally

From the repository root, using a previously built demo bundle:

```bat
python -m support_ticket_ai.robustness artifacts/demo-v1/model artifacts/demo-v1/prepared artifacts/robustness-v1.json
```

Choose a fresh output filename when repeating an experiment. Use the prepared directory that belongs to the model: the evaluator checks the preparation manifest fingerprint and training CSV checksum. It reads only `manifest.json` and `train.csv` from that directory. Validation and test CSVs are not opened. It rejects probes that exactly duplicate normalized training requests; near-template similarity is not checked.

The evaluator compares forced suggestions against the explicit diagnostic cutoff. It records the installed policy cutoff separately, so evaluating 0.70 is unambiguous even when a model directory has no installed policy. It does not change that policy.

Results: [versioned JSON report](../reports/bitext-baseline-v1/robustness_diagnostics.json).

## Observed results against provisional labels

| Measurement | Forced suggestions | Frozen cutoff 0.70 |
|---|---:|---:|
| Supported requests receiving a category | 66/66 | 14/66 (21.2%) |
| Correct among selected supported requests | 34/66 | 14/14 |
| Valid supported requests withheld | 0/66 | 52/66 |
| Unrelated requests withheld | 0/24 | 20/24 |
| Unrelated requests receiving a category | 24/24 | 4/24 |
| Ambiguous requests withheld | 0/8 | 6/8 |

All 98 labels remain provisional; the reviewed-only report contains zero rows. No normalized exact training duplicates were found. These are descriptive counts on a small, intentionally difficult collection. Repeated intents are correlated, so the row counts cannot be treated as independent samples or production accuracy estimates.

Coverage differs sharply by writing style:

| Supported slice | Suggestions passing 0.70 |
|---|---:|
| Plain wording | 11/22 |
| Typos and informal spelling | 1/22 |
| Indirect wording | 2/22 |

All four unrelated tasks that passed contain familiar support keywords. Examples include “Translate the phrase shipping address into Italian.” (SHIPPING, raw score approximately 1.000) and “Invent dialogue for a fictional customer support agent.” (CONTACT, 0.993). A high raw score is not evidence that a request belongs within the application's scope.

The eight REVIEW cases have no unique target category under the current single-label contract. Their withholding rate is reported separately; they are excluded from supported-category accuracy and unsupported-request rejection. Human review is required for every live request, including any ambiguous case that passes the cutoff.

## Review the labels before selecting a replacement

1. Preserve the shipped CSV and report as version 1. Use a separate copy for review.
2. Ask a reviewer to label the text without seeing model predictions or provisional labels. Record case ID, chosen category, reviewer identity or pseudonym, date, and rationale in a separate review log. Using a second reviewer allows disagreements to be adjudicated. Do not treat agreement by the original author alone as independent review.
3. Apply the category contract below. Mark genuinely unclear or conflicting intents REVIEW; do not force a single target solely to improve a score.
4. Record label changes and unresolved disagreements. Copy adjudicated labels into the new probe CSV and mark only completed rows `reviewed`. `--probes PATH` evaluates that version. The flag records workflow state; code cannot certify reviewer independence.
5. Freeze a distinct, independently authored audit set before comparing candidate models. Existing scored probes remain development data. Keep template families and paraphrases together when splitting future collections.

### Category contract

The source category names are narrower than their everyday meanings. This project preserves the source ontology rather than relabeling examples to suit the classifier.

| Category | Intended request |
|---|---|
| ACCOUNT | Customer account access, creation, deletion, or profile changes |
| CANCEL | Questions about cancellation fees; an actual cancellation request is ORDER |
| CONTACT | Reaching customer service or an agent |
| DELIVERY | Delivery options and expected service times |
| FEEDBACK | Customer complaints and service reviews |
| INVOICE | Retrieving or requesting billing documents |
| ORDER | Placing, changing, cancelling, or tracking an existing purchase |
| PAYMENT | Payment methods, payment failure, or a disputed charge |
| REFUND | Refund eligibility, requests, or progress |
| SHIPPING | Setting or correcting destination addresses |
| SUBSCRIPTION | Newsletter subscription or unsubscription |
| UNSUPPORTED | A task outside customer support, including tasks that merely mention support vocabulary |
| REVIEW | Insufficient context or multiple unresolved routing intents |

These are proposed annotation rules for review, not evidence that every source label is consistent. If the desired product uses a different contract, version the ontology and relabel/retrain deliberately.

## What to learn and build next

**Coverage** measures how often a supported request receives a suggestion. **Selected accuracy** measures correctness only among those accepted requests. Always inspect both, along with unsupported false suggestions: abstaining on almost everything can make selected accuracy look impressive while providing little help.

Next experiments should test character n-gram features for spelling variation and a separate scope decision for unrelated tasks. Develop them using reviewed development data and compare frozen candidates on a fresh audit set. Character features alone will not necessarily fix a high-confidence keyword trap. Do not lower the cutoff simply to raise coverage, or encode special rules for the four exposed failures.

The final held-out source test remains untouched. Once the model and policy are frozen, it can measure in-source performance; it still cannot establish out-of-scope detection or real-world generalization.
