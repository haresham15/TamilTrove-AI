"""Evaluate autonomous recommendation agent on clarification, tool-calling, and grounding."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.agent import RecommendationAgent
from app.catalog import Catalog
from app.config import Settings
from app.ranking import SearchIndex
from app.schemas import AgentChatRequest
from app.services import ServiceContainer

logging.basicConfig(level=logging.WARNING)

DEFAULT_REPORT = ROOT / "evaluation" / "reports" / "agent_eval_latest.json"

AMBIGUOUS_TEST_QUERIES = [
    "recommend a movie",
    "something intense but not action",
    "thriller",
    "hidden gem",
    "what should I watch tonight",
    "good movie",
    "comedy",
    "any suggestions",
    "something intense",
    "underrated",
]

SPECIFIC_TEST_QUERIES = [
    "Kamal Haasan crime investigation directed by Lokesh",
    "Village drama with Dhanush directed by Vetri Maaran",
    "Sci-fi thriller starring Suriya directed by Vikram Kumar",
    "Feel-good family comedy starring Sivakarthikeyan",
    "Dark psychological thriller starring Vijay Sethupathi",
]

MULTI_TURN_CONVERSATIONS = [
    {
        "name": "Intense Non-Action Flow",
        "turn_1": "something intense but not action",
        "turn_2": "Psychological Thriller & Mind Games",
        "expected_genre": "thriller",
    },
    {
        "name": "Hidden Gem Flow",
        "turn_1": "hidden gem",
        "turn_2": "Overlooked Neo-Noir Thrillers",
        "expected_genre": "thriller",
    },
    {
        "name": "Tonight Mood Flow",
        "turn_1": "what should I watch tonight",
        "turn_2": "Feel-good Village & Family Drama",
        "expected_genre": "drama",
    },
]


def setup_container() -> ServiceContainer:
    settings = Settings(
        data_path=ROOT / "backend" / "data" / "movies_processed.json",
        embeddings_path=ROOT / "backend" / "data" / "embeddings.npy",
        enable_transformer=False,
    )
    catalog = Catalog.load(settings.data_path)
    index = SearchIndex(catalog, settings)
    from app.observability import MetricRegistry, Tracer
    container = ServiceContainer(
        settings=settings,
        catalog=catalog,
        store=None,
        index=index,
        metrics=MetricRegistry(),
        tracer=Tracer("tamiltrove-agent-eval", "v4"),
        ingestion=None,
    )
    return container


def evaluate_agent(container: ServiceContainer) -> dict[str, Any]:
    agent = RecommendationAgent(container)
    catalog = container.catalog
    catalog_by_id = {m.id: m for m in catalog.movies}
    catalog_by_title = {m.canonical_title.casefold(): m for m in catalog.movies}

    # 1. Ambiguity & Clarification Rate
    clarification_successes = 0
    for query in AMBIGUOUS_TEST_QUERIES:
        session_id = f"test-clarify-{abs(hash(query))}"
        req = AgentChatRequest(message=query, session_id=session_id)
        resp = agent.chat(req)
        if resp.needs_clarification and resp.clarification is not None:
            clarification_successes += 1
    clarification_rate = clarification_successes / max(1, len(AMBIGUOUS_TEST_QUERIES))

    # 2. Specific Queries & Tool-Call Accuracy + Grounding Fidelity
    tool_calls_total = 0
    tool_calls_valid = 0
    total_recommendations = 0
    grounded_recommendations = 0
    fallbacks = 0

    for query in SPECIFIC_TEST_QUERIES:
        session_id = f"test-specific-{abs(hash(query))}"
        req = AgentChatRequest(message=query, session_id=session_id)
        try:
            resp = agent.chat(req)
        except Exception:  # noqa: BLE001
            fallbacks += 1
            continue

        for tc in resp.tool_calls_executed:
            tool_calls_total += 1
            if tc.name in ("search_movies", "get_movie_details", "get_similar_movies") and isinstance(tc.arguments, dict):
                tool_calls_valid += 1

        for rec in resp.recommendations:
            total_recommendations += 1
            # Grounding check: verify movie exists in catalog
            matched = catalog_by_id.get(rec.id) or catalog_by_title.get(rec.title.casefold())
            if matched is not None and (
                matched.canonical_title.casefold() == rec.title.casefold()
                or matched.title.casefold() == rec.title.casefold()
            ):
                grounded_recommendations += 1

    # 3. Multi-Turn Conversation Evaluation
    multi_turn_results = []
    total_turns_to_success = []

    for conv in MULTI_TURN_CONVERSATIONS:
        session_id = f"test-multiturn-{abs(hash(conv['name']))}"
        # Turn 1
        req1 = AgentChatRequest(message=conv["turn_1"], session_id=session_id)
        resp1 = agent.chat(req1)
        turn_count = 1

        if resp1.needs_clarification:
            # Turn 2: User responds
            req2 = AgentChatRequest(message=conv["turn_2"], session_id=session_id)
            resp2 = agent.chat(req2)
            turn_count = 2

            for tc in resp2.tool_calls_executed:
                tool_calls_total += 1
                if isinstance(tc.arguments, dict):
                    tool_calls_valid += 1

            for rec in resp2.recommendations:
                total_recommendations += 1
                matched = catalog_by_id.get(rec.id) or catalog_by_title.get(rec.title.casefold())
                if matched:
                    grounded_recommendations += 1

            if resp2.recommendations:
                total_turns_to_success.append(turn_count)
                multi_turn_results.append({
                    "name": conv["name"],
                    "turns": turn_count,
                    "top_recommended": resp2.recommendations[0].title,
                    "success": True,
                })
            else:
                fallbacks += 1
        else:
            fallbacks += 1

    tool_accuracy = tool_calls_valid / max(1, tool_calls_total) if tool_calls_total > 0 else 1.0
    grounding_fidelity = grounded_recommendations / max(1, total_recommendations) if total_recommendations > 0 else 1.0
    avg_turns = sum(total_turns_to_success) / max(1, len(total_turns_to_success)) if total_turns_to_success else 0.0
    fallback_rate = fallbacks / (len(AMBIGUOUS_TEST_QUERIES) + len(SPECIFIC_TEST_QUERIES) + len(MULTI_TURN_CONVERSATIONS))

    return {
        "timestamp": dt.datetime.now(dt.timezone.utc).isoformat(),
        "metrics": {
            "clarification_rate": clarification_rate,
            "tool_call_accuracy": tool_accuracy,
            "grounding_fidelity": grounding_fidelity,
            "avg_conversation_turns": avg_turns,
            "fallback_rate": fallback_rate,
            "total_tool_calls": tool_calls_total,
            "total_recommendations_verified": total_recommendations,
        },
        "multi_turn_results": multi_turn_results,
        "targets": {
            "clarification_rate": {"target": 0.80, "passed": clarification_rate >= 0.80},
            "tool_call_accuracy": {"target": 0.95, "passed": tool_accuracy >= 0.95},
            "grounding_fidelity": {"target": 1.00, "passed": grounding_fidelity >= 0.999},
            "avg_conversation_turns": {"target": 4.0, "passed": avg_turns <= 4.0},
            "fallback_rate": {"target": 0.05, "passed": fallback_rate <= 0.05},
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate autonomous recommendation agent.")
    parser.add_argument("--output", type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args()

    print("Initializing TamilTrove V4 Agent Evaluation...")
    container = setup_container()
    print("Catalog and SearchIndex loaded.")

    report = evaluate_agent(container)
    m = report["metrics"]
    t = report["targets"]

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print("\n" + "=" * 60)
    print("AUTONOMOUS AGENT EVALUATION REPORT (V4.0)")
    print("=" * 60)
    print(f"Clarification Rate:     {m['clarification_rate'] * 100:.1f}%  (Target: >=80.0%) -> {'PASS' if t['clarification_rate']['passed'] else 'FAIL'}")
    print(f"Tool-Call Accuracy:     {m['tool_call_accuracy'] * 100:.1f}%  (Target: >=95.0%) -> {'PASS' if t['tool_call_accuracy']['passed'] else 'FAIL'}")
    print(f"Grounding Fidelity:     {m['grounding_fidelity'] * 100:.1f}% (Target: 100.0%) -> {'PASS' if t['grounding_fidelity']['passed'] else 'FAIL'}")
    print(f"Avg Conversation Turns: {m['avg_conversation_turns']:.1f}   (Target: <=4.0)   -> {'PASS' if t['avg_conversation_turns']['passed'] else 'FAIL'}")
    print(f"Fallback Rate:          {m['fallback_rate'] * 100:.1f}%   (Target: <5.0)   -> {'PASS' if t['fallback_rate']['passed'] else 'FAIL'}")
    print("-" * 60)
    print(f"Verified Recommendations: {m['total_recommendations_verified']}")
    print(f"Total Tool Calls:         {m['total_tool_calls']}")
    print("=" * 60)

    all_passed = all(tgt["passed"] for tgt in t.values())
    if all_passed:
        print("ALL AGENT BENCHMARK GATES PASSED!")
    else:
        print("WARNING: Some agent benchmark targets were not met.")
        sys.exit(1)


if __name__ == "__main__":
    main()
