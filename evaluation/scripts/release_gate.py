"""Fail a release on absolute-quality or unexplained relevance regressions."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("report", type=Path)
    parser.add_argument("--baseline", type=Path, default=ROOT / "evaluation" / "reports" / "baseline-v2.json")
    parser.add_argument("--min-hit5", type=float, default=0.80)
    parser.add_argument("--min-slice-hit5", type=float, default=0.75)
    parser.add_argument("--max-ndcg-regression", type=float, default=0.02)
    parser.add_argument("--max-mrr-regression", type=float, default=0.02)
    parser.add_argument("--max-p95-ms", type=float, default=750.0)
    args = parser.parse_args()

    current = json.loads(args.report.read_text(encoding="utf-8"))
    baseline = json.loads(args.baseline.read_text(encoding="utf-8")) if args.baseline.exists() else None
    failures: list[str] = []
    metrics = current["metrics"]

    if current.get("query_count", 0) < 100:
        failures.append("full release evaluation must include at least 100 queries")
    if metrics["hit@5"] < args.min_hit5:
        failures.append(f"Hit@5 {metrics['hit@5']:.3f} is below {args.min_hit5:.3f}")
    for language, slice_metrics in current.get("slices", {}).get("language", {}).items():
        if slice_metrics["hit@5"] < args.min_slice_hit5:
            failures.append(f"{language} Hit@5 {slice_metrics['hit@5']:.3f} is below {args.min_slice_hit5:.3f}")
    if metrics["latency_ms"]["p95"] > args.max_p95_ms:
        failures.append(f"p95 latency {metrics['latency_ms']['p95']:.1f} ms exceeds {args.max_p95_ms:.1f} ms")

    if baseline:
        for name, allowed in (("ndcg@10", args.max_ndcg_regression), ("mrr", args.max_mrr_regression)):
            regression = baseline["metrics"][name] - metrics[name]
            if regression > allowed:
                failures.append(f"{name} regressed by {regression:.3f}; allowed {allowed:.3f}")

    if failures:
        print("Release gate failed:")
        for failure in failures:
            print(f"- {failure}")
        raise SystemExit(1)
    print("Release gate passed")


if __name__ == "__main__":
    main()
