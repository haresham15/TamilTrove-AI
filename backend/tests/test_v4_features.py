"""Unit and integration tests for TamilTrove V4 features."""

import tempfile
from pathlib import Path

import numpy as np
import pytest

from app.agent import RecommendationAgent
from app.catalog import Catalog
from app.config import Settings
from app.multimodal import (
    generate_multimodal_vector,
    infer_audio_profile,
    infer_visual_palette,
)
from app.normalization import normalize_query
from app.observability import MetricRegistry, Tracer
from app.ranking import SearchIndex, cross_modal_rank_fusion
from app.schemas import AgentChatRequest, SearchRequest
from app.services import ServiceContainer
from app.streaming import AnalyticsEventSink, DynamicVectorUpdater, EventStream


@pytest.fixture
def sample_catalog() -> Catalog:
    data_path = Path(__file__).resolve().parents[1] / "data" / "movies_processed.json"
    return Catalog.load(data_path)


@pytest.fixture
def container(sample_catalog: Catalog) -> ServiceContainer:
    settings = Settings(
        data_path=Path(__file__).resolve().parents[1] / "data" / "movies_processed.json",
        embeddings_path=Path(__file__).resolve().parents[1] / "data" / "embeddings.npy",
        enable_transformer=False,
    )
    index = SearchIndex(sample_catalog, settings)
    return ServiceContainer(
        settings=settings,
        catalog=sample_catalog,
        store=None,
        index=index,
        metrics=MetricRegistry(),
        tracer=Tracer("tamiltrove-test", "v4"),
        ingestion=None,
    )


# 1. Multimodal Feature Extraction & Vectors
def test_multimodal_inference():
    palette = infer_visual_palette(
        title="Vikram",
        genres=["action", "thriller"],
        themes=["revenge", "undercover"],
        overview="A black-ops squad led by an undercover cop hunts a violent drug cartel in dark alleyways.",
    )
    assert "dominant_colors" in palette
    assert palette["contrast"] > 0
    assert any(tag in palette["aesthetic_tags"] for tag in ("dark", "noir", "gritty"))

    audio = infer_audio_profile(
        title="Vikram",
        genres=["action", "thriller"],
        themes=["revenge"],
        overview="Fast-paced gun battles and high-energy electronic music.",
    )
    assert audio["bpm"] is not None
    assert audio["energy"] > 0
    assert len(audio["instruments"]) > 0

    # Test vector generation
    vec1 = generate_multimodal_vector("dark noir neon night city", dimension=384, salt="visual")
    vec2 = generate_multimodal_vector("dark noir neon night city", dimension=384, salt="visual")
    assert vec1.shape == (384,)
    assert np.isclose(np.linalg.norm(vec1), 1.0)
    assert np.allclose(vec1, vec2)  # Deterministic


# 2. Cross-Modal Rank Fusion
def test_cross_modal_rank_fusion():
    ch1 = np.array([0.9, 0.5, 0.1])
    ch2 = np.array([0.1, 0.8, 0.7])
    ch3 = np.array([0.8, 0.7, 0.2])

    fused = cross_modal_rank_fusion([(ch1, 1.0), (ch2, 0.8), (ch3, 0.5)], k=60)
    assert len(fused) == 3
    assert all(0 <= val <= 1 for val in fused)


# 3. Search Index Multimodal Scoring
def test_search_index_multimodal(container: ServiceContainer):
    q = normalize_query("detective crime")
    req = SearchRequest(
        query="detective crime",
        visual_query="dark noir rain-soaked",
        audio_query="tense orchestral heartbeat",
        visual_weight=0.7,
        audio_weight=0.6,
        page_size=5,
    )
    results, _, _ = container.index.rank(q, req)
    assert len(results) > 0
    top = results[0]
    assert hasattr(top, "visual")
    assert hasattr(top, "audio")
    assert any(ev.get("modality") in ("visual", "audio") for ev in top.evidence)


# 4. Streaming Personalization & Event Log Replay
def test_streaming_pipeline(container: ServiceContainer):
    with tempfile.TemporaryDirectory() as td:
        sink_path = Path(td) / "events.jsonl"
        sink = AnalyticsEventSink(sink_path)
        updater = DynamicVectorUpdater(container.catalog, container.index, sink=sink)
        stream = EventStream(updater)
        stream.start()

        try:
            user_id = "test-user-v4"
            movie = container.catalog.movies[0]

            # Publish interaction event
            ev = stream.publish(
                user_id=user_id,
                event_type="like",
                movie_id=movie.id,
            )
            assert ev.event_id is not None
            assert ev.user_id == user_id

            # Drain queue
            stream.queue.join()

            # Check user profile update
            prof = updater.get_or_create_profile(user_id)
            assert movie.id in prof.positive_movie_ids
            assert prof.events_processed >= 1

            # Check durable replay
            replayed = []
            count = sink.replay_events(lambda event: replayed.append(event))
            assert count >= 1
            assert replayed[0].user_id == user_id
        finally:
            stream.stop()
            sink.close()


# 5. Recommendation Agent ReAct Loop & Grounding
def test_recommendation_agent_flow(container: ServiceContainer):
    agent = RecommendationAgent(container)

    # Ambiguous initial query -> Clarification
    req_ambiguous = AgentChatRequest(message="recommend a movie")
    res1 = agent.chat(req_ambiguous)
    assert res1.needs_clarification is True
    assert res1.clarification is not None
    assert len(res1.clarification.options) > 0

    # User answers with specific sub-genre -> Recommendations
    session_id = res1.session_id
    req_answer = AgentChatRequest(
        message="High-octane Thriller & Action",
        session_id=session_id,
    )
    res2 = agent.chat(req_answer)
    assert res2.needs_clarification is False
    assert len(res2.recommendations) > 0
    assert len(res2.tool_calls_executed) > 0
    assert res2.grounding_verified is True

    # Check 100% metadata grounding
    for rec in res2.recommendations:
        catalog_movie = next((m for m in container.catalog.movies if m.id == rec.id), None)
        assert catalog_movie is not None
        assert rec.title == catalog_movie.canonical_title
