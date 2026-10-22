"""Start the demo API on the local loopback interface."""

import argparse
from pathlib import Path

import uvicorn

from .api import create_app


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-dir", required=True, type=Path, help="Trusted model bundle directory")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--semantic-model-dir", type=Path, help="Optional trusted experimental semantic bundle")
    parser.add_argument("--requests-db", type=Path, default=Path("artifacts/requests.sqlite3"), help="Local SQLite request database (created on first launch)")
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("Port must be between 1 and 65535.")
    uvicorn.run(create_app(args.model_dir, args.semantic_model_dir, args.requests_db), host="127.0.0.1", port=args.port)


if __name__ == "__main__":
    main()
