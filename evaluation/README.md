# Relevance evaluation

TamilTrove keeps relevance judgments and ranking measurements versioned with the application. The committed V2 dataset contains 120 reviewed, catalog-grounded queries split evenly across English, Tamil, and Tanglish patterns. Seed judgments use unambiguous plot or credit evidence; obtain an independent audience review before publishing external quality claims.

Run the dependency-free PR baseline:

```bash
python evaluation/scripts/validate_dataset.py
python -m unittest discover -s evaluation/tests
python evaluation/scripts/evaluate.py
python evaluation/scripts/release_gate.py evaluation/reports/latest.json
```

Evaluate a running V2 API instead:

```bash
python evaluation/scripts/evaluate.py --api-url http://localhost:8000 --output evaluation/reports/api-local.json
python evaluation/scripts/release_gate.py evaluation/reports/api-local.json
```

Reports contain Hit@1/5/10, Precision@5/10, Recall@5/10, MRR, NDCG@10, coverage, result diversity, zero-result rate, p50/p95/p99 latency, and language/category slices. `release_gate.py` enforces the absolute Hit@5 target, per-language floors, the latency budget, and bounded MRR/NDCG regression against the recorded baseline.

To revise the benchmark, update `build_benchmark.py`, generate a new version, inspect every changed judgment, obtain additional review for ambiguous cases, and deliberately update the dataset version and baseline. Never tune ranker weights on the release-test judgments.
