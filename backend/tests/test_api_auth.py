from __future__ import annotations

from conftest import register_user
from fastapi.testclient import TestClient


def test_register_login_profile_export_logout_and_revocation(client: TestClient) -> None:
    payload, headers = register_user(client)

    assert payload["token_type"] == "bearer"
    assert payload["expires_in"] == 3_600
    assert payload["profile"]["email"] == "viewer@example.com"
    assert "password" not in str(payload).casefold()
    assert (
        "httponly"
        in client.post(
            "/api/v1/auth/login",
            json={"email": "viewer@example.com", "password": "StrongPass123!"},
        )
        .headers["set-cookie"]
        .casefold()
    )

    duplicate = client.post(
        "/api/v1/auth/register",
        json={
            "email": "VIEWER@example.com",
            "password": "AnotherStrong42!",
            "display_name": "Duplicate",
            "locale": "en",
        },
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "conflict"

    bad_login = client.post(
        "/api/v1/auth/login",
        json={"email": "viewer@example.com", "password": "wrong"},
    )
    assert bad_login.status_code == 401
    assert bad_login.json()["error"]["message"] == "Email or password is incorrect"

    profile = client.patch(
        "/api/v1/profile",
        headers=headers,
        json={
            "display_name": "Updated Viewer",
            "preferences": {
                "favorite_genres": ["crime"],
                "favorite_themes": ["one-night"],
                "hidden_gem_preference": 0.8,
            },
            "privacy": {"analytics_consent": True},
        },
    )
    assert profile.status_code == 200, profile.text
    assert profile.json()["display_name"] == "Updated Viewer"
    assert profile.json()["preferences"]["favorite_genres"] == ["crime"]
    assert profile.json()["privacy"]["analytics_consent"] is True

    exported = client.get("/api/v1/profile/export", headers=headers)
    assert exported.status_code == 200
    assert "attachment" in exported.headers["content-disposition"]
    assert "password_hash" not in exported.text

    logout = client.post("/api/v1/auth/logout", headers=headers)
    assert logout.status_code == 204
    revoked = client.get("/api/v1/profile", headers=headers)
    assert revoked.status_code == 401
    assert "revoked" in revoked.json()["error"]["message"]


def test_weak_password_has_specific_safe_error(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": "weak@example.com",
            "password": "password",
            "display_name": "Weak",
            "locale": "en",
        },
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "weak_password"


def test_cookie_auth_requires_double_submit_csrf(client: TestClient) -> None:
    register_user(client, email="cookie@example.com")

    rejected = client.patch("/api/v1/profile", json={"display_name": "Rejected"})
    assert rejected.status_code == 403
    assert rejected.json()["error"]["code"] == "csrf_failed"

    csrf = client.cookies.get("tt_csrf")
    accepted = client.patch(
        "/api/v1/profile",
        headers={"X-CSRF-Token": csrf, "Origin": "http://testserver"},
        json={"display_name": "Cookie User"},
    )
    assert accepted.status_code == 200
    assert accepted.json()["display_name"] == "Cookie User"

    wrong_origin = client.patch(
        "/api/v1/profile",
        headers={"X-CSRF-Token": csrf, "Origin": "https://evil.example"},
        json={"display_name": "Nope"},
    )
    assert wrong_origin.status_code == 403


def test_profile_deletion_removes_account_and_session(client: TestClient) -> None:
    _, headers = register_user(client, email="delete@example.com")
    deleted = client.delete("/api/v1/profile", headers=headers)
    assert deleted.status_code == 204
    assert client.get("/api/v1/profile", headers=headers).status_code == 401
