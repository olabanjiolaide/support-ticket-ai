# Milestone 2 implementation: import and split

## Implemented

`support_ticket_ai.prepare` reads a local Bitext-format CSV, collapses duplicates using Unicode normalization, case folding, and whitespace normalization, and excludes requests assigned conflicting labels. The source's category names are preserved. All source rows are validated; invalid records stop the import.

It makes deterministic train/validation/test splits by category, targeting 70/15/15 percent. At least one example per class goes into each split. Small classes can differ substantially from the target percentages; fewer than three unique nonconflicting requests causes an error. The manifest reports actual counts.

## Running later on a computer

Obtain the CSV and publisher license from the pinned dataset revision identified in the dataset plan. Record the download date in your experiment notes. Replace the placeholders below with the real source paths and full upstream commit SHA.

```bash
python -m support_ticket_ai.prepare path/to/source.csv artifacts/bitext-v1 --source-revision FULL_40_CHARACTER_COMMIT_SHA --license-file path/to/LICENSE.txt
python -m unittest discover -s tests -v
```

The command rejects an existing output directory, preserving prior experiment versions. The manifest records source and split checksums, category counts, duplicate removal, conflicts, source revision, and license checksum. The publisher license is copied alongside the output. The supplied revision is recorded, not verified against the network; obtain the file from that exact revision yourself.

Generated data stays under the ignored `artifacts/` directory. Tests use tiny synthetic fixtures. A subsequent [baseline run](04-baseline-results.md) imported the pinned external source and evaluated validation performance.

## Loading the imported categories

The original demo loader still defaults to billing/account/technical. For imported data, read the manifest's category vocabulary explicitly:

```python
import json
from pathlib import Path
from support_ticket_ai.data import load_tickets

root = Path("artifacts/bitext-v1")
manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
categories = frozenset(manifest["audit"]["categories"])
train = load_tickets(root / "train.csv", categories=categories)
```

The existing summary CLI is for the original demo vocabulary. The preparation CLI prints the imported dataset's category counts.

## Learn from your phone

Open `tests/test_prepare.py` and find `test_deduplication_conflicts_and_split_isolation`. It checks that the same normalized text never appears in multiple splits. The source-order test checks that shuffling CSV rows does not change assignments.

**Practice answer:** “I deduplicate requests before splitting so repeated examples cannot inflate held-out performance.”

This only handles normalized exact duplicates. Similar templates and paraphrases may still cross splits. Evaluation must disclose that limitation and inspect template overlap before drawing conclusions about generalization.

Next: obtain a pinned dataset, audit the prepared outputs, then train and evaluate the baseline.
