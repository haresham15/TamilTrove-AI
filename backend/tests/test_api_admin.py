from __future__ import annotations

from conftest import register_user
from fastapi.testclient import TestClient


def valid_ingestion_body(*, dry_run: bool = True) -> dict[str, object]:
    return {
        "dry_run": dry_run,
        "transformation_version": "api-test-v1",
        "records": [
            {
                "source_system": "test_source",
                "source_identifier": "new-film-1",
                "confidence": 0.9,
                "movie": {
                    "title": "Ingested Film",
                    "release_year": 2025,
                    "runtime_minutes": 120,
                    "language": "ta",
                    "overview": (
                        "A complete and factual synopsis with enough detail for the ingestion validation "
                        "pipeline to accept this new movie record."
                    ),
                },
            }
        ],
    }


def test_admin_role_enforcement_quality_and_experiment_metadata(client: TestClient) -> None:
    _, normal_headers = register_user(client, email="normal@example.com")
    denied = client.get("/api/v1/admin/data-quality", headers=normal_headers)
    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "permission_denied"

    _, admin_headers = register_user(client, email="admin@example.com", display_name="Admin")
    quality = client.get("/api/v1/admin/data-quality", headers=admin_headers)
    assert quality.status_code == 200
    assert quality.json()["accepted_records"] == 6
    assert quality.json()["quality_distribution"] == {"validated": 6}
    assert quality.json()["semantic_backend"] == "multilingual-character-fallback"

    experiments = client.get("/api/v1/admin/experiments", headers=admin_headers)
    assert experiments.status_code == 200
    assert experiments.json()["feature_flags"]["personalization"] is True
    assert 0 < experiments.json()["weights"]["semantic"] < 1


def test_admin_ingestion_validation_dry_run_and_dataset_registry(client: TestClient) -> None:
    _, headers = register_user(client, email="admin@example.com", display_name="Admin")
    body = valid_ingestion_body()

    validated = client.post("/api/v1/admin/ingestion/validate", headers=headers, json=body)
    assert validated.status_code == 200, validated.text
    assert validated.json()["accepted_count"] == 1
    assert validated.json()["quarantined_count"] == 0

    run = client.post("/api/v1/admin/ingestion/run", headers=headers, json=body)
    assert run.status_code == 200, run.text
    assert run.json()["status"] == "completed"
    assert run.json()["dry_run"] is True
    assert run.json()["report"]["requires_promotion"] is False

    versions = client.get("/api/v1/admin/dataset/versions", headers=headers)
    assert versions.status_code == 200
    assert len(versions.json()["items"]) == 1
    assert versions.json()["items"][0]["status"] == "validated"


def test_admin_ingestion_quarantines_invalid_metadata(client: TestClient) -> None:
    _, headers = register_user(client, email="admin@example.com", display_name="Admin")
    body = valid_ingestion_body()
    body["records"][0]["movie"]["overview"] = "too short"
    body["records"][0]["movie"]["poster_url"] = "http://example.com/poster.jpg"

    response = client.post("/api/v1/admin/ingestion/validate", headers=headers, json=body)
    assert response.status_code == 200
    assert response.json()["accepted_count"] == 0
    assert response.json()["quarantined_count"] == 1
    reasons = response.json()["quarantined"][0]["reasons"]
    assert "overview_too_short" in reasons
    assert "poster_must_use_https" in reasons
