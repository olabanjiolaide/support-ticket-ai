"""Run with: python -m support_ticket_ai data/sample_tickets.csv."""

import argparse
from collections import Counter
import sys

from .data import load_tickets


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate and summarize ticket CSV data.")
    parser.add_argument("csv_path", help="Path to the ticket CSV")
    args = parser.parse_args()
    try:
        tickets = load_tickets(args.csv_path)
    except (OSError, ValueError, UnicodeError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    print(f"Validated {len(tickets)} tickets")
    for category, count in sorted(Counter(ticket.category for ticket in tickets).items()):
        print(f"{category}: {count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
