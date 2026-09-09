"""Evaluate cross-modal visual and audio retrieval performance on TamilTrove."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import statistics
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.catalog import Catalog
from app.config import Settings
from app.ranking import SearchIndex

DEFAULT_DATASET = ROOT / "evaluation" / "datasets" / "crossmodal-v4.0.json"
DEFAULT_CATALOG = ROOT / "backend" / "data" / "movies_processed.json"
DEFAULT_EMBEDDINGS = ROOT / "backend" / "data" / "embeddings.npy"
DEFAULT_REPORT = ROOT / "evaluation" / "reports" / "crossmodal_latest.json"


def query_metrics(relevant_ids: set[str], retrieved_ids: list[str]) -> dict[str, float]:
    binary = [1 if mid in relevant_ids else 0 for mid in retrieved_ids]
    first_rank = next((index + 1 for index, value in enumerate(binary) if value), None)

    def hit(k: int) -> float:
        return float(any(binary[:k]))

    def precision(k: int) -> float:
        return sum(binary[:k]) / k if k else 0.0

    def recall(k: int) -> float:
        return sum(binary[:k]) / max(1, len(relevant_ids))

    def ndcg(k: int) -> float:
        gains = binary[:k]
        dcg = sum((2**gain - 1) / math.log2(index + 2) for index, gain in enumerate(gains))
        ideal = sorted(binary, reverse=True)[:k]
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
        "mrr": 1.0 / first_rank if first_rank else 0.0,
        "ndcg@10": ndcg(10),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate cross-modal retrieval performance.")
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    parser.add_argument("--embeddings", type=Path, default=DEFAULT_EMBEDDINGS)
    parser.add_argument("--output", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--threshold", type=float, default=0.75, help="Hit@5 release gate threshold")
    args = parser.parse_args()

    if not args.dataset.exists():
        raise SystemExit(f"Dataset file not found: {args.dataset}")

    payload = json.loads(args.dataset.read_text(encoding="utf-8"))
    queries = payload.get("queries", [])
    print(f"Loaded {len(queries)} cross-modal benchmark queries from {args.dataset.name}")

    settings = Settings(
        data_path=args.catalog,
        embeddings_path=args.embeddings,
        enable_transformer=False,
    )
    catalog = Catalog.load(settings.data_path)
    search_index = SearchIndex(catalog, settings)
    print(f"Built SearchIndex with {len(catalog.movies)} movies.")

    latencies: list[float] = []
    rows: list[dict[str, Any]] = []
    slice_records: dict[str, list[dict[str, Any]]] = defaultdict(list)

    from app.normalization import normalize_query
    from app.schemas import SearchRequest

    for i, record in enumerate(queries, 1):
        t0 = time.perf_counter()
        slice_name = record.get("slice", "general")
        v_weight = 0.85 if "visual" in slice_name else (0.65 if slice_name == "cross-modal" else 0.0)
        a_weight = 0.85 if "audio" in slice_name else (0.65 if slice_name == "cross-modal" else 0.0)
        alpha = 0.4 if slice_name in ("visual-only", "audio-only") else 0.58

        query_text = record.get("query", "")
        normalized_q = normalize_query(query_text)
        req = SearchRequest(
            query=query_text,
            visual_query=record.get("visual_query") or None,
            audio_query=record.get("audio_query") or None,
            visual_weight=v_weight,
            audio_weight=a_weight,
            alpha=alpha,
            page_size=10,
        )
        ranked_movies, _meta, _coords = search_index.rank(normalized_q, req)
        elapsed_ms = (time.perf_counter() - t0) * 1000
        latencies.append(elapsed_ms)

        retrieved_ids = [r.movie.id for r in ranked_movies[:10]]
        relevant_ids = set(record.get("relevant_movie_ids", []))
        metrics = query_metrics(relevant_ids, retrieved_ids)

        row = {
            "id": record["id"],
            "slice": slice_name,
            "query": record.get("query"),
            "visual_query": record.get("visual_query"),
            "audio_query": record.get("audio_query"),
            "latency_ms": elapsed_ms,
            "metrics": metrics,
            "retrieved_titles": [r.movie.title for r in ranked_movies[:5]],
        }
        rows.append(row)
        slice_records[slice_name].append(row)
        if i % 5 == 0 or i == len(queries):
            print(f"  Processed {i}/{len(queries)} queries...", flush=True)

    # Compute aggregate metrics
    metric_keys = ["hit@1", "hit@5", "hit@10", "precision@5", "recall@5", "mrr", "ndcg@10"]
    global_metrics = {k: statistics.fmean(r["metrics"][k] for r in rows) for k in metric_keys}
    global_metrics["latency_p50_ms"] = statistics.median(latencies) if latencies else 0.0
    global_metrics["latency_p95_ms"] = sorted(latencies)[int(len(latencies) * 0.95)] if latencies else 0.0

    slice_summary: dict[str, dict[str, float]] = {}
    for s_name, s_rows in slice_records.items():
        slice_summary[s_name] = {k: statistics.fmean(r["metrics"][k] for r in s_rows) for k in metric_keys}
        slice_summary[s_name]["count"] = len(s_rows)

    report = {
        "timestamp": dt.datetime.now(dt.timezone.utc).isoformat(),
        "benchmark_version": payload.get("version", "v4.0"),
        "total_queries": len(queries),
        "global_metrics": global_metrics,
        "slice_metrics": slice_summary,
        "passed": global_metrics["hit@5"] >= args.threshold,
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print("\n" + "=" * 60)
    print("CROSS-MODAL RETRIEVAL BENCHMARK REPORT (V4.0)")
    print("=" * 60)
    print(f"Overall Hit@1:     {global_metrics['hit@1'] * 100:.1f}%")
    print(f"Overall Hit@5:     {global_metrics['hit@5'] * 100:.1f}% (Target: >={args.threshold * 100:.0f}%)")
    print(f"Overall Hit@10:    {global_metrics['hit@10'] * 100:.1f}%")
    print(f"Overall MRR:       {global_metrics['mrr']:.3f}")
    print(f"Overall NDCG@10:   {global_metrics['ndcg@10']:.3f}")
    print(f"Latency P50:       {global_metrics['latency_p50_ms']:.2f}ms")
    print(f"Latency P95:       {global_metrics['latency_p95_ms']:.2f}ms")
    print("-" * 60)
    print("Slice Breakdown:")
    for s_name, sm in sorted(slice_summary.items()):
        print(f"  [{s_name:12s}] N={sm['count']:2d} | Hit@5: {sm['hit@5'] * 100:5.1f}% | MRR: {sm['mrr']:.3f}")
    print("=" * 60)

    if report["passed"]:
        print(f"SUCCESS: Cross-modal retrieval Hit@5 ({global_metrics['hit@5']*100:.1f}%) meets target.")
    else:
        print(f"FAILURE: Cross-modal retrieval Hit@5 ({global_metrics['hit@5']*100:.1f}%) below target ({args.threshold*100:.0f}%).")
        sys.exit(1)


if __name__ == "__main__":
    main()
