"""Validate benchmark structure, coverage, review state, and catalog references."""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--dataset", type=Path, default=ROOT / "evaluation" / "datasets" / "relevance-v2.0.json"
    )
    parser.add_argument(
        "--catalog", type=Path, default=ROOT / "backend" / "data" / "movies_processed.json"
    )
    args = parser.parse_args()

    payload = json.loads(args.dataset.read_text(encoding="utf-8"))
    catalog = json.loads(args.catalog.read_text(encoding="utf-8"))
    records = payload.get("queries", [])
    failures: list[str] = []

    if not re.fullmatch(r"\d+\.\d+\.\d+", str(payload.get("dataset_version", ""))):
        failures.append("dataset_version must use semantic versioning")
    if len(records) < 100:
        failures.append(f"expected at least 100 queries, found {len(records)}")

    identifiers = [record.get("id") for record in records]
    queries = [str(record.get("query", "")).strip().casefold() for record in records]
    if len(set(identifiers)) != len(identifiers):
        failures.append("query IDs must be unique")
    if len(set(queries)) != len(queries):
        failures.append("query text must be unique")

    languages = Counter(record.get("language") for record in records)
    for language in ("en", "ta", "tanglish"):
        if languages[language] < 20:
            failures.append(f"language slice {language!r} needs at least 20 queries")

    catalog_titles = {str(movie.get("title", "")).strip().casefold() for movie in catalog}
    for index, record in enumerate(records, start=1):
        prefix = record.get("id") or f"record {index}"
        if record.get("review_status") != "reviewed":
            failures.append(f"{prefix}: judgment is not reviewed")
        if not str(record.get("reviewer_notes", "")).strip():
            failures.append(f"{prefix}: reviewer notes are required")
        judgments = record.get("judgments") or []
        if not judgments:
            failures.append(f"{prefix}: at least one judgment is required")
        for judgment in judgments:
            title = str(judgment.get("movie_title", "")).strip().casefold()
            if title not in catalog_titles:
                failures.append(f"{prefix}: unknown catalog movie {judgment.get('movie_title')!r}")
            if judgment.get("relevance") not in (0, 1, 2, 3):
                failures.append(f"{prefix}: relevance must be an integer from 0 to 3")

    if failures:
        print("Benchmark validation failed:")
        for failure in failures[:50]:
            print(f"- {failure}")
        if len(failures) > 50:
            print(f"- ... and {len(failures) - 50} more")
        raise SystemExit(1)
    print(f"Validated {len(records)} reviewed queries: {dict(sorted(languages.items()))}")


if __name__ == "__main__":
    main()
