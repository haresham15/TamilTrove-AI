from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.config import Settings
from main import create_app


def test_health_readiness_metrics_and_openapi(client: TestClient) -> None:
    health = client.get("/health", headers={"X-Request-ID": "test.request-1"})
    assert health.status_code == 200
    assert health.json()["status"] == "ok"
    assert health.headers["X-Request-ID"] == "test.request-1"

    ready = client.get("/ready")
    assert ready.status_code == 200
    assert ready.json()["checks"] == {"database": True, "catalog": True, "ranking": True}

    client.post("/api/v1/search", json={"query": "crime"})
    metrics = client.get("/metrics")
    assert metrics.status_code == 200
    assert metrics.headers["content-type"].startswith("text/plain")
    assert "tamiltrove_ready 1" in metrics.text
    assert "tamiltrove_search_requests_total" in metrics.text
    assert "tamiltrove_http_request_duration_seconds_bucket" in metrics.text

    schema = client.get("/openapi.json").json()
    assert schema["info"]["version"] == "2.0.0"
    assert "/api/v1/search" in schema["paths"]
    assert "/api/v1/collections/{collection_id}" in schema["paths"]


def test_invalid_request_id_is_replaced_and_validation_uses_error_envelope(
    client: TestClient,
) -> None:
    response = client.post(
        "/api/v1/search",
        headers={"X-Request-ID": "invalid request id with spaces"},
        json={"query": "crime", "unexpected": True},
    )

    assert response.status_code == 422
    assert response.headers["X-Request-ID"] != "invalid request id with spaces"
    body = response.json()["error"]
    assert body["code"] == "validation_error"
    assert body["request_id"] == response.headers["X-Request-ID"]
    assert body["details"][0]["location"][-1] == "unexpected"


def test_request_size_and_rate_limits_are_enforced(app_settings: Settings) -> None:
    constrained = Settings(
        **{
            field: getattr(app_settings, field)
            for field in app_settings.__dataclass_fields__
            if field not in {"max_request_bytes", "rate_limit_requests"}
        },
        max_request_bytes=1_024,
        rate_limit_requests=2,
    )
    with TestClient(create_app(constrained), base_url="http://testserver") as limited:
        oversized = limited.post("/api/v1/search", json={"query": "x" * 2_000})
        assert oversized.status_code == 413
        assert oversized.json()["error"]["code"] == "request_too_large"

        assert limited.post("/api/v1/search", json={"query": "one"}).status_code == 200
        assert limited.post("/api/v1/search", json={"query": "two"}).status_code == 200
        blocked = limited.post("/api/v1/search", json={"query": "three"})
        assert blocked.status_code == 429
        assert blocked.headers["Retry-After"]
        assert blocked.json()["error"]["code"] == "rate_limited"


def test_health_stays_live_when_startup_dependency_fails(tmp_path: Path) -> None:
    settings = Settings(
        environment="test",
        database_url=f"sqlite:///{(tmp_path / 'state.db').as_posix()}",
        data_path=tmp_path / "missing.json",
        embeddings_path=tmp_path / "missing.npy",
        secret_key="test-signing-key-that-is-longer-than-thirty-two-bytes",
        allowed_origins=("http://testserver",),
    )
    with TestClient(create_app(settings), base_url="http://testserver") as unavailable:
        assert unavailable.get("/health").status_code == 200
        readiness = unavailable.get("/ready")
        assert readiness.status_code == 503
        assert readiness.json()["ready"] is False
        search = unavailable.post("/api/v1/search", json={"query": "crime"})
        assert search.status_code == 503
        assert search.json()["error"]["code"] == "service_unavailable"
