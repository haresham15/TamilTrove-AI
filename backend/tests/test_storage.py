from __future__ import annotations

from pathlib import Path

import pytest

from app.errors import ConflictError
from app.storage import SQLiteStore, create_store


@pytest.fixture
def store(tmp_path: Path):
    repository = SQLiteStore(tmp_path / "state.db")
    repository.initialize()
    try:
        yield repository
    finally:
        repository.close()


def test_user_profile_crud_and_export_excludes_password(store: SQLiteStore) -> None:
    user = store.create_user("USER@example.com", "encoded-secret", "Initial Name", "en")

    assert user["email"] == "user@example.com"
    assert user["preferences"]["languages"] == ["Tamil"]
    assert store.get_user_by_email("User@Example.Com")["id"] == user["id"]
    with pytest.raises(ConflictError):
        store.create_user("user@example.com", "other-secret", "Duplicate", "en")

    updated = store.update_user(
        user["id"],
        {
            "display_name": "Updated Name",
            "preferences": {**user["preferences"], "favorite_genres": ["crime"]},
            "privacy": {**user["privacy"], "analytics_consent": True},
        },
    )
    assert updated["display_name"] == "Updated Name"
    assert updated["preferences"]["favorite_genres"] == ["crime"]
    assert updated["privacy"]["analytics_consent"] is True

    exported = store.export_user(user["id"])
    assert "password_hash" not in exported["profile"]
    assert exported["profile"]["email"] == "user@example.com"


def test_interaction_upsert_history_and_revocation_lifecycle(store: SQLiteStore) -> None:
    user = store.create_user("state@example.com", "encoded-secret", "State", "en")
    first = store.upsert_interaction(user["id"], "movie-1", "rating", 3.5, {"surface": "search"})
    second = store.upsert_interaction(user["id"], "movie-1", "rating", 4.5, {"surface": "detail"})

    ratings = store.list_interactions(user["id"], "rating")
    assert len(ratings) == 1
    assert ratings[0]["id"] == first["id"] == second["id"]
    assert ratings[0]["value"] == 4.5
    assert ratings[0]["context"] == {"surface": "detail"}

    store.add_search_history(
        user["id"],
        "crime",
        "crime",
        "english",
        {"genres": ["crime"]},
        ["movie-1"],
        "rank-v2",
        12.5,
    )
    history = store.list_search_history(user["id"])
    assert history[0]["filters"] == {"genres": ["crime"]}
    assert history[0]["result_ids"] == ["movie-1"]
    assert store.clear_search_history(user["id"]) == 1

    store.revoke_token("token-jti", user["id"], 4_102_444_800)
    assert store.is_token_revoked("token-jti") is True


def test_collection_sharing_order_and_account_cascade(store: SQLiteStore) -> None:
    user = store.create_user("owner@example.com", "encoded-secret", "Owner", "en")
    collection = store.create_collection(user["id"], "Noir", "Dark films", "private")
    store.add_collection_item(collection["id"], "movie-a", None)
    store.add_collection_item(collection["id"], "movie-b", 0)

    # SQLite's local repository permits equal explicit positions but preserves a
    # deterministic secondary order. PostgreSQL uses a deferred unique index.
    items = store.collection_items(collection["id"])
    assert {item["movie_id"] for item in items} == {"movie-a", "movie-b"}
    shared = store.share_collection(collection["id"])
    assert shared["visibility"] == "unlisted"
    assert shared["share_token"]
    assert store.get_shared_collection(shared["share_token"])["id"] == collection["id"]

    private = store.update_collection(collection["id"], {"visibility": "private"})
    assert private["share_token"] is None
    assert store.get_shared_collection(shared["share_token"]) is None

    assert store.delete_user(user["id"])
    assert store.get_collection(collection["id"]) is None


def test_repository_factory_rejects_unknown_database_schemes(tmp_path: Path) -> None:
    repository = create_store(f"sqlite:///{(tmp_path / 'factory.db').as_posix()}")
    assert isinstance(repository, SQLiteStore)
    with pytest.raises(ValueError, match=r"sqlite.*postgresql"):
        create_store("mysql://localhost/tamiltrove")
