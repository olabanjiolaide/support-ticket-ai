# Frozen sentence-embedding experiment

## Why this experiment exists

Word features miss unfamiliar wording; character features helped typos but did little for indirect requests. This experiment asks whether a pretrained sentence encoder improves the representation before a small classifier learns the ticket labels. It also tests a separate binary scope head using the same frozen embeddings. Neither head turns semantic similarity into guaranteed task understanding.

## Fixed design

- Encoder: `sentence-transformers/all-MiniLM-L6-v2`, pinned revision `1110a243fdf4706b3f48f1d95db1a4f5529b4d41`, CPU with two Torch threads, 384-dimensional unit-normalized embeddings, batch size 64, maximum 256 wordpieces. Encoder is in evaluation mode with all parameters frozen.
- Category head: logistic regression, C=1, maximum 1,000 iterations, no class weighting, source seed 42; fitted on the same 16,990 source training tickets as the word model.
- Scope head: logistic regression with balanced class weights, fitted on the source training tickets plus the existing 48 provisional authored unrelated tasks. Scope threshold fixed at 0.50.
- No supervised fitting uses source validation, challenge selection, audit, regression, or broader probe rows. The encoder does encode these rows for evaluation; encoding is not fine-tuning.
- Each category-only policy chooses its own cutoff from the existing fixed grid using only the cleaned challenge selection partition. The semantic-with-scope policy selects its category cutoff with its fixed scope gate applied.
- Existing selection criteria remain unchanged: supported coverage at least 0.25, selected supported accuracy at least 0.90, unsupported rejection at least 0.90. Choose maximum supported coverage; break ties with the lowest eligible cutoff. If no cutoff qualifies, report no selected policy.
- Previously inspected challenge audit and broader probes are evaluated after cutoff selection. They are development diagnostics and do not become independent evidence merely because the code excludes them from selection.
- The source held-out test is never opened. No candidate weights or policies are exported or installed.

Encoder reference: [official model card](https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2). The model card describes the sentence representation and 256-wordpiece truncation. This implementation uses the standard Sentence Transformers pooling and normalization, with safe tensor weights and remote code disabled.

## Training overlap discovered during this milestone

One old selection case, `sel-subscription-1` ("How do I subscribe to your newsletter?"), exactly matches a normalized source training request. This experiment excludes it **before scoring**, leaving 21 supported and 12 unrelated selection cases. The historical cutoff experiment and report are preserved, with an added disclosure in [the abstention guide](11-experimental-abstention.md). Its cutoff-selection evidence was partly contaminated.

The old audit has no normalized exact training match. The 98 broader probes and 48 authored negatives also have no normalized exact support-training match; negative/probe/challenge exact overlap is rejected. Semantic and template-family overlap remain possible.

## Observed development results

All 98 broader probe labels are provisional. Correctness counts below are agreement with those labels, not independently verified accuracy.

| Category model | Synthetic validation macro-F1 | Correct supported probes before abstention | Median warm category inference |
|---|---:|---:|---:|
| word | 0.99839 | 34/66 | 0.69 ms |
| semantic | 0.99634 | 56/66 | 13.01 ms |

Timing uses one warm sequential pass over 20 texts, batch size one, on this execution environment. Semantic timing includes encoding plus the category head; word timing includes TF-IDF plus its classifier. It excludes download, model loading, HTTP, the scope head, concurrency, and repeated-trial analysis. Do not treat it as a production latency benchmark.

### Policies selected on cleaned selection data

| Model and policy | Selected category cutoff | Valid broader probes accepted | Correct among accepted valid probes | Unrelated broader probes accepted | Ambiguous broader probes withheld |
|---|---:|---:|---:|---:|---:|
| word: category_only | 0.70 | 14/66 | 14/14 | 4/24 | 6/8 |
| semantic: category_only | 0.90 | 25/66 | 24/25 | 3/24 | 8/8 |
| semantic: with_scope | 0.50 | 52/66 | 49/52 | 0/24 | 3/8 |

The fixed-0.70 comparison is also retained in the JSON as a diagnostic, but raw scores across different models are not calibrated or matched-risk operating points. Per-slice results, old audit counts, all candidate cutoffs, and individual scores remain in the [full report](../reports/bitext-baseline-v1/semantic_experiment.json).

### Supported probes by writing style, before abstention

| Slice | Word correct / total | Semantic correct / total |
|---|---:|---:|
| plain | 18/22 | 22/22 |
| typo | 6/22 | 16/22 |
| indirect | 10/22 | 18/22 |

## What improved, and what did not

Semantic representations improve indirect wording from 10/22 to 18/22 correct and typo requests from 6/22 to 16/22 before abstention on this collection. At their separately selected operating points, the combined semantic policy raises supported coverage from 14/66 (21.2%) to 52/66 (78.8%). It makes three accepted routing errors (49/52 correct, 94.2%), whereas the much narrower word policy makes none among its 14 accepted supported requests. This is a coverage/error tradeoff, not an across-the-board reliability improvement.

The combined semantic policy rejects all 24 unrelated probes, but accepts five of eight ambiguous requests. A successful scope gate does not resolve missing context or multiple supported intents. These findings support continued evaluation, not automatic routing or replacing the live model. The source validation macro-F1 also decreases slightly; the improvement on these wording probes does not mean every evaluation improves.

## Limits and interpretation

These are exploratory results on a previously inspected collection. The scope negatives were authored after known failure families were exposed. All labels remain provisional, and the three label rules discussed with the user were shown before agreement, rather than independently blind-reviewed. A small selection set and repeated development experiments can overfit even when code prevents direct row leakage.

The synthetic source validation has known template overlap. Pretraining overlap with downstream data has not been independently audited. The encoder truncates beyond 256 wordpieces; truncation counts are not measured in this experiment. The current English model is not validated for French, mixed-language input, or long requests. Balanced scope training does not calibrate its scores to real traffic prevalence.

REVIEW cases have insufficient context or multiple intents, and are excluded from category accuracy and unsupported rejection. A scope classifier does not resolve multiple supported intents. Every live request still requires human review. This report makes no production reliability or statistical significance claim.

## Reproduce without changing the application

The ordinary app and standard test workflow retain the lightweight core requirements. Semantic dependencies are optional. On a Windows computer, use a separate Python 3.12 environment to keep this experiment isolated from the working demo:

```bat
conda create -n support-ticket-semantic python=3.12 -y
conda activate support-ticket-semantic
python -m pip install torch==2.8.0 --index-url https://download.pytorch.org/whl/cpu
python -m pip install -r requirements-semantic.txt
python -m support_ticket_ai.semantic_experiment artifacts/demo-v1/model artifacts/demo-v1/prepared artifacts/semantic-v1.json
```

Run from the updated repository root. Use a fresh report filename for repeats. CPU Torch and encoder weights require an initial download; cached weights are reused. The optional package pins match the tested experiment; the report records installed versions. Version compatibility with your existing trusted model is checked before loading it.

From a phone, the **Run offline semantic experiment** workflow in GitHub Actions can build the pinned demo and run the real encoder on demand. Download its JSON artifact after completion. It uploads reports, provenance, and the source license, rather than the encoder or classifier weights. It does not deploy a service. The regular Python checks use a deterministic fake encoder for unit tests and need no semantic packages or downloads; the real experiment was also run locally.

## What to learn and decide next

An embedding changes how text is represented; a classifier still learns the application labels. Inspect whether meaningfully different wording improves, whether scope rejects tasks about support rather than actual support requests, and how much coverage costs in errors and CPU time.

Do not tune against the exposed audit or immediately promote a winner. The next evidence needed is a separately reviewed, family-disjoint audit whose texts are not authored to match these known examples. Freeze candidate and threshold selection first; keep that audit out of fitting and selection. Preserve the final source test for the eventual frozen model, while recognizing that in-source test performance alone cannot establish scope handling.
