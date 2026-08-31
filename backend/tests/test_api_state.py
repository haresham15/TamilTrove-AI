from __future__ import annotations

from conftest import register_user
from fastapi.testclient import TestClient

MOVIE_ID = "11111111-1111-4111-8111-111111111111"
SECOND_MOVIE_ID = "22222222-2222-4222-8222-222222222222"


def test_ratings_watchlist_dismissal_and_profile_reset(client: TestClient) -> None:
    _, headers = register_user(client, email="feedback@example.com")

    bad_step = client.post(
        "/api/v1/interactions",
        headers=headers,
        json={"movie_id": MOVIE_ID, "type": "rating", "value": 4.25},
    )
    assert bad_step.status_code == 422
    missing = client.post(
        "/api/v1/interactions",
        headers=headers,
        json={"movie_id": "missing", "type": "like"},
    )
    assert missing.status_code == 404

    rating = client.post(
        "/api/v1/interactions",
        headers=headers,
        json={
            "movie_id": MOVIE_ID,
            "type": "rating",
            "value": 4.5,
            "context": {"surface": "detail"},
        },
    )
    assert rating.status_code == 201
    assert rating.json()["value"] == 4.5

    saved = client.put(f"/api/v1/watchlist/{MOVIE_ID}", headers=headers)
    assert saved.status_code == 200
    watchlist = client.get("/api/v1/watchlist", headers=headers).json()
    assert watchlist["total"] == 1
    assert watchlist["items"][0]["user_state"] == {"rating": 4.5, "in_watchlist": True}

    dismissed = client.post(
        "/api/v1/interactions",
        headers=headers,
        json={
            "movie_id": SECOND_MOVIE_ID,
            "type": "dismiss",
            "context": {"surface": "recommendations"},
        },
    )
    assert dismissed.status_code == 201
    search = client.post("/api/v1/search", headers=headers, json={"query": "family drama"}).json()
    assert SECOND_MOVIE_ID not in {movie["id"] for movie in search["results"]}

    interactions = client.get("/api/v1/interactions?page_size=20", headers=headers).json()
    assert {item["type"] for item in interactions["items"]} == {"rating", "save", "dismiss"}
    assert client.delete(f"/api/v1/watchlist/{MOVIE_ID}", headers=headers).status_code == 204
    assert client.get("/api/v1/watchlist", headers=headers).json()["total"] == 0

    reset = client.patch("/api/v1/profile", headers=headers, json={"reset_interactions": True})
    assert reset.status_code == 200
    assert client.get("/api/v1/interactions", headers=headers).json()["items"] == []


def test_collection_ownership_visibility_sharing_and_items(client: TestClient) -> None:
    _, owner_headers = register_user(client, email="owner@example.com", display_name="Owner")
    created = client.post(
        "/api/v1/collections",
        headers=owner_headers,
        json={"name": "Night films", "description": "A private list", "visibility": "private"},
    )
    assert created.status_code == 201, created.text
    collection_id = created.json()["id"]

    added = client.post(
        f"/api/v1/collections/{collection_id}/items",
        headers=owner_headers,
        json={"movie_id": MOVIE_ID},
    )
    assert added.status_code == 200
    assert added.json()["item_count"] == 1
    assert added.json()["items"][0]["movie"]["id"] == MOVIE_ID

    shared = client.post(f"/api/v1/collections/{collection_id}/share", headers=owner_headers)
    assert shared.status_code == 200
    token = shared.json()["share_token"]
    assert shared.json()["visibility"] == "unlisted"

    _, other_headers = register_user(client, email="other@example.com", display_name="Other")
    hidden = client.get(f"/api/v1/collections/{collection_id}", headers=other_headers)
    assert hidden.status_code == 404
    public_share = client.get(f"/api/v1/collections/shared/{token}")
    assert public_share.status_code == 200
    assert public_share.json()["owner_id"] is None
    assert public_share.json()["share_token"] is None
    assert public_share.json()["owner_display_name"] == "Owner"

    forbidden = client.patch(
        f"/api/v1/collections/{collection_id}",
        headers=other_headers,
        json={"name": "Stolen"},
    )
    assert forbidden.status_code == 403

    made_public = client.patch(
        f"/api/v1/collections/{collection_id}",
        headers=owner_headers,
        json={"visibility": "public"},
    )
    assert made_public.status_code == 200
    visible = client.get(f"/api/v1/collections/{collection_id}", headers=other_headers)
    assert visible.status_code == 200
    assert visible.json()["owner_id"] is None

    removed = client.delete(
        f"/api/v1/collections/{collection_id}/items/{MOVIE_ID}", headers=owner_headers
    )
    assert removed.status_code == 200
    assert removed.json()["item_count"] == 0
    assert (
        client.delete(f"/api/v1/collections/{collection_id}", headers=owner_headers).status_code
        == 204
    )
    assert (
        client.get(f"/api/v1/collections/{collection_id}", headers=owner_headers).status_code == 404
    )


def test_non_owner_cannot_delete_or_add_collection_items(client: TestClient) -> None:
    _, owner_headers = register_user(client, email="first@example.com")
    collection = client.post(
        "/api/v1/collections",
        headers=owner_headers,
        json={"name": "Owned", "visibility": "public"},
    ).json()
    _, other_headers = register_user(client, email="second@example.com")

    add = client.post(
        f"/api/v1/collections/{collection['id']}/items",
        headers=other_headers,
        json={"movie_id": MOVIE_ID},
    )
    assert add.status_code == 403
    assert (
        client.delete(f"/api/v1/collections/{collection['id']}", headers=other_headers).status_code
        == 403
    )
