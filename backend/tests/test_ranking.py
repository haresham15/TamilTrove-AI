from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from app.catalog import Catalog
from app.config import Settings
from app.normalization import normalize_query
from app.ranking import (
    SearchIndex,
    UserSignals,
    hidden_gem_score,
    mmr_rerank,
    phrase_in_query,
    reciprocal_rank_fusion,
)
from app.schemas import SearchFilters, SearchRequest


@pytest.fixture
def index(
    tmp_path: Path,
    movie_records: list[dict[str, object]],
) -> SearchIndex:
    path = tmp_path / "movies.json"
    path.write_text(json.dumps(movie_records), encoding="utf-8")
    catalog = Catalog.load(path)
    return SearchIndex(catalog, Settings(environment="test", enable_transformer=False))


def test_reciprocal_rank_fusion_is_shape_safe_and_weighted() -> None:
    semantic = np.array([1.0, 0.1, 0.2])
    lexical = np.array([0.0, 1.0, 0.2])

    fused = reciprocal_rank_fusion(semantic, lexical, semantic_weight=0.8, lexical_weight=0.2)
    assert fused.shape == semantic.shape
    # Agreement across both ranked lists beats an item that is first in the
    # lower-weight list but last in the semantic-heavy list.
    assert fused[0] > fused[2] > fused[1]
    assert fused.max() == pytest.approx(1.0)
    with pytest.raises(ValueError, match="same shape"):
        reciprocal_rank_fusion(semantic, lexical[:2], 0.5, 0.5)


def test_boundary_phrase_matching_does_not_boost_one_character_titles() -> None:
    assert phrase_in_query("i", "i am searching")
    assert not phrase_in_query("i", "political thriller")
    assert phrase_in_query("maya ravi", "films with maya ravi")
    assert not phrase_in_query("maya ravi", "mayar avian")


def test_hidden_gem_score_rewards_relevant_low_prominence_titles() -> None:
    assert hidden_gem_score(0.1, 0.8, 1.0) > hidden_gem_score(0.9, 0.8, 1.0)
    assert hidden_gem_score(0.1, -0.5, 1.0) == 0


def test_multilingual_rank_filters_and_grounded_explanations(index: SearchIndex) -> None:
    request = SearchRequest(
        query="கிராமத்து குடும்பம்",
        filters=SearchFilters(year_min=2017, year_max=2019, genres=["drama"]),
        diversity=0,
    )
    ranked, hints, coordinates = index.rank(normalize_query(request.query), request)

    assert [item.movie.title for item in ranked] == ["Village Skies"]
    assert ranked[0].final >= 0
    assert hints["genres"] == ["family"]
    assert all(value is None or -1 <= value <= 1 for value in coordinates)


def test_dismissed_watched_and_personal_preferences_affect_results(index: SearchIndex) -> None:
    village_id = "22222222-2222-4222-8222-222222222222"
    court_id = "33333333-3333-4333-8333-333333333333"
    signals = UserSignals(
        favorite_genres=("drama",),
        favorite_themes=("family",),
        dismissed_movie_ids=(village_id,),
        watched_movie_ids=(court_id,),
    )
    request = SearchRequest(
        query="family drama",
        filters=SearchFilters(exclude_dismissed=True, exclude_watched=True),
        diversity=0,
    )

    ranked, _, _ = index.rank(normalize_query(request.query), request, signals)
    ids = {item.movie.id for item in ranked}
    assert village_id not in ids
    assert court_id not in ids
    assert any(item.preference > 0 for item in ranked)


def test_database_candidate_provider_bounds_local_reranking(index: SearchIndex) -> None:
    only_id = "11111111-1111-4111-8111-111111111111"
    calls: list[tuple[str, tuple[int, ...], int]] = []

    def candidates(query: str, vector: np.ndarray, limit: int) -> dict[str, tuple[float, float]]:
        calls.append((query, vector.shape, limit))
        return {only_id: (0.9, 0.7)}

    request = SearchRequest(query="crime thriller", diversity=0)
    ranked, _, _ = index.rank(
        normalize_query(request.query), request, candidate_provider=candidates
    )

    assert [item.movie.id for item in ranked] == [only_id]
    assert calls
    assert calls[0][1] == (384,)


def test_mmr_handles_empty_and_zero_limit() -> None:
    assert mmr_rerank([], diversity=0.5, limit=10) == []
    assert mmr_rerank([], diversity=0.5, limit=0) == []
