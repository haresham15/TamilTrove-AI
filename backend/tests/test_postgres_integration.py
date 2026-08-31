from __future__ import annotations

import json
import os
import uuid
from pathlib import Path

import pytest

from app.catalog import Catalog
from app.config import Settings
from app.postgres import PostgresStore
from app.ranking import SearchIndex

pytestmark = pytest.mark.postgres


@pytest.fixture
def postgres_url() -> str:
    value = os.getenv("TAMILTROVE_TEST_POSTGRES_URL")
    if not value:
        pytest.skip("TAMILTROVE_TEST_POSTGRES_URL is not configured")
    return value


@pytest.fixture
def postgres_store(postgres_url: str):
    store = PostgresStore(postgres_url)
    store.initialize()
    try:
        yield store
    finally:
        store.close()


def test_migration_catalog_sync_hybrid_retrieval_and_user_state(
    postgres_store: PostgresStore,
    tmp_path: Path,
    movie_records: list[dict[str, object]],
) -> None:
    # Use a unique catalog version and identities so reruns against a developer's
    # explicitly supplied test database remain idempotent and isolated.
    suffix = uuid.uuid4().hex[:10]
    records = []
    for record in movie_records:
        value = dict(record)
        value["id"] = str(uuid.uuid4())
        value["title"] = f"{value['title']} {suffix}"
        records.append(value)
    data_path = tmp_path / f"postgres-{suffix}.json"
    data_path.write_text(json.dumps(records), encoding="utf-8")
    catalog = Catalog.load(data_path)
    index = SearchIndex(catalog, Settings(environment="test", enable_transformer=False))

    report = postgres_store.sync_catalog(
        catalog,
        index.semantic_backend,
        "integration-test",
        index.dense_embeddings(),
    )
    second_report = postgres_store.sync_catalog(
        catalog,
        index.semantic_backend,
        "integration-test",
        index.dense_embeddings(),
    )
    assert report["movie_count"] == len(records)
    assert report["embedding_count"] == len(records)
    assert second_report == report
    assert postgres_store.ping()

    _, query_vector = index.encode_query("crime thriller")
    candidates = postgres_store.hybrid_candidates("crime thriller", query_vector, 3)
    assert 1 <= len(candidates) <= 3
    assert set(candidates) <= {movie.id for movie in catalog.movies}
    assert all(0 <= semantic <= 1 and lexical >= 0 for semantic, lexical in candidates.values())

    email = f"integration-{suffix}@example.com"
    user = postgres_store.create_user(email, "x" * 32, "Integration User", "en")
    try:
        movie_id = catalog.movies[0].id
        interaction = postgres_store.upsert_interaction(
            user["id"], movie_id, "rating", 4.5, {"source": "integration-test"}
        )
        assert interaction["type"] == "rating"
        assert postgres_store.list_interactions(user["id"], "rating")[0]["value"] == 4.5

        collection = postgres_store.create_collection(
            user["id"], "Integration Collection", "", "private"
        )
        postgres_store.add_collection_item(collection["id"], movie_id, None)
        assert postgres_store.collection_items(collection["id"])[0]["movie_id"] == movie_id
        shared = postgres_store.share_collection(collection["id"])
        assert postgres_store.get_shared_collection(shared["share_token"])["id"] == collection["id"]
    finally:
        postgres_store.delete_user(user["id"])


def test_hybrid_retrieval_rejects_invalid_vectors(postgres_store: PostgresStore) -> None:
    with pytest.raises(ValueError, match="384 finite"):
        postgres_store.hybrid_candidates("crime", [0.1, 0.2], 10)
    with pytest.raises(ValueError, match="non-zero"):
        postgres_store.hybrid_candidates("crime", [0.0] * 384, 10)
