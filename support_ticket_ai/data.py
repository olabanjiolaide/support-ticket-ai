"""Validate the ticket data contract before any model sees the data."""

import csv
from dataclasses import dataclass
from pathlib import Path

CATEGORIES = frozenset({"billing", "account", "technical"})
REQUIRED_COLUMNS = frozenset({"ticket_id", "text", "category"})


@dataclass(frozen=True)
class Ticket:
    ticket_id: str
    text: str
    category: str


def load_tickets(
    path: str | Path, *, categories: frozenset[str] = CATEGORIES
) -> list[Ticket]:
    """Load a nonempty UTF-8 CSV, or raise ValueError for invalid records.

    Surrounding whitespace is stripped. Category names remain case-sensitive.
    I/O errors are left to callers to handle.
    """
    tickets = []
    seen_ids = set()
    with Path(path).open(encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source, strict=True)
        try:
            headers = reader.fieldnames or []
            if len(headers) != len(set(headers)):
                raise ValueError("Duplicate CSV column names.")
            missing = REQUIRED_COLUMNS - set(headers)
            if missing:
                raise ValueError(f"Missing required columns: {', '.join(sorted(missing))}")
            for record_number, row in enumerate(reader, start=1):
                if None in row or any(value is None for value in row.values()):
                    raise ValueError(f"Record {record_number}: incorrect number of fields.")
                fields = {key: row[key].strip() for key in REQUIRED_COLUMNS}
                if not all(fields.values()):
                    raise ValueError(f"Record {record_number}: required fields cannot be blank.")
                if fields["category"] not in categories:
                    raise ValueError(f"Record {record_number}: unsupported category.")
                ticket_id = fields["ticket_id"]
                if ticket_id in seen_ids:
                    raise ValueError(f"Record {record_number}: duplicate ticket_id.")
                seen_ids.add(ticket_id)
                tickets.append(Ticket(**fields))
        except csv.Error as error:
            raise ValueError(f"Malformed CSV near line {reader.line_num}.") from error
    if not tickets:
        raise ValueError("CSV must contain at least one ticket.")
    return tickets
