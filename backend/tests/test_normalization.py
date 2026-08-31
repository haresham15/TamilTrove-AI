from __future__ import annotations

import pytest

from app.normalization import detect_language, normalize_query, normalize_text, parse_query_hints
from app.schemas import InteractionRequest, SearchFilters


@pytest.mark.parametrize(
    ("query", "language"),
    [
        ("courtroom thriller", "english"),
        ("காதல் குடும்பம்", "tamil"),
        ("kadhal padam", "tanglish"),
        ("காதல் movie", "mixed"),
    ],
)
def test_detect_language_slices(query: str, language: str) -> None:
    assert detect_language(query) == language


def test_query_normalization_preserves_names_and_expands_domain_terms() -> None:
    normalized = normalize_query("  KADHAL   padam  ")

    assert normalized.original == "KADHAL   padam"
    assert normalized.detected_language == "tanglish"
    assert normalized.normalized.startswith("kadhal padam")
    assert {"love", "romance", "movie", "film"} <= set(normalized.expanded_terms)
    assert normalize_text("  Café\u200b—TEST ") == "café test"


def test_tamil_query_expands_to_searchable_english_evidence() -> None:
    normalized = normalize_query("கிராமத்து குடும்பம்")

    assert normalized.detected_language == "tamil"
    assert {"village", "rural", "family"} <= set(normalized.expanded_terms)


def test_query_hints_only_extract_explicit_constraints() -> None:
    assert parse_query_hints("political thriller after 2018") == {
        "year_min": 2018,
        "genres": ["political", "thriller"],
    }
    assert parse_query_hints("1990s comedy before 1998") == {
        "year_min": 1990,
        "year_max": 1998,
        "genres": ["comedy"],
    }


def test_schema_rejects_inverted_ranges_and_invalid_rating_steps() -> None:
    with pytest.raises(ValueError, match="year_min"):
        SearchFilters(year_min=2020, year_max=2010)
    with pytest.raises(ValueError, match="half-star"):
        InteractionRequest(movie_id="movie", type="rating", value=4.25)

    rating = InteractionRequest(movie_id="movie", type="rating", value=4.5)
    assert rating.value == 4.5
