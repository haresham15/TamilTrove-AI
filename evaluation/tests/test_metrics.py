from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "evaluate.py"
SPEC = importlib.util.spec_from_file_location("evaluate", MODULE_PATH)
assert SPEC and SPEC.loader
evaluate = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(evaluate)


class EvaluationTests(unittest.TestCase):
    def test_perfect_first_result(self) -> None:
        record = {"judgments": [{"movie_title": "Kaithi", "relevance": 3}]}
        metrics = evaluate.query_metrics(record, [{"title": "Kaithi"}, {"title": "Vikram"}])
        self.assertEqual(metrics["hit@1"], 1.0)
        self.assertEqual(metrics["mrr"], 1.0)
        self.assertEqual(metrics["ndcg@10"], 1.0)

    def test_missing_result(self) -> None:
        record = {"judgments": [{"movie_title": "Kaithi", "relevance": 3}]}
        metrics = evaluate.query_metrics(record, [{"title": "Vikram"}])
        self.assertEqual(metrics["hit@10"], 0.0)
        self.assertEqual(metrics["mrr"], 0.0)

    def test_tamil_and_tanglish_aliases_are_preserved(self) -> None:
        self.assertIn("starring", evaluate.tokens("Karthi nadicha padam"))
        self.assertIn("starring", evaluate.tokens("Karthi நடித்த படம்"))

    def test_offline_ranker_uses_credited_evidence(self) -> None:
        ranker = evaluate.OfflineRanker(
            [
                {"title": "Kaithi", "genre": "Action", "director": "Lokesh", "cast": "Karthi", "overview": "A prisoner helps the police."},
                {"title": "Other", "genre": "Drama", "director": "Someone", "cast": "Another", "overview": "A family story."},
            ]
        )
        results = ranker.search("Karthi nadicha action padam, Lokesh direction", {}, 2)
        self.assertEqual(results[0]["title"], "Kaithi")


if __name__ == "__main__":
    unittest.main()
