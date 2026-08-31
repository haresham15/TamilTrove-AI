from __future__ import annotations

from conftest import register_user
from fastapi.testclient import TestClient


def test_multilingual_hybrid_search_filters_pagination_and_debug(client: TestClient) -> None:
    response = client.post(
        "/api/v1/search",
        json={
            "query": "கிராமத்து குடும்பம்",
            "filters": {"year_min": 2017, "year_max": 2019, "genres": ["drama"]},
            "page": 1,
            "page_size": 5,
            "diversity": 0,
            "include_debug": True,
        },
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["detected_language"] == "tamil"
    assert [result["title"] for result in body["results"]] == ["Village Skies"]
    assert body["meta"]["total"] == 1
    assert body["meta"]["total_pages"] == 1
    assert body["meta"]["stage_timings_ms"]["total"] >= 0
    result = body["results"][0]
    assert result["scores"]["final"] == result["final_score"]
    assert result["explanation"]["summary"]
    assert result["debug"]["semantic_backend"] == "multilingual-character-fallback"

    zero = client.post(
        "/api/v1/search",
        json={"query": "crime", "filters": {"year_min": 1990, "year_max": 1991}},
    )
    assert zero.status_code == 200
    assert zero.json()["results"] == []
    assert zero.json()["meta"]["total_pages"] == 0


def test_movie_detail_similar_and_missing_movie(client: TestClient) -> None:
    movie_id = "11111111-1111-4111-8111-111111111111"
    detail = client.get(f"/api/v1/movies/{movie_id}")
    assert detail.status_code == 200
    assert detail.json()["id"] == movie_id
    assert detail.json()["provenance"]["source_system"] == "legacy_dataset"

    similar = client.get(f"/api/v1/movies/{movie_id}/similar?page_size=3")
    assert similar.status_code == 200, similar.text
    assert all(movie["id"] != movie_id for movie in similar.json()["results"])
    assert len(similar.json()["results"]) <= 3

    missing = client.get("/api/v1/movies/00000000-0000-4000-8000-000000000000")
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "not_found"


def test_search_history_respects_privacy_setting(client: TestClient) -> None:
    _, headers = register_user(client, email="history@example.com")
    assert (
        client.post("/api/v1/search", headers=headers, json={"query": "crime"}).status_code == 200
    )
    history = client.get("/api/v1/history/search", headers=headers)
    assert history.json()["total"] == 1
    assert history.json()["items"][0]["query_text"] == "crime"

    profile = client.get("/api/v1/profile", headers=headers).json()
    privacy = {**profile["privacy"], "store_search_history": False}
    assert (
        client.patch("/api/v1/profile", headers=headers, json={"privacy": privacy}).status_code
        == 200
    )
    assert (
        client.post("/api/v1/search", headers=headers, json={"query": "comedy"}).status_code == 200
    )
    assert client.get("/api/v1/history/search", headers=headers).json()["total"] == 1

    assert client.delete("/api/v1/history/search", headers=headers).status_code == 204
    assert client.get("/api/v1/history/search", headers=headers).json()["total"] == 0


def test_recommendations_require_authentication_and_return_explanations(client: TestClient) -> None:
    client.cookies.clear()
    assert client.get("/api/v1/recommendations").status_code == 401

    _, headers = register_user(client, email="recommend@example.com")
    response = client.get(
        "/api/v1/recommendations?surface=hidden_gems&page_size=3", headers=headers
    )
    assert response.status_code == 200, response.text
    assert response.json()["meta"]["personalized"] is True
    assert len(response.json()["results"]) == 3
    assert all(result["explanation"]["summary"] for result in response.json()["results"])
