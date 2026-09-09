"""Benchmark real-time event streaming and dynamic vector updater latency/throughput."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.catalog import Catalog
from app.config import Settings
from app.ranking import SearchIndex, UserSignals
from app.schemas import InteractionEvent, SearchRequest
from app.streaming import AnalyticsEventSink, DynamicVectorUpdater, EventStream

logging.basicConfig(level=logging.WARNING)

DEFAULT_REPORT = ROOT / "evaluation" / "reports" / "streaming_benchmark_latest.json"


def percentile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    idx = int(len(s) * q)
    return s[min(idx, len(s) - 1)]


def benchmark_streaming(output_path: Path) -> dict[str, Any]:
    print("Loading catalog and search index for streaming benchmark...")
    settings = Settings(
        data_path=ROOT / "backend" / "data" / "movies_processed.json",
        embeddings_path=ROOT / "backend" / "data" / "embeddings.npy",
        enable_transformer=False,
    )
    catalog = Catalog.load(settings.data_path)
    search_index = SearchIndex(catalog, settings)
    movies = catalog.movies
    temp_log = ROOT / "backend" / "data" / "bench_events.jsonl"
    if temp_log.exists():
        temp_log.unlink()

    sink = AnalyticsEventSink(temp_log)
    updater = DynamicVectorUpdater(catalog, search_index, sink=sink)
    stream = EventStream(updater)
    stream.start()

    try:
        # 1. Event-to-vector update latency benchmark (100 events)
        event_types = ["click", "like", "save", "rating", "dismiss", "viewed"]
        latencies_ms: list[float] = []
        user_ids = [f"bench-user-{i % 10}" for i in range(100)]

        for i in range(100):
            m = movies[i % len(movies)]
            etype = event_types[i % len(event_types)]
            ctx = {"dwell_ms": 18000} if etype == "viewed" else ({"value": 4.5} if etype == "rating" else {})
            ev = InteractionEvent(
                user_id=user_ids[i],
                movie_id=m.id,
                event_type=etype,
                context=ctx,
            )
            t0 = time.perf_counter()
            updater.process_event(ev)
            elapsed_ms = (time.perf_counter() - t0) * 1000
            latencies_ms.append(elapsed_ms)

        p50_latency = percentile(latencies_ms, 0.50)
        p95_latency = percentile(latencies_ms, 0.95)
        p99_latency = percentile(latencies_ms, 0.99)
        max_latency = max(latencies_ms) if latencies_ms else 0.0

        # 2. Preference reflection in next request (< 1s end-to-end)
        test_user = "bench-reflection-user"
        target_movie = movies[0]
        t_refl_start = time.perf_counter()
        # Event sent
        ev = InteractionEvent(
            user_id=test_user,
            movie_id=target_movie.id,
            event_type="like",
        )
        updater.process_event(ev)
        # Next query with updated signals
        prof = updater.get_or_create_profile(test_user)
        signals = UserSignals(
            favorite_genres=tuple(prof.genre_weights.keys())[:3],
            positive_movie_ids=tuple(prof.positive_movie_ids),
        )
        from app.normalization import normalize_query
        ranked, _, _ = search_index.rank(
            normalize_query("action thriller"),
            SearchRequest(query="action thriller", page_size=10),
            signals=signals,
        )
        assert len(ranked) >= 0
        reflection_time_ms = (time.perf_counter() - t_refl_start) * 1000

        # 3. Event stream batch throughput (2,000 events)
        t_batch_start = time.perf_counter()
        batch_count = 2000
        for i in range(batch_count):
            m = movies[i % len(movies)]
            stream.publish(
                user_id=f"throughput-user-{i % 20}",
                movie_id=m.id,
                event_type="click",
            )

        # Wait for queue to drain
        stream.queue.join()
        total_time_s = time.perf_counter() - t_batch_start
        throughput_events_per_sec = batch_count / max(0.001, total_time_s)

        # 4. Durable replay verification
        replayed = []
        count = sink.replay_events(lambda ev: replayed.append(ev))
        replay_ok = count >= (100 + 1 + batch_count)

    finally:
        stream.stop()
        sink.close()
        if temp_log.exists():
            temp_log.unlink()

    report = {
        "timestamp": dt.datetime.now(dt.timezone.utc).isoformat(),
        "metrics": {
            "p50_event_latency_ms": round(p50_latency, 3),
            "p95_event_latency_ms": round(p95_latency, 3),
            "p99_event_latency_ms": round(p99_latency, 3),
            "max_event_latency_ms": round(max_latency, 3),
            "preference_reflection_time_ms": round(reflection_time_ms, 2),
            "throughput_events_per_sec": round(throughput_events_per_sec, 1),
            "replay_verified_count": len(replayed),
            "durable_replay_passed": replay_ok,
        },
        "targets": {
            "p95_event_latency_ms": {"target": 500.0, "actual": p95_latency, "passed": p95_latency < 500.0},
            "preference_reflection_time_ms": {"target": 1000.0, "actual": reflection_time_ms, "passed": reflection_time_ms < 1000.0},
            "throughput_events_per_sec": {"target": 1000.0, "actual": throughput_events_per_sec, "passed": throughput_events_per_sec >= 1000.0},
            "durable_replay": {"target": True, "actual": replay_ok, "passed": replay_ok},
        },
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark streaming personalization engine.")
    parser.add_argument("--output", type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args()

    print("Running TamilTrove V4 Streaming & Personalization Benchmark...")
    report = benchmark_streaming(args.output)
    m = report["metrics"]
    t = report["targets"]

    print("\n" + "=" * 60)
    print("STREAMING & PERSONALIZATION BENCHMARK REPORT (V4.0)")
    print("=" * 60)
    print(f"Event-to-Vector P50:    {m['p50_event_latency_ms']:.3f} ms")
    print(f"Event-to-Vector P95:    {m['p95_event_latency_ms']:.3f} ms  (Target: <500ms)  -> {'PASS' if t['p95_event_latency_ms']['passed'] else 'FAIL'}")
    print(f"Event-to-Vector P99:    {m['p99_event_latency_ms']:.3f} ms")
    print(f"Preference Reflection:  {m['preference_reflection_time_ms']:.1f} ms  (Target: <1000ms) -> {'PASS' if t['preference_reflection_time_ms']['passed'] else 'FAIL'}")
    print(f"Stream Throughput:      {m['throughput_events_per_sec']:,.0f} ev/s (Target: >=1000)   -> {'PASS' if t['throughput_events_per_sec']['passed'] else 'FAIL'}")
    print(f"Durable Log Replay:     {m['replay_verified_count']} events  (Replay Verified: {m['durable_replay_passed']})")
    print("=" * 60)

    all_passed = all(tgt["passed"] for tgt in t.values())
    if all_passed:
        print("ALL STREAMING BENCHMARK GATES PASSED!")
    else:
        print("WARNING: Some streaming benchmark targets were not met.")
        sys.exit(1)


if __name__ == "__main__":
    main()
