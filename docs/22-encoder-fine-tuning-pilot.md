# Train-only semantic encoder fine-tuning pilot

The browser uses a frozen MiniLM sentence encoder plus logistic category and scope heads. This offline experiment asks whether updating the encoder on the existing support categories helps. It does not replace either browser model, export a serving bundle, or require more manual labeling.

## What learns, and from which data

1. Verify the prepared train/validation checksums, category coverage, and disjoint ticket IDs and normalized text. Check that the authored scope negatives and development probes do not exactly overlap either split or each other. Near-template and semantic overlap are not ruled out.
2. Load `sentence-transformers/all-MiniLM-L6-v2` at revision `1110a243fdf4706b3f48f1d95db1a4f5529b4d41` on CPU. Compute the frozen representation comparison first.
3. Select at most 128 training tickets per category by a stable seeded hash. On the pinned dataset this is 1,408 requests across 11 categories. Update all encoder parameters for one epoch using a temporary linear category head and cross-entropy. The differentiable encoder forward pass is used: `encode()` is an inference API and must not be used for training gradients.
4. Discard that temporary head. Fit fresh category and scope logistic regressions on each representation using identical recipes and the same full 16,990 supported training rows plus the same 48 authored scope negatives. The category head never fits the negatives. Fine-tuning never fits the negatives, validation, probes, review labels, or test data.
5. Compare both representations on the same synthetic validation partition and existing 98 authored development probes. Record category macro-F1, confusion matrices, per-class metrics, accepted-suggestion accuracy, coverage, unsupported false suggestions, ambiguous requests withheld, and cases whose category or acceptance changed.

Both comparisons use fixed category and scope cutoffs of 0.5. No threshold sweep, calibration, early stopping, or checkpoint selection occurs. A change in coverage alone does not establish a better classifier. The same numeric cutoff need not mean the same risk for two representations.

## Fixed recipe

| Setting | Value |
|---|---|
| Seed | 42 |
| Training subset | Up to 128 tickets per class from train only |
| Epochs / batch size | 1 / 16 |
| Encoder / temporary-head learning rate | 0.00002 / 0.001 |
| Optimizer / weight decay | AdamW / 0.01 |
| Gradient norm cap | 1.0 |
| Temporary classifier logits | Linear head on normalized sentence embeddings, scaled by 20 |
| Category and scope heads after adaptation | Logistic regression, C=1, max_iter=1000; balanced class weights for scope only |
| Input length | 256 wordpieces |
| Compute | CPU, two Torch threads |

The report hashes encoder parameters before and after adaptation and fails if the encoder did not change. It records the selected training IDs, input hashes, package versions, training loss, and number of optimizer steps. Training loss is diagnostic rather than evidence of predictive improvement. One seed does not establish run-to-run stability.

## Reproduce locally

Use the existing environment that runs semantic mode successfully. From the repository root, with `requirements-semantic.txt` already installed:

```bat
python -m support_ticket_ai.finetune_experiment artifacts/demo-v1/prepared artifacts/finetune-pilot-v1.json
```

The first encoder load may download the pinned weights. If they are already cached and you need to run without Hub access, set `HF_HUB_OFFLINE=1` for this command. On Windows Command Prompt, use `set HF_HUB_OFFLINE=1`, run the command, then `set HF_HUB_OFFLINE=` to remove that setting. This assumes the complete pinned checkpoint is in `artifacts/encoder-cache`.

Use a new output filename for every run. Existing reports are preserved. No GPU, additional labeling, or new training dependency is required beyond the semantic environment. The CLI prints a compact comparison and saves detailed JSON. `test.csv` is never opened, hashed, or evaluated.

The manually triggered **Run offline encoder fine-tuning pilot** GitHub Actions workflow runs the tests, rebuilds the pinned demo data, runs the comparison, and uploads the report. It does not host the app or deploy any candidate. Downloadable reports expire after seven days; checked-in reports remain in the repository.

## Interpretation

These probes were already inspected and their labels are provisional. They are development diagnostics, not independent evidence of deployment accuracy. The validation source is synthetic and can share templates with training. No model-selection claim should be based on its near-perfect validation F1 alone.

The experiment trains category distinctions; it does not train multiple-intent detection. All browser predictions still require human review. The offline pilot truncates encoder inputs at 256 wordpieces and does not reproduce the browser's extra truncation-abstention guard, so its acceptance diagnostics are not a full serving-policy benchmark.

Any later candidate promotion needs separate evaluation of correctness, coverage, ambiguity, unsupported requests, and runtime behavior. The pending review collection remains paused.

## Recorded pilot result

The [machine-readable report](../reports/bitext-baseline-v1/finetune_pilot.json) records a real CPU run, not a test double. All 22,713,216 encoder parameters were enabled for training; 88 optimizer steps updated the encoder state fingerprint. The temporary classifier was discarded before fitting the comparison heads.

| Measure | Frozen encoder | Fine-tuned encoder |
|---|---:|---:|
| Synthetic validation macro-F1 | 0.99634 | 0.99752 |
| Correct top category on 66 supported development requests, before abstention | 56/66 | 54/66 |
| Supported development macro-F1, before abstention | 0.85193 | 0.82175 |
| Supported requests receiving a suggestion with scope gate | 52/66 | 53/66 |
| Correct accepted supported suggestions | 49/52 | 50/53 |
| Incorrect accepted supported suggestions | 3 | 3 |
| Unrelated development requests withheld | 24/24 | 24/24 |
| Ambiguous development requests withheld | 3/8 | 3/8 |

Decision: retain the frozen encoder in the browser. This pilot is not an overall improvement. Fine-tuning increases coverage slightly, but worsens overall category accuracy on these known development cases. The unchanged total of ambiguous requests withheld also hides a regression: the fine-tuned model starts accepting `I want my invoice and I also want to cancel my order.`, while it starts withholding the unclear `It does not work.`. Those outcomes should not be treated as interchangeable successes.

Two typo-heavy requests change from a correct but withheld top category to an incorrect withheld top category: `need to speek to a suport agnet` and `wanna cancle my ordar before it ships`. These are leads for a separately designed robustness experiment, not permission to tune repeatedly against these same examples and call the resulting score independent evidence.

Practical lesson: encoder adaptation can improve fit to synthetic training patterns while weakening useful general-purpose representations. A larger validation number alone is insufficient grounds to deploy a new model. This run supports investigating spelling robustness and explicit ambiguity handling before another encoder change.
