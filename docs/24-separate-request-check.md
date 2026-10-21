# Optional experimental separate-request check

Semantic mode now offers an unchecked **Check for separate requests · experimental** option. It can withhold a single-category suggestion when distinct affirmative request fragments receive accepted predictions in different categories. The default word mode and ordinary semantic predictions are unchanged.

This is a rule-based engineering baseline, not a trained general multi-intent or clarification model. No match does not establish a single clear intent. Every suggestion still requires human review.

## Try it in the browser

Update the checkout and restart the server using the environment that already runs semantic mode successfully. On the current Windows setup, stop the server with Ctrl+C, then:

```bat
conda deactivate
git pull --ff-only
conda activate support-ticket-ai
python -m support_ticket_ai.serve --model-dir artifacts/demo-v1/model --semantic-model-dir artifacts/semantic-v1
```

If your working semantic environment has another name, activate that environment instead. No dependency install or model rebuild is needed for this option. Installed-wheel users should rebuild/reinstall the package from the updated checkout; source users can run the command directly.

Open http://127.0.0.1:8000/, refresh the page, choose **Semantic · experimental**, and tick **Check for separate requests · experimental**.

Try `Change my account email and refund my last purchase.`. Without the check, the current semantic model offers a single category. With the check, the interface withholds the category and explains that separate requests need review.

Also try `Change my account name and reset my password.`. Both actions concern ACCOUNT, so this cross-category check does not withhold the message merely because it contains two actions. Background context such as `My purchase arrived broken and I want a refund.` does not supply a second explicit request under these rules.

Changing the checkbox clears any previous displayed result. Switching models resets it to unchecked; it is hidden in word mode. Controls are disabled during prediction. The browser verifies that the response matches the requested model and option before displaying it.

## What the check does

1. Obtain the existing whole-message prediction. If it already abstains, preserve that decision without additional clause inference.
2. Split a bounded message at supported conjunctions and sentence/semicolon/newline boundaries. Recognize affirmative English request openings and a fixed imperative-action list. More than four segments and conditional/alternative wording are skipped, not resolved.
3. Require at least two explicit request fragments. Skip negated fragments. Score each candidate with the same loaded semantic predictor, including its category/scope cutoffs and truncation rule. At most four additional model calls occur.
4. Withhold only if at least two accepted fragments have different routing categories. Same-category actions do not trigger it. CONTACT alongside a specific task is conservatively treated as a possible human-agent preference rather than automatically another routing need.

The original top category, uncalibrated score, and model fingerprint remain available. The extra decision concerns whether to show one category; it does not make that score a calibrated probability. A model scoring error on an isolated fragment can still produce a mistaken guard decision.

The CONTACT exception can miss an independent request for contact information. Indirect problems, questions without recognized request openings, quotation scope, complicated negation, contextual references, and other languages are not generally handled. Requests can be ambiguous for reasons beyond multiple categories. The rules are intentionally narrow and must not be described as full sentence understanding.

## API contract

Package 0.5.0 / API 0.4.0 accepts:

```json
{
  "text": "Change my account email and refund my last purchase.",
  "mode": "semantic",
  "check_multiple_requests": true
}
```

The option defaults to false and requires an actual JSON Boolean. Enabling it with word mode returns 422. Unavailable semantic mode returns 503; there is no fallback to a different model.

Responses add `multiple_request_check_enabled`, `multiple_requests_detected`, nullable `request_check_status`, and nullable `request_check_version`. Version 1 describes this fixed rule configuration. A request with the option off gets false flags and null check status/version. An already-withheld message with the option on has `outer_prediction_already_withheld` status; this does not count as a newly detected multi-intent case. The HTTP response does not expose fragment text. The offline diagnostic report includes public development fragments for inspection.

## Offline development evidence

The [recorded comparison](../reports/bitext-baseline-v1/multi_intent_pilot.json) uses the existing 98 authored development probes and the same frozen semantic bundle. It verifies matching training checksums and excludes exact normalized training overlaps. It opens neither validation/test CSVs nor private/pending review collections, fits no model, and selects no threshold.

| Development measure | Existing semantic policy | Optional check enabled |
|---|---:|---:|
| Supported requests receiving a suggestion | 52/66 | 52/66 |
| Correct accepted supported suggestions | 49/52 | 49/52 |
| Unrelated requests withheld | 24/24 | 24/24 |
| Ambiguous requests withheld | 3/8 | 5/8 |

The two newly withheld cases are `Change my account email and refund my last purchase.` and `Stop the newsletter and update the shipping address.`. Four additional clause-model calls are made across all 98 requests. This small known set shows no extra withholding of supported cases; it does not establish a real-world false-positive rate.

The check still misses `I cannot log in and my checkout payment was rejected.` because it states two problems rather than two recognized affirmative requests. It also leaves two vague requests accepted. The existing invoice-plus-cancellation probe was already withheld by the base policy; do not count that as a guard improvement.

These cases have provisional labels and have been inspected before. They are development diagnostics, not independent test evidence or a production guarantee. The optional control makes this limitation visible instead of replacing the current model policy by default. Manual labeling remains paused.

Reproduce the report with a fresh output path:

```bat
python -m support_ticket_ai.multi_intent_experiment artifacts/semantic-v1 artifacts/demo-v1/prepared artifacts/multi-intent-pilot-v1.json
```

The **Build semantic browser demo** Actions workflow also generates the report and checks real desktop/mobile browser flows, including enabling/disabling the option, unchanged same-category requests, original-score preservation, model switching, and input truncation. It does not host the application.
