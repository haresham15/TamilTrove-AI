from __future__ import annotations

import json
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.config import Settings  # noqa: E402
from main import create_app  # noqa: E402


@pytest.fixture
def movie_records() -> list[dict[str, Any]]:
    return [
        {
            "id": "11111111-1111-4111-8111-111111111111",
            "title": "Midnight Patrol",
            "release_year": 2022,
            "runtime_minutes": 118,
            "certificate": "UA",
            "overview": (
                "During a single night in Chennai, an honest police officer pursues a crime ring "
                "while protecting a frightened witness and confronting corruption inside the force."
            ),
            "language": "ta",
            "genres": ["crime", "thriller"],
            "themes": ["one-night", "chase", "crime"],
            "director": "Arun Kumar",
            "cast": ["Maya Ravi", "Kavin Raj"],
            "poster_url": "https://image.tmdb.org/t/p/w500/midnight.jpg",
            "prominence_score": 0.78,
            "data_quality_status": "validated",
        },
        {
            "id": "22222222-2222-4222-8222-222222222222",
            "title": "Village Skies",
            "release_year": 2018,
            "runtime_minutes": 132,
            "certificate": "U",
            "overview": (
                "A farmer and her estranged brother return to their Tamil village, rebuild a family "
                "home, and rediscover friendship while resisting a powerful developer."
            ),
            "language": "ta",
            "genres": ["drama", "family"],
            "themes": ["village", "family", "friendship"],
            "director": "Meena Selvan",
            "cast": ["Anu Devi", "Surya Das"],
            "poster_url": "https://image.tmdb.org/t/p/w500/village.jpg",
            "prominence_score": 0.25,
            "data_quality_status": "validated",
        },
        {
            "id": "33333333-3333-4333-8333-333333333333",
            "title": "Court of Truth",
            "release_year": 2020,
            "runtime_minutes": 144,
            "certificate": "U",
            "overview": (
                "A determined lawyer challenges a wrongful conviction in a tense courtroom drama, "
                "using overlooked evidence to expose injustice and restore a family name."
            ),
            "language": "ta",
            "genres": ["drama"],
            "themes": ["courtroom", "family"],
            "director": "Ravi Chandran",
            "cast": ["Leela Mani", "Vijay Arun"],
            "poster_url": "https://image.tmdb.org/t/p/w500/court.jpg",
            "prominence_score": 0.55,
            "data_quality_status": "validated",
        },
        {
            "id": "44444444-4444-4444-8444-444444444444",
            "title": "Ghost Wedding",
            "release_year": 2019,
            "runtime_minutes": 105,
            "certificate": "UA",
            "overview": (
                "A chaotic wedding party discovers a playful ghost in an old mansion, turning a "
                "family celebration into a warm supernatural comedy about grief and reconciliation."
            ),
            "language": "ta",
            "genres": ["comedy", "horror"],
            "themes": ["family"],
            "director": "Priya Mani",
            "cast": ["Nila Ram", "Hari Siva"],
            "poster_url": "https://image.tmdb.org/t/p/w500/ghost.jpg",
            "prominence_score": 0.46,
            "data_quality_status": "validated",
        },
        {
            "id": "55555555-5555-4555-8555-555555555555",
            "title": "Red Earth",
            "release_year": 2016,
            "runtime_minutes": 126,
            "certificate": "UA",
            "overview": (
                "After leaving prison, a quiet mechanic returns home to seek revenge against the "
                "gangster who framed him, but friendship offers a different path toward justice."
            ),
            "language": "ta",
            "genres": ["action", "crime"],
            "themes": ["revenge", "prison", "friendship"],
            "director": "Bala Naren",
            "cast": ["Karthi Dev", "Maya Ravi"],
            "poster_url": "https://image.tmdb.org/t/p/w500/red-earth.jpg",
            "prominence_score": 0.18,
            "data_quality_status": "validated",
        },
        {
            "id": "66666666-6666-4666-8666-666666666666",
            "title": "Ballot Box",
            "release_year": 2024,
            "runtime_minutes": 136,
            "certificate": "UA",
            "overview": (
                "An idealistic teacher enters a local election and uncovers a political conspiracy, "
                "forcing her community to decide whether courage can defeat entrenched corruption."
            ),
            "language": "ta",
            "genres": ["political", "thriller"],
            "themes": ["politics", "village"],
            "director": "Jaya Vel",
            "cast": ["Nila Ram", "Rohan Jay"],
            "poster_url": "https://image.tmdb.org/t/p/w500/ballot.jpg",
            "prominence_score": 0.68,
            "data_quality_status": "validated",
        },
    ]


@pytest.fixture
def app_settings(tmp_path: Path, movie_records: list[dict[str, Any]]) -> Settings:
    data_path = tmp_path / "movies.json"
    data_path.write_text(json.dumps(movie_records, ensure_ascii=False), encoding="utf-8")
    return Settings(
        environment="test",
        database_url=f"sqlite:///{(tmp_path / 'state.db').as_posix()}",
        data_path=data_path,
        embeddings_path=tmp_path / "missing-embeddings.npy",
        secret_key="test-signing-key-that-is-longer-than-thirty-two-bytes",
        allowed_origins=("http://testserver",),
        admin_emails=("admin@example.com",),
        enable_transformer=False,
        debug_scores=True,
        rate_limit_requests=1_000,
    )


@pytest.fixture
def client(app_settings: Settings) -> Iterator[TestClient]:
    with TestClient(create_app(app_settings), base_url="http://testserver") as test_client:
        assert test_client.app.state.startup_error is None
        yield test_client


def register_user(
    client: TestClient,
    *,
    email: str = "viewer@example.com",
    password: str = "StrongPass123!",
    display_name: str = "Viewer",
) -> tuple[dict[str, Any], dict[str, str]]:
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": password,
            "display_name": display_name,
            "locale": "en",
        },
    )
    assert response.status_code == 201, response.text
    payload = response.json()
    return payload, {"Authorization": f"Bearer {payload['access_token']}"}
