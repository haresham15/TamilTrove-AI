from __future__ import annotations

from pathlib import Path

from app.ingestion import IngestionService, identity_similarity


def envelope(identifier: str, **movie: object) -> dict[str, object]:
    return {
        "source_system": "test_source",
        "source_identifier": identifier,
        "confidence": 0.95,
        "movie": movie,
    }


def test_identity_similarity_prioritizes_external_ids_and_evidence() -> None:
    assert identity_similarity({"external_id": "tt-1"}, {"source_identifier": "tt-1"}) == 1
    close = identity_similarity(
        {"title": "Example", "release_year": 2020, "director": "A", "cast": "One Two"},
        {"title": "Example", "release_year": 2020, "director": "A", "cast": "Two Three"},
    )
    conflict = identity_similarity(
        {"title": "Example", "release_year": 2020},
        {"title": "Example", "release_year": 2023},
    )
    assert close > 0.9
    assert conflict < close
    assert identity_similarity({"title": "One"}, {"title": "Two"}) == 0


def test_ingestion_quarantines_bad_records_and_warns_on_unknown_host(tmp_path: Path) -> None:
    service = IngestionService(("image.tmdb.org",), tmp_path / "versions")
    good = envelope(
        "good-1",
        title="A Valid Film",
        release_year=2024,
        runtime_minutes=120,
        overview="A sufficiently detailed and factual movie synopsis that passes the minimum validation length.",
        language="ta",
        poster_url="https://image.tmdb.org/poster.jpg",
    )
    duplicate = envelope(
        "bad-1",
        title="A Valid Film",
        release_year=2024,
        runtime_minutes=10,
        overview="was born and is an actor",
        language="ta",
        poster_url="http://unknown.example/poster.jpg",
    )
    unknown_host = envelope(
        "warning-1",
        title="Another Film",
        release_year=2022,
        runtime_minutes=100,
        overview="A complete synopsis about a family journey with enough detail to be accepted by validation.",
        language="ta",
        poster_url="https://cdn.example/poster.jpg",
    )

    outcome = service.validate([good, duplicate, unknown_host], "test-transform-v1")

    assert len(outcome.accepted) == 2
    assert len(outcome.quarantined) == 1
    reasons = set(outcome.quarantined[0]["reasons"])
    assert {
        "runtime_out_of_range",
        "overview_too_short",
        "overview_appears_biographical",
    } <= reasons
    assert "duplicate_title_year_language" in reasons
    assert outcome.warnings == [
        {"index": 2, "code": "untrusted_poster_host", "host": "cdn.example"}
    ]


def test_ingestion_write_is_content_addressed_and_idempotent(tmp_path: Path) -> None:
    service = IngestionService((), tmp_path / "versions")
    record = envelope(
        "movie-1",
        title="Stable Film",
        release_year=2021,
        runtime_minutes=110,
        overview="A complete synopsis with enough detail to pass validation and produce a stable content digest.",
        language="ta",
    )

    dry_run = service.run([record], "test-transform-v1", dry_run=True)
    first = service.run([record], "test-transform-v1", dry_run=False)
    second = service.run([record], "test-transform-v1", dry_run=False)

    assert dry_run["output_path"] is None
    assert first["content_hash"] == dry_run["content_hash"] == second["content_hash"]
    assert first["output_path"] == second["output_path"]
    assert first["idempotent"] is True
    assert Path(first["output_path"]).is_file()
