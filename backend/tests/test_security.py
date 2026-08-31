from __future__ import annotations

import pytest

from app.errors import AuthenticationError
from app.security import (
    hash_password,
    issue_token,
    validate_password_strength,
    verify_password,
    verify_token,
)


def test_password_hash_is_salted_and_verifies_without_plaintext() -> None:
    first = hash_password("CorrectHorse42")
    second = hash_password("CorrectHorse42")

    assert first != second
    assert "CorrectHorse42" not in first
    assert verify_password("CorrectHorse42", first)
    assert not verify_password("wrong", first)
    assert not verify_password("anything", "not-a-valid-hash")


@pytest.mark.parametrize(
    ("password", "email", "message"),
    [
        ("Short1", "user@example.com", "10 characters"),
        ("12345678901", "user@example.com", "letter"),
        ("OnlyLettersHere", "user@example.com", "number"),
        ("user-Password42", "user@example.com", "email name"),
    ],
)
def test_password_strength_rules(password: str, email: str, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        validate_password_strength(password, email)


def test_access_token_required_claims_expiry_and_signature() -> None:
    signing_key = "a" * 32
    different_key = "b" * 32
    token = issue_token("user-123", signing_key, 60, now=1_000)
    payload = verify_token(token, signing_key, now=1_001)
    assert payload["sub"] == "user-123"
    assert payload["iss"] == "tamiltrove"
    assert payload["jti"]

    with pytest.raises(AuthenticationError, match="expired"):
        verify_token(token, signing_key, now=1_060)
    with pytest.raises(AuthenticationError, match="invalid"):
        verify_token(token, different_key, now=1_001)
