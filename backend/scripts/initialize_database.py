from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.storage import create_store  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Apply the V2 schema when needed and verify database connectivity."
    )
    parser.add_argument(
        "--database-url",
        default=os.getenv("TAMILTROVE_DATABASE_URL") or os.getenv("DATABASE_URL"),
        help="sqlite:/// or postgresql:// URL; defaults to TAMILTROVE_DATABASE_URL/DATABASE_URL.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.database_url:
        raise SystemExit("--database-url or TAMILTROVE_DATABASE_URL is required")
    store = create_store(args.database_url)
    try:
        store.initialize()
        if not store.ping():
            raise RuntimeError("database ping failed after initialization")
    finally:
        store.close()
    print("TamilTrove database is initialized and reachable.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
