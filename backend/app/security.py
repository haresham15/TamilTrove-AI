from __future__ import annotations

import base64
import hashlib
import hmac
import re
import secrets
import time
import uuid
from dataclasses import dataclass
from typing import Any

import jwt
from jwt.types import Options
from pwdlib import PasswordHash
from pwdlib.exceptions import UnknownHashError

from .errors import AuthenticationError

PBKDF2_ITERATIONS = 310_000
TOKEN_ISSUER = "tamiltrove"
SAFE_REQUEST_ID = re.compile(r"^[A-Za-z0-9._:-]{1,100}$")
PASSWORD_HASH = PasswordHash.recommended()
DUMMY_PASSWORD_HASH = PASSWORD_HASH.hash("invalid-login-placeholder-42")


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _b64decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def hash_password(password: str) -> str:
    """Hash new passwords with pwdlib's recommended Argon2id parameters."""

    return PASSWORD_HASH.hash(password)


def verify_password(password: str, encoded: str) -> bool:
    """Verify Argon2id hashes while retaining compatibility with V2 preview data."""

    if not encoded.startswith("pbkdf2_sha256$"):
        try:
            return PASSWORD_HASH.verify(password, encoded)
        except (TypeError, ValueError, UnknownHashError):
            return False

    # The preview implementation used this versioned PBKDF2 representation.
    # It remains verification-only so a staged rollout does not lock out users.
    try:
        algorithm, iterations, salt, expected = encoded.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        digest = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), _b64decode(salt), int(iterations)
        )
        return hmac.compare_digest(digest, _b64decode(expected))
    except (ValueError, TypeError):
        return False


def validate_password_strength(password: str, email: str = "") -> None:
    local_part = email.partition("@")[0].casefold()
    checks = (
        (len(password) >= 10, "Password must contain at least 10 characters"),
        (any(character.isalpha() for character in password), "Password must contain a letter"),
        (any(character.isdigit() for character in password), "Password must contain a number"),
        (
            not local_part or local_part not in password.casefold(),
            "Password must not contain your email name",
        ),
    )
    for passed, message in checks:
        if not passed:
            raise ValueError(message)


def issue_token(user_id: str, secret_key: str, ttl_seconds: int, now: int | None = None) -> str:
    if len(secret_key.encode("utf-8")) < 32:
        raise ValueError("Token signing keys must contain at least 32 bytes")
    timestamp = int(time.time() if now is None else now)
    payload = {
        "sub": user_id,
        "iss": TOKEN_ISSUER,
        "iat": timestamp,
        "exp": timestamp + ttl_seconds,
        "jti": str(uuid.uuid4()),
    }
    return jwt.encode(payload, secret_key, algorithm="HS256", headers={"typ": "JWT"})


def verify_token(token: str, secret_key: str, now: int | None = None) -> dict[str, Any]:
    try:
        if len(secret_key.encode("utf-8")) < 32:
            raise AuthenticationError("The access token is invalid")
        options: Options = {
            "require": ["sub", "iss", "iat", "exp", "jti"],
            "verify_exp": now is None,
            "verify_iat": now is None,
        }
        payload = jwt.decode(
            token,
            secret_key,
            algorithms=["HS256"],
            issuer=TOKEN_ISSUER,
            options=options,
        )
        if now is not None and int(payload["exp"]) <= now:
            raise AuthenticationError("The access token has expired")
        if now is not None and int(payload["iat"]) > now:
            raise AuthenticationError("The access token is invalid")
        if not isinstance(payload.get("sub"), str) or not payload["sub"]:
            raise AuthenticationError("The access token is invalid")
        return payload
    except AuthenticationError:
        raise
    except jwt.ExpiredSignatureError as exc:
        raise AuthenticationError("The access token has expired") from exc
    except jwt.PyJWTError as exc:
        raise AuthenticationError("The access token is invalid") from exc
    except Exception as exc:
        raise AuthenticationError("The access token is invalid") from exc


def csrf_token() -> str:
    return secrets.token_urlsafe(32)


@dataclass(frozen=True, slots=True)
class AuthenticatedUser:
    id: str
    email: str
    display_name: str
    is_admin: bool
