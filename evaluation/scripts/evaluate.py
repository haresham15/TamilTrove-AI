"""Run deterministic offline or live-API TamilTrove relevance evaluation."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import os
import platform
import re
import statistics
import subprocess
import time
import tracemalloc
import unicodedata
import urllib.error
import urllib.request
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATASET = ROOT / "evaluation" / "datasets" / "relevance-v2.0.json"
DEFAULT_CATALOG = ROOT / "backend" / "data" / "movies_processed.json"
DEFAULT_REPORT = ROOT / "evaluation" / "reports" / "latest.json"

ALIASES = {
    "nadicha": "starring",
    "naditha": "starring",
    "padam": "film",
    "padamum": "film",
    "maadhiri": "like",
    "mari": "like",
    "iyakkam": "directed",
    "திரைப்படம்": "film",
    "படம்": "film",
    "நடித்த": "starring",
    "இயக்கிய": "directed",
    "இயக்கம்": "directed",
}


def normalize(value: Any) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).casefold()
    text = re.sub(r"[^\w\u0B80-\u0BFF]+", " ", text, flags=re.UNICODE)
    words = [ALIASES.get(word, word) for word in text.split()]
    return " ".join(words)


def tokens(value: Any) -> set[str]:
    return {word for word in normalize(value).split() if len(word) > 1}


def percentile(values: list[float], quantile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    position = (len(ordered) - 1) * quantile
    lower, upper = math.floor(position), math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


class OfflineRanker:
    """Dependency-free lexical baseline used for fast PR regression checks."""

    def __init__(self, catalog: Iterable[dict[str, Any]]) -> None:
        self.movies = list(catalog)
        self.documents: list[tuple[dict[str, Any], dict[str, set[str]], str, set[str]]] = []
        for movie in self.movies:
            fields = {
                "title": tokens(movie.get("title")),
                "genre": tokens(movie.get("genre")),
                "director": tokens(movie.get("director")),
                "cast": tokens(movie.get("cast")),
                "overview": tokens(movie.get("overview")),
            }
            self.documents.append(
                (movie, fields, normalize(movie.get("title")), set().union(*fields.values()))
            )

    def search(self, query: str, filters: dict[str, Any], limit: int = 10) -> list[dict[str, Any]]:
        query_normalized = normalize(query)
        query_tokens = tokens(query)
        ranked: list[tuple[float, str, dict[str, Any]]] = []
        for movie, fields, title_normalized, document_tokens in self.documents:
            if not self._matches_filters(movie, filters):
                continue
            score = sum(
                len(query_tokens & field_tokens) * weight
                for field_tokens, weight in (
                    (fields["title"], 8.0),
                    (fields["director"], 6.0),
                    (fields["cast"], 5.0),
                    (fields["genre"], 3.0),
                    (fields["overview"], 1.0),
                )
            )
            if title_normalized and title_normalized in query_normalized:
                score += 25.0
            denominator = max(1, len(query_tokens | document_tokens))
            score += len(query_tokens & document_tokens) / denominator
            ranked.append((score, title_normalized, movie))
        ranked.sort(key=lambda item: (-item[0], item[1]))
        return [
            {"id": movie.get("id"), "title": movie.get("title"), "score": score}
            for score, _, movie in ranked[:limit]
        ]

    @staticmethod
    def _matches_filters(movie: dict[str, Any], filters: dict[str, Any]) -> bool:
        genre = filters.get("genre")
        if genre and normalize(genre) not in normalize(movie.get("genre")):
            return False
        year = movie.get("release_year") or movie.get("year")
        if filters.get("year_min") and year and int(year) < int(filters["year_min"]):
            return False
        if filters.get("year_max") and year and int(year) > int(filters["year_max"]):
            return False
        return True


class ApiRanker:
    def __init__(self, api_url: str, token: str | None) -> None:
        self.endpoint = f"{api_url.rstrip('/')}/api/v1/search"
        self.token = token

    def search(self, query: str, filters: dict[str, Any], limit: int = 10) -> list[dict[str, Any]]:
        body = json.dumps({"query": query, "filters": filters, "page": 1, "page_size": limit}).encode()
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        request = urllib.request.Request(self.endpoint, data=body, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                payload = json.load(response)
        except urllib.error.HTTPError as error:
            detail = error.read().decode(errors="replace")
            raise RuntimeError(f"Search returned HTTP {error.code}: {detail}") from error
        return payload.get("results", payload.get("items", []))


def result_title(result: dict[str, Any]) -> str:
    return normalize(result.get("canonical_title") or result.get("title") or result.get("movie", {}).get("title"))


def query_metrics(record: dict[str, Any], results: list[dict[str, Any]]) -> dict[str, float]:
    grades = {normalize(item["movie_title"]): int(item["relevance"]) for item in record["judgments"]}
    ranked_titles = [result_title(item) for item in results]
    relevant = {title for title, grade in grades.items() if grade > 0}
    binary = [1 if title in relevant else 0 for title in ranked_titles]
    first_rank = next((index + 1 for index, value in enumerate(binary) if value), None)

    def hit(k: int) -> float:
        return float(any(binary[:k]))

    def precision(k: int) -> float:
        return sum(binary[:k]) / k

    def recall(k: int) -> float:
        return sum(binary[:k]) / max(1, len(relevant))

    def ndcg(k: int) -> float:
        gains = [grades.get(title, 0) for title in ranked_titles[:k]]
        dcg = sum((2**gain - 1) / math.log2(index + 2) for index, gain in enumerate(gains))
        ideal = sorted(grades.values(), reverse=True)[:k]
        idcg = sum((2**gain - 1) / math.log2(index + 2) for index, gain in enumerate(ideal))
        return dcg / idcg if idcg else 0.0

    return {
        "hit@1": hit(1),
        "hit@5": hit(5),
        "hit@10": hit(10),
        "precision@5": precision(5),
        "precision@10": precision(10),
        "recall@5": recall(5),
        "recall@10": recall(10),
        "mrr": 1 / first_rank if first_rank else 0.0,
        "ndcg@10": ndcg(10),
    }


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    metric_names = list(rows[0]["metrics"]) if rows else []
    metrics = {name: statistics.fmean(row["metrics"][name] for row in rows) for name in metric_names}
    latencies = [row["latency_ms"] for row in rows]
    unique_results = {title for row in rows for title in row["result_titles"] if title}
    result_count = sum(len(row["result_titles"]) for row in rows)
    metrics.update(
        {
            "catalog_coverage_count": len(unique_results),
            "result_diversity": len(unique_results) / max(1, result_count),
            "zero_result_rate": statistics.fmean(not row["result_titles"] for row in rows),
            "error_rate": statistics.fmean(bool(row.get("error")) for row in rows),
            "latency_ms": {
                "p50": percentile(latencies, 0.50),
                "p95": percentile(latencies, 0.95),
                "p99": percentile(latencies, 0.99),
                "mean": statistics.fmean(latencies) if latencies else 0.0,
            },
        }
    )
    return metrics


def git_revision() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, stderr=subprocess.DEVNULL
        ).strip()
    except (OSError, subprocess.SubprocessError):
        return os.getenv("GITHUB_SHA", "unknown")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    parser.add_argument("--api-url")
    parser.add_argument("--token")
    parser.add_argument("--output", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()

    benchmark = json.loads(args.dataset.read_text(encoding="utf-8"))
    records = benchmark["queries"][: args.limit]
    if len(records) < 100 and args.limit is None:
        raise SystemExit("Full V2 evaluation requires at least 100 queries")
    if any(record.get("review_status") != "reviewed" for record in records):
        raise SystemExit("Benchmark contains unreviewed judgments")

    if args.api_url:
        ranker: OfflineRanker | ApiRanker = ApiRanker(args.api_url, args.token)
        mode = "live_api"
    else:
        ranker = OfflineRanker(json.loads(args.catalog.read_text(encoding="utf-8")))
        mode = "offline_lexical_baseline"

    tracemalloc.start()
    evaluation_started = time.perf_counter()
    rows: list[dict[str, Any]] = []
    for record in records:
        started = time.perf_counter()
        error_message = None
        try:
            results = ranker.search(record["query"], record.get("filters", {}), 10)
        except (OSError, RuntimeError, ValueError) as error:
            results = []
            error_message = str(error)[:500]
        latency_ms = (time.perf_counter() - started) * 1000
        rows.append(
            {
                "id": record["id"],
                "language": record["language"],
                "category": record["category"],
                "latency_ms": latency_ms,
                "result_titles": [result_title(item) for item in results],
                "metrics": query_metrics(record, results),
                "error": error_message,
            }
        )

    by_language: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_category: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_language[row["language"]].append(row)
        by_category[row["category"]].append(row)

    _, peak_bytes = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    report = {
        "dataset_version": benchmark["dataset_version"],
        "mode": mode,
        "query_count": len(rows),
        "experiment": {
            "code_commit": git_revision(),
            "recorded_at": dt.datetime.now(dt.UTC).isoformat(),
            "embedding_model": "api-configured" if args.api_url else "none",
            "ranking_version": "api-response" if args.api_url else "offline-lexical-v1",
            "ranking_weights": {
                "exact_title": 25.0,
                "title_token": 8.0,
                "director_token": 6.0,
                "cast_token": 5.0,
                "genre_token": 3.0,
                "overview_token": 1.0,
            }
            if not args.api_url
            else "configured by API",
            "runtime_seconds": time.perf_counter() - evaluation_started,
            "peak_traced_memory_mb": peak_bytes / 1_048_576,
            "runtime": f"Python {platform.python_version()} on {platform.platform()}",
        },
        "metrics": summarize(rows),
        "slices": {
            "language": {key: summarize(value) for key, value in sorted(by_language.items())},
            "category": {key: summarize(value) for key, value in sorted(by_category.items())},
        },
        "queries": rows,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"mode": mode, "query_count": len(rows), **report["metrics"]}, indent=2))


if __name__ == "__main__":
    main()
