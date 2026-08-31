from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.catalog import Catalog  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate a TamilTrove catalog and embedding bundle."
    )
    parser.add_argument(
        "--data",
        type=Path,
        default=BACKEND_DIR / "data" / "movies_processed.json",
        help="Catalog JSON path.",
    )
    parser.add_argument(
        "--embeddings",
        type=Path,
        default=BACKEND_DIR / "data" / "embeddings.npy",
        help="Optional NumPy embedding matrix path.",
    )
    parser.add_argument(
        "--allow-invalid",
        action="store_true",
        help="Report invalid or duplicate rows without returning a non-zero status.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    catalog = Catalog.load(args.data.resolve(), args.embeddings.resolve())
    report = catalog.validation_report
    print(json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True))
    blocking = bool(
        report["invalid_records"]
        or report["duplicate_identities"]
        or report["embedding_errors"]
        or report["accepted_records"] != report["source_records"]
    )
    return 0 if args.allow_invalid or not blocking else 1


if __name__ == "__main__":
    raise SystemExit(main())
