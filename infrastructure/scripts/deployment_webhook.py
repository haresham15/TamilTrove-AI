"""Validate and submit a narrow, immutable TamilTrove deployment intent."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import ssl
import sys
import urllib.error
import urllib.request
import uuid
from dataclasses import asdict, dataclass
from typing import Any
from urllib.parse import urlsplit


IMAGE_RE = re.compile(
    r"^ghcr\.io/[a-z0-9][a-z0-9._-]*/[a-z0-9][a-z0-9._/-]*@sha256:[0-9a-f]{64}$"
)
RELEASE_RE = re.compile(r"^[0-9a-f]{40}$")
VERSION_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/+-]{0,127}$")


class NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Do not risk forwarding an environment credential across a redirect."""

    def redirect_request(  # type: ignore[override]
        self,
        request: urllib.request.Request,
        file_pointer: Any,
        code: int,
        message: str,
        headers: Any,
        new_url: str,
    ) -> None:
        return None


@dataclass(frozen=True, slots=True)
class DeploymentIntent:
    schema_version: int
    action: str
    environment: str
    release_id: str
    backend_image: str
    frontend_image: str
    migration_id: str | None = None
    dataset_version: str | None = None
    embedding_model: str | None = None
    embedding_model_version: str | None = None
    ranking_version: str | None = None
    reason: str | None = None

    def payload(self) -> dict[str, Any]:
        return {key: value for key, value in asdict(self).items() if value not in {None, ""}}


def valid_version(value: str | None, field: str, *, required: bool = False) -> str | None:
    if not value:
        if required:
            raise ValueError(f"{field} is required")
        return None
    if not VERSION_RE.fullmatch(value):
        raise ValueError(f"{field} contains unsupported characters or is too long")
    return value


def build_intent(args: argparse.Namespace) -> DeploymentIntent:
    if args.environment not in {"staging", "production"}:
        raise ValueError("environment must be staging or production")
    if args.action not in {"migrate", "deploy", "rollback"}:
        raise ValueError("action must be migrate, deploy, or rollback")
    if not RELEASE_RE.fullmatch(args.release_id):
        raise ValueError("release-id must be a full lowercase 40-character Git commit")
    for field, image in (("backend-image", args.backend_image), ("frontend-image", args.frontend_image)):
        if not IMAGE_RE.fullmatch(image):
            raise ValueError(f"{field} must be a lowercase GHCR image pinned by sha256 digest")

    migration_id = valid_version(args.migration_id, "migration-id")
    dataset_version = valid_version(
        args.dataset_version,
        "dataset-version",
        required=args.action in {"deploy", "rollback"},
    )
    embedding_model = valid_version(
        args.embedding_model,
        "embedding-model",
        required=args.action in {"deploy", "rollback"},
    )
    embedding_model_version = valid_version(
        args.embedding_model_version,
        "embedding-model-version",
        required=args.action in {"deploy", "rollback"},
    )
    ranking_version = valid_version(
        args.ranking_version,
        "ranking-version",
        required=args.action in {"deploy", "rollback"},
    )
    reason = args.reason.strip() if args.reason else None
    if reason and (len(reason) > 500 or any(ord(character) < 32 for character in reason)):
        raise ValueError("reason must be at most 500 printable characters")
    if args.action == "rollback" and (not reason or len(reason) < 10):
        raise ValueError("rollback requires a reason of at least 10 characters")

    return DeploymentIntent(
        schema_version=2,
        action=args.action,
        environment=args.environment,
        release_id=args.release_id,
        backend_image=args.backend_image,
        frontend_image=args.frontend_image,
        migration_id=migration_id,
        dataset_version=dataset_version,
        embedding_model=embedding_model,
        embedding_model_version=embedding_model_version,
        ranking_version=ranking_version,
        reason=reason,
    )


def validate_url(value: str) -> str:
    parsed = urlsplit(value)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("DEPLOY_WEBHOOK_URL must be an HTTPS URL without embedded credentials")
    if parsed.fragment:
        raise ValueError("DEPLOY_WEBHOOK_URL must not contain a fragment")
    return value


def submit(intent: DeploymentIntent, url: str, token: str, timeout: float) -> dict[str, Any]:
    if len(token) < 20:
        raise ValueError("DEPLOY_TOKEN is missing or unexpectedly short")
    request_id = str(uuid.uuid4())
    data = json.dumps(intent.payload(), separators=(",", ":"), sort_keys=True).encode("utf-8")
    request = urllib.request.Request(
        validate_url(url),
        data=data,
        headers={
            "Accept": "application/json",
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Idempotency-Key": (
                f"{intent.environment}:{intent.action}:{intent.release_id}:"
                f"{hashlib.sha256(data).hexdigest()[:24]}"
            ),
            "User-Agent": "tamiltrove-deployment-client/2",
            "X-Request-ID": request_id,
        },
        method="POST",
    )
    opener = urllib.request.build_opener(
        NoRedirectHandler(), urllib.request.HTTPSHandler(context=ssl.create_default_context())
    )
    try:
        with opener.open(request, timeout=timeout) as response:
            if response.status < 200 or response.status >= 300:
                raise RuntimeError(f"deployment adapter returned HTTP {response.status}")
            if response.headers.get_content_type() != "application/json":
                raise RuntimeError("deployment adapter response must be application/json")
            result = json.load(response)
    except urllib.error.HTTPError as error:
        raise RuntimeError(f"deployment adapter returned HTTP {error.code}") from error
    except urllib.error.URLError as error:
        raise RuntimeError(f"deployment adapter connection failed: {error.reason}") from error

    if not isinstance(result, dict) or result.get("accepted") is not True:
        raise RuntimeError("deployment adapter did not accept the request")
    if result.get("status") != "succeeded":
        raise RuntimeError("deployment adapter did not report a successful terminal status")
    return result


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--action", required=True, choices=("migrate", "deploy", "rollback"))
    result.add_argument("--environment", required=True, choices=("staging", "production"))
    result.add_argument("--release-id", required=True)
    result.add_argument("--backend-image", required=True)
    result.add_argument("--frontend-image", required=True)
    result.add_argument("--migration-id")
    result.add_argument("--dataset-version")
    result.add_argument("--embedding-model")
    result.add_argument("--embedding-model-version")
    result.add_argument("--ranking-version")
    result.add_argument("--reason")
    result.add_argument("--timeout", type=float, default=300.0)
    result.add_argument("--dry-run", action="store_true")
    return result


def main() -> int:
    args = parser().parse_args()
    try:
        if not 1 <= args.timeout <= 900:
            raise ValueError("timeout must be between 1 and 900 seconds")
        intent = build_intent(args)
        if args.dry_run:
            print(json.dumps(intent.payload(), indent=2, sort_keys=True))
            return 0
        result = submit(
            intent,
            os.environ.get("DEPLOY_WEBHOOK_URL", ""),
            os.environ.get("DEPLOY_TOKEN", ""),
            args.timeout,
        )
        deployment_id = result.get("deployment_id", "not-provided")
        print(f"{intent.action} succeeded for {intent.environment}; deployment_id={deployment_id}")
        return 0
    except (ValueError, RuntimeError, json.JSONDecodeError) as error:
        print(f"Deployment request failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
