# A short recruiter walkthrough

## Opening: the practical problem

“Support Ticket AI is a Python application that suggests categories for customer-support requests and keeps a human in the decision loop. I built the data preparation, baseline training, prediction API, responsive interface, and reproducible experiment tooling.”

## Demonstrate the application

Start the local server with your existing model bundle:

```bat
support-ticket-serve --model-dir artifacts/demo-v1/model
```

If you have not installed the new package yet, the existing command still works:

```bat
python -m support_ticket_ai.serve --model-dir artifacts/demo-v1/model
```

Open http://127.0.0.1:8000/ and show the model-ready indicator. Enter a clear account-access request and submit it. Describe the suggested category, the explicitly uncalibrated score, and the human-review requirement. Explain that editing the request clears the old result.

If the existing optional abstention policy is installed, try an unrelated request and explain the withheld-suggestion outcome. A score rule can still accept unrelated requests; do not promise that a chosen example will always be rejected. Without an installed policy, explain that the default classifier is forced to choose among supported labels.

## Explain the engineering evidence

Show the GitHub Actions checks and [installation guide](19-installable-package.md). The package is tested outside its source checkout, and browser checks exercise form submission, error recovery, and mobile layout against a real API with a generated model fixture. These are software checks, separate from ML-quality evaluation.

Explain that model bundles are checksum-checked and version-checked, input validation is explicit, and readiness is distinct from liveness. Model files remain trusted local inputs; a checksum checks consistency rather than author authenticity.

## Explain the ML findings honestly

“The source validation score was very high, but the source is synthetic and contains related templates. I therefore investigated overlap, manually written failures, coverage, unsupported requests, and indirect wording. Frozen sentence embeddings improved indirect wording on an authored development set. However, a semantic model still accepted ambiguous requests and made routing errors, so I kept it experimental, with human review required. It can now be enabled explicitly in the local browser demo while the word baseline remains the default.”

Use [the semantic experiment](15-semantic-embedding-experiment.md) and [the reconciled pilot report](17-reviewed-pilot-evaluation.md) for exact counts and limitations. Identify authored, provisional, guided, and reconciled labels accurately. Do not describe these development collections as an independent benchmark, real-customer accuracy, or a production deployment. The final source test remains untouched.

## Close with your contribution

“The main learning was that classification accuracy alone is insufficient: a useful service must balance coverage, incorrect routing, unsupported tasks, and requests needing clarification. I kept experiments reproducible and separated them from changes to the running application.”

The current public demonstration is the local application and its repository evidence. There is no hosted live service yet. This project is separate from private MuFedSL; the walkthrough requires no private research code or unpublished research claims.

## Keep the milestone bounded

Manual labeling is paused. The pending ambiguity collection can remain pending. This release focuses on an installable application, automated interaction checks, and a clear demonstration. Further NLP experiments are optional future work, not a prerequisite for presenting the engineering already completed.
