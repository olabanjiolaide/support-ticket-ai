# Experimental score-based abstention

The classifier can now withhold its category suggestion and display **No reliable suggestion** when an optional score rule is installed. This is a selective-prediction prototype, not a trained detector of unsupported requests. Passing the rule does not establish reliability. Every request still requires human review.

## Later overlap finding (October 20, 2026)

The semantic experiment's train-overlap check found that selection case `sel-subscription-1` ("How do I subscribe to your newsletter?") exactly matches a normalized training ticket. The original historical experiment below did not check challenge/train overlap. Its selection was therefore partly contaminated; it should not be treated as clean evidence for the cutoff. The audit had no normalized exact training match, but remains a small authored development set. The new semantic comparison excludes that selection case before scoring, leaving 21 supported and 12 unrelated selection requests. Historical reports and the optional live policy are preserved unchanged. Future independently reviewed collections must be screened for exact and template-family overlap before selection.

## What changed

The trained classifier and its original scores are unchanged. When the model's maximum uncalibrated probability is below the installed threshold, the prediction returns decision=abstain and suggested_category=null. The underlying model_top_category is retained in the JSON for diagnostics, but is not presented as the recommended category.

Without an abstention_policy.json file in the model directory, the existing suggestion behavior remains active. Invalid policies or policies for a different model fingerprint prevent the bundle from loading. The model checksum is still verified.

## Development challenge design

data/development_challenge.csv contains 60 project-authored cases. Labels are author-assigned and have not been independently adjudicated.

| Partition | Supported requests | Unrelated requests | Purpose |
| --- | ---: | ---: | --- |
| Selection | 22 | 12 | Choose a threshold |
| Audit | 11 | 12 | Check the frozen threshold without retuning |
| Regression | 2 | 1 | Revisit the user's three manual probes; excluded from selection and audit metrics |

All 11 model categories appear in both selection and audit. Unrelated cases include general requests and messages containing support-related vocabulary in a different context. Duplicate IDs and normalized duplicate texts are rejected.

These are small development probes, not a representative benchmark or an independently collected test set. Similarity and exact overlap with every source-training example have not been exhaustively audited. The reserved dataset test split is not accessed.

## Selection rule and results

The fixed candidate thresholds are 0.50, 0.60, 0.70, 0.80, 0.85, 0.90, 0.95, 0.98, and 0.99. Among candidates with at least 25% supported coverage, at least 90% accuracy on selected supported examples, and at least 90% rejection of unrelated examples in the selection partition, choose the highest supported coverage. Ties choose the lower threshold.

The selected threshold is **0.70**. Installation is offered only if the separate audit also meets those same empirical criteria. These small-sample criteria are not statistical guarantees.

Observed audit results:

| Measure | Forced-suggestion baseline | Score rule at 0.70 |
| --- | ---: | ---: |
| Supported requests receiving a suggestion | 11 / 11 | 3 / 11 |
| Correct among those suggestions | 11 / 11 | 3 / 3 |
| Unrelated requests receiving a suggestion | 12 / 12 | 0 / 12 |
| Correct supported suggestions withheld | 0 | 8 |

The rule removes forced suggestions for these 12 unrelated audit examples, but withholds eight correct supported predictions. That loss of coverage is substantial. It does not improve the underlying classifier's category accuracy.

It also fails on a selection example: “Write a short story about a dragon.” produces FEEDBACK with score 0.771 and passes the 0.70 rule. A high score is not proof of task relevance.

The three regression probes all trigger abstention, including the correctly classified invoice request. The account-access example with score about 0.840 still receives an ACCOUNT suggestion. Full per-case scores and both partition reports are in reports/bitext-baseline-v1/abstention_experiment.json.

## Enable it on an existing Windows installation

Stop the running server with Ctrl+C. Git was available in the user's base Conda environment, so update there:

```bat
conda deactivate
git pull --ff-only
conda activate support-ticket-ai
python -m support_ticket_ai.abstain artifacts/demo-v1/model artifacts/abstention-v1.json --install-policy
python -m support_ticket_ai.serve --model-dir artifacts/demo-v1/model
```

Run commands from the repository root. The first line assumes the project environment is active; if already in base, start with git pull. The experiment uses the local model's fingerprint, so a Windows model with different serialized bytes is handled correctly.

Open http://127.0.0.1:8000/ and refresh. Try the account-access, duplicate-charge, and poem requests. Expand View API response to inspect decision, model_top_category, and abstention_threshold.

No classifier retraining, dataset download, or new dependency is required. The command reuses the saved model and the bundled authored challenge CSV. The normal demo builder does not install the policy automatically.

Existing report filenames and existing policies are never overwritten. If evaluation fails the fixed audit criteria, the report remains available and no policy is installed. If a policy already exists, keep it and use a separately versioned bundle for a new experiment. To disable the rule, stop the server and move the policy file out of the active model directory before restarting; keep it for provenance.

## API version 0.2.0

Additional response fields:

| Field | Meaning |
| --- | --- |
| decision | suggestion or abstain |
| suggested_category | Recommended category, or null when withheld |
| model_top_category | Highest-scoring classifier category, even if withheld |
| abstention_threshold | Installed score cutoff, or null when no policy is installed |

The uncalibrated_probability field always refers to the maximum raw model score. The requires_human_review field remains true in both decisions. External clients must handle a nullable suggested_category when the optional policy is activated.

The browser renders an abstention as a completed response requiring manual classification, not as a connection error or as proof that the request is unsupported. Temperature scaling is not applied to the live score.

## Verification and next learning step

All 61 Python tests pass locally, including threshold boundaries, preservation of human review, nullable API output, model-bound policy validation, and prevention of policy overwrites. Browser checks cover real-model abstention and normal suggestions alongside the existing desktop/mobile interactions.

The next model-quality step is a larger, independently labelled challenge corpus and comparison with a dedicated scope-detection approach. This cutoff is a transparent baseline for studying coverage versus errors, not a production routing policy.

Learning point: abstaining can prevent an unsupported suggestion, but it can also withhold a correct answer. Report both outcomes.
