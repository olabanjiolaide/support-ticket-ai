"""Import a locally downloaded Bitext CSV and freeze duplicate-aware splits."""

import argparse
from collections import Counter, defaultdict
import csv
import hashlib
import io
import json
from pathlib import Path
import re
import shutil
import sys
import tempfile
import unicodedata

SOURCE_URL = "https://github.com/bitext/customer-support-llm-chatbot-training-dataset"
FIELDS = ["ticket_id", "text", "category"]


def normalize(text: str) -> str:
    """Group case/Unicode/whitespace variants; retain punctuation differences."""
    return " ".join(unicodedata.normalize("NFKC", text).casefold().split())


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def build_splits(raw: bytes, seed: int = 42) -> tuple[dict, dict]:
    """Deduplicate requests, quarantine label conflicts, and split each class.

    Groups with conflicting labels are omitted, not resolved by majority vote.
    Every remaining category needs at least three unique normalized requests.
    """
    reader = csv.DictReader(io.StringIO(raw.decode("utf-8-sig"), newline=""), strict=True)
    headers = reader.fieldnames or []
    if len(headers) != len(set(headers)):
        raise ValueError("Duplicate CSV column names.")
    if not {"instruction", "category"}.issubset(headers):
        raise ValueError("Source requires instruction and category columns.")
    groups = defaultdict(list)
    input_labels = set()
    rows = 0
    for row in reader:
        rows += 1
        if None in row or any(value is None for value in row.values()):
            raise ValueError(f"Source record {rows}: incorrect field count.")
        text, label = row["instruction"].strip(), row["category"].strip()
        if not text or not label:
            raise ValueError(f"Source record {rows}: blank text or category.")
        input_labels.add(label)
        groups[normalize(text)].append((text, label))
    if not rows:
        raise ValueError("Source CSV has no records.")

    by_category = defaultdict(list)
    conflicts, conflict_rows, duplicates = 0, 0, 0
    for normalized, members in groups.items():
        labels = {label for _, label in members}
        if len(labels) > 1:
            conflicts += 1
            conflict_rows += len(members)
            continue
        label = next(iter(labels))
        duplicates += len(members) - 1
        # Deterministic representative, independent of source row order.
        text = min(text for text, _ in members)
        by_category[label].append({
            "ticket_id": digest(normalized.encode("utf-8")),
            "text": text,
            "category": label,
        })

    if len(input_labels) < 2:
        raise ValueError("Classification requires at least two categories.")
    splits = {"train": [], "validation": [], "test": []}
    for label in sorted(input_labels):
        members = by_category[label]
        if len(members) < 3:
            raise ValueError(f"Category {label!r} requires at least three nonconflicting unique requests.")
        members.sort(key=lambda item: digest(f"{seed}:{item['ticket_id']}".encode()))
        holdout = max(1, round(len(members) * 0.15))
        splits["validation"].extend(members[:holdout])
        splits["test"].extend(members[holdout:2 * holdout])
        splits["train"].extend(members[2 * holdout:])
    audit = {
        "input_rows": rows,
        "unique_normalized_requests": len(groups),
        "conflicting_groups_quarantined": conflicts,
        "conflicting_rows_quarantined": conflict_rows,
        "duplicate_rows_removed": duplicates,
        "retained_rows": sum(map(len, splits.values())),
        "categories": sorted(input_labels),
        "split_counts": {name: dict(sorted(Counter(r["category"] for r in records).items()))
                         for name, records in splits.items()},
    }
    return splits, audit


def prepare(source: Path, output: Path, revision: str, license_file: Path, seed: int = 42) -> dict:
    """Write a new output directory; refuse to replace existing artifacts."""
    if not re.fullmatch(r"[0-9a-fA-F]{40}", revision):
        raise ValueError("Source revision must be a full 40-character Git commit SHA.")
    if output.exists():
        raise ValueError("Output directory already exists; choose a new evaluation version.")
    license_bytes = license_file.read_bytes()
    if not license_bytes.strip():
        raise ValueError("A nonempty publisher license file is required.")
    raw = source.read_bytes()
    splits, audit = build_splits(raw, seed)
    manifest = {
        "schema_version": 1,
        "source_url": SOURCE_URL,
        "source_revision": revision.lower(),
        "source_filename": source.name,
        "source_sha256": digest(raw),
        "publisher_license_sha256": digest(license_bytes),
        "license_metadata": "CDLA-Sharing-1.0",
        "seed": seed,
        "normalization": "NFKC + casefold + whitespace collapse; punctuation preserved",
        "split_policy": "per-class hash ordering, 15% validation and test rounded, minimum one each",
        "audit": audit,
        "split_sha256": {},
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    # Stage files before exclusively creating the output directory.
    with tempfile.TemporaryDirectory(dir=output.parent) as staging:
        stage = Path(staging)
        for name, records in splits.items():
            path = stage / f"{name}.csv"
            with path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=FIELDS)
                writer.writeheader()
                writer.writerows(records)
            manifest["split_sha256"][name] = digest(path.read_bytes())
        (stage / "DATA_LICENSE.txt").write_bytes(license_bytes)
        (stage / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        # Exclusive creation also protects against a concurrent run.
        output.mkdir()
        try:
            for path in stage.iterdir():
                shutil.copyfile(path, output / path.name)
        except OSError:
            shutil.rmtree(output)
            raise
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--source-revision", required=True)
    parser.add_argument("--license-file", required=True, type=Path)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    try:
        manifest = prepare(args.source, args.output, args.source_revision, args.license_file, args.seed)
    except (OSError, ValueError, UnicodeError, csv.Error) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    print(json.dumps(manifest["audit"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
