from __future__ import annotations

import math
import os
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse

BACKEND_DIR = Path(__file__).resolve().parents[1]


def _as_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _as_csv(value: str | None, default: tuple[str, ...] = ()) -> tuple[str, ...]:
    if not value:
        return default
    return tuple(item.strip() for item in value.split(",") if item.strip())


@dataclass(frozen=True, slots=True)
class Settings:
    environment: str = "development"
    app_name: str = "TamilTrove API"
    app_version: str = "2.0.0"
    database_url: str = f"sqlite:///{(BACKEND_DIR / 'data' / 'tamiltrove_v2.db').as_posix()}"
    data_path: Path = BACKEND_DIR / "data" / "movies_processed.json"
    embeddings_path: Path = BACKEND_DIR / "data" / "embeddings.npy"
    model_name: str = "sentence-transformers/all-MiniLM-L6-v2"
    model_version: str = "1"
    enable_transformer: bool = False
    secret_key: str = "development-only-change-me-at-least-32"
    auth_token_ttl_seconds: int = 60 * 60
    allowed_origins: tuple[str, ...] = ("http://localhost:3000",)
    admin_emails: tuple[str, ...] = ()
    trusted_poster_hosts: tuple[str, ...] = (
        "upload.wikimedia.org",
        "image.tmdb.org",
    )
    rate_limit_requests: int = 120
    rate_limit_window_seconds: int = 60
    max_request_bytes: int = 1_048_576
    debug_scores: bool = False
    metrics_enabled: bool = True
    session_cookie_name: str = "tt_session"
    csrf_cookie_name: str = "tt_csrf"
    ranking_semantic_weight: float = 0.46
    ranking_lexical_weight: float = 0.34
    ranking_preference_weight: float = 0.10
    ranking_quality_weight: float = 0.06
    ranking_hidden_gem_weight: float = 0.04
    ranking_diversity: float = 0.18
    ranking_candidate_limit: int = 250
    ranking_version: str = field(default="v2-local-hybrid-1")

    def __post_init__(self) -> None:
        if self.environment in {"staging", "production"}:
            if len(self.secret_key.encode("utf-8")) < 32 or self.secret_key.startswith(
                "development-only-change-me"
            ):
                raise RuntimeError("TAMILTROVE_SECRET_KEY must be at least 32 random characters")
            insecure_origins = [
                origin for origin in self.allowed_origins if urlparse(origin).scheme != "https"
            ]
            if insecure_origins:
                raise RuntimeError("Production and staging ALLOWED_ORIGINS must use HTTPS")
        if self.environment == "production" and not self.database_url.startswith(
            ("postgresql://", "postgresql+psycopg://", "postgres://")
        ):
            raise RuntimeError("Production requires PostgreSQL as the canonical database")
        weights = (
            self.ranking_semantic_weight,
            self.ranking_lexical_weight,
            self.ranking_preference_weight,
            self.ranking_quality_weight,
            self.ranking_hidden_gem_weight,
            self.ranking_diversity,
        )
        if not all(math.isfinite(value) and value >= 0 for value in weights):
            raise RuntimeError("Ranking weights must be finite and non-negative")
        if self.ranking_diversity > 1:
            raise RuntimeError("RANKING_DIVERSITY must be between 0 and 1")

    @classmethod
    def from_env(cls) -> Settings:
        environment = os.getenv("TAMILTROVE_ENV", os.getenv("APP_ENV", "development")).lower()
        secret = os.getenv("TAMILTROVE_SECRET_KEY", os.getenv("SECRET_KEY", ""))
        if not secret:
            if environment in {"production", "staging"}:
                raise RuntimeError("TAMILTROVE_SECRET_KEY is required outside development/test")
            secret = "development-only-change-me-at-least-32"
        if environment in {"production", "staging"} and len(secret.encode("utf-8")) < 32:
            raise RuntimeError("TAMILTROVE_SECRET_KEY must contain at least 32 bytes")

        default_db = f"sqlite:///{(BACKEND_DIR / 'data' / 'tamiltrove_v2.db').as_posix()}"
        return cls(
            environment=environment,
            database_url=os.getenv(
                "TAMILTROVE_DATABASE_URL", os.getenv("DATABASE_URL", default_db)
            ),
            data_path=Path(
                os.getenv(
                    "TAMILTROVE_DATA_PATH", str(BACKEND_DIR / "data" / "movies_processed.json")
                )
            ),
            embeddings_path=Path(
                os.getenv(
                    "TAMILTROVE_EMBEDDINGS_PATH", str(BACKEND_DIR / "data" / "embeddings.npy")
                )
            ),
            model_name=os.getenv("TAMILTROVE_MODEL_NAME", "sentence-transformers/all-MiniLM-L6-v2"),
            model_version=os.getenv("TAMILTROVE_MODEL_VERSION", "1"),
            enable_transformer=_as_bool(os.getenv("TAMILTROVE_ENABLE_TRANSFORMER"), False),
            secret_key=secret,
            auth_token_ttl_seconds=max(300, int(os.getenv("AUTH_TOKEN_TTL_SECONDS", "3600"))),
            allowed_origins=_as_csv(os.getenv("ALLOWED_ORIGINS"), ("http://localhost:3000",)),
            admin_emails=tuple(
                email.casefold() for email in _as_csv(os.getenv("TAMILTROVE_ADMIN_EMAILS"))
            ),
            trusted_poster_hosts=_as_csv(
                os.getenv("TRUSTED_POSTER_HOSTS"), ("upload.wikimedia.org", "image.tmdb.org")
            ),
            rate_limit_requests=max(1, int(os.getenv("RATE_LIMIT_REQUESTS", "120"))),
            rate_limit_window_seconds=max(1, int(os.getenv("RATE_LIMIT_WINDOW_SECONDS", "60"))),
            max_request_bytes=max(1024, int(os.getenv("MAX_REQUEST_BYTES", "1048576"))),
            debug_scores=_as_bool(
                os.getenv("TAMILTROVE_DEBUG_SCORES"), environment != "production"
            ),
            metrics_enabled=_as_bool(os.getenv("TAMILTROVE_METRICS_ENABLED"), True),
            ranking_semantic_weight=float(os.getenv("RANKING_SEMANTIC_WEIGHT", "0.46")),
            ranking_lexical_weight=float(os.getenv("RANKING_LEXICAL_WEIGHT", "0.34")),
            ranking_preference_weight=float(os.getenv("RANKING_PREFERENCE_WEIGHT", "0.10")),
            ranking_quality_weight=float(os.getenv("RANKING_QUALITY_WEIGHT", "0.06")),
            ranking_hidden_gem_weight=float(os.getenv("RANKING_HIDDEN_GEM_WEIGHT", "0.04")),
            ranking_diversity=float(os.getenv("RANKING_DIVERSITY", "0.18")),
            ranking_candidate_limit=max(50, int(os.getenv("RANKING_CANDIDATE_LIMIT", "250"))),
            ranking_version=os.getenv("TAMILTROVE_RANKING_VERSION", "v2-local-hybrid-1"),
        )

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def secure_cookies(self) -> bool:
        return self.environment in {"staging", "production"}

    @property
    def sqlite_path(self) -> Path:
        if not self.database_url.startswith("sqlite:///"):
            raise ValueError("The local state store requires a sqlite:/// URL")
        value = self.database_url.removeprefix("sqlite:///")
        return Path(value)
