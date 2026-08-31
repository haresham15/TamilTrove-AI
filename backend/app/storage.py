from __future__ import annotations

import json
import secrets
import sqlite3
import threading
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .errors import ConflictError, NotFoundError


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


DEFAULT_PREFERENCES = {
    "favorite_genres": [],
    "favorite_themes": [],
    "preferred_eras": [],
    "hidden_gem_preference": 0.5,
    "languages": ["Tamil"],
    "dubbing_tolerance": False,
    "onboarding_movie_ids": [],
}
DEFAULT_PRIVACY = {
    "store_search_history": True,
    "use_interactions_for_recommendations": True,
    "analytics_consent": False,
}


SCHEMA = """
PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    email TEXT NOT NULL UNIQUE COLLATE NOCASE,
    password_hash TEXT NOT NULL,
    display_name TEXT NOT NULL,
    locale TEXT NOT NULL DEFAULT 'en',
    preferences_json TEXT NOT NULL,
    privacy_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS user_interactions (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    movie_id TEXT NOT NULL,
    interaction_type TEXT NOT NULL CHECK (interaction_type IN
      ('impression','click','save','rating','like','dislike','dismiss','viewed')),
    value REAL,
    context_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(user_id, movie_id, interaction_type)
);
CREATE INDEX IF NOT EXISTS idx_interactions_user_updated
    ON user_interactions(user_id, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_interactions_movie_type
    ON user_interactions(movie_id, interaction_type);
CREATE TABLE IF NOT EXISTS collections (
    id TEXT PRIMARY KEY,
    owner_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    visibility TEXT NOT NULL CHECK (visibility IN ('private','unlisted','public')),
    share_token TEXT UNIQUE,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_collections_owner_updated
    ON collections(owner_id, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_collections_visibility
    ON collections(visibility, updated_at DESC);
CREATE TABLE IF NOT EXISTS collection_items (
    collection_id TEXT NOT NULL REFERENCES collections(id) ON DELETE CASCADE,
    movie_id TEXT NOT NULL,
    position INTEGER NOT NULL CHECK (position >= 0),
    note TEXT,
    added_at TEXT NOT NULL,
    PRIMARY KEY(collection_id, movie_id)
);
CREATE INDEX IF NOT EXISTS idx_collection_items_order
    ON collection_items(collection_id, position, added_at);
CREATE TABLE IF NOT EXISTS search_history (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    query_text TEXT NOT NULL,
    normalized_query TEXT NOT NULL,
    detected_language TEXT NOT NULL,
    filters_json TEXT NOT NULL,
    result_ids_json TEXT NOT NULL,
    ranking_version TEXT NOT NULL,
    latency_ms REAL NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_search_history_user_created
    ON search_history(user_id, created_at DESC);
CREATE TABLE IF NOT EXISTS ingestion_runs (
    id TEXT PRIMARY KEY,
    dataset_version TEXT,
    transformation_version TEXT NOT NULL,
    status TEXT NOT NULL,
    dry_run INTEGER NOT NULL,
    report_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    completed_at TEXT
);
CREATE TABLE IF NOT EXISTS dataset_versions (
    id TEXT PRIMARY KEY,
    content_hash TEXT NOT NULL UNIQUE,
    record_count INTEGER NOT NULL,
    status TEXT NOT NULL,
    report_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS revoked_access_tokens (
    jti TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    expires_at INTEGER NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_revoked_tokens_expiry
    ON revoked_access_tokens(expires_at);
"""


class SQLiteStore:
    """Transactional local repository used for development and deterministic tests."""

    def __init__(self, path: Path):
        self.path = path
        self._lock = threading.RLock()
        self._connection: sqlite3.Connection | None = None

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path, check_same_thread=False, timeout=30)
        connection.row_factory = sqlite3.Row
        with self._lock:
            connection.executescript(SCHEMA)
            connection.commit()
            self._connection = connection

    def close(self) -> None:
        with self._lock:
            if self._connection is not None:
                self._connection.close()
                self._connection = None

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        if self._connection is None:
            raise RuntimeError("Database is not initialized")
        with self._lock:
            try:
                yield self._connection
                self._connection.commit()
            except Exception:
                self._connection.rollback()
                raise

    def ping(self) -> bool:
        try:
            with self.transaction() as connection:
                return connection.execute("SELECT 1").fetchone()[0] == 1
        except Exception:
            return False

    @staticmethod
    def _user(row: sqlite3.Row | None) -> dict[str, Any] | None:
        if row is None:
            return None
        result = dict(row)
        result["preferences"] = json.loads(result.pop("preferences_json"))
        result["privacy"] = json.loads(result.pop("privacy_json"))
        return result

    def create_user(
        self, email: str, password_hash: str, display_name: str, locale: str
    ) -> dict[str, Any]:
        identifier, now = str(uuid.uuid4()), utc_now()
        try:
            with self.transaction() as connection:
                connection.execute(
                    """INSERT INTO users
                    (id,email,password_hash,display_name,locale,preferences_json,privacy_json,created_at,updated_at)
                    VALUES (?,?,?,?,?,?,?,?,?)""",
                    (
                        identifier,
                        email.casefold(),
                        password_hash,
                        display_name,
                        locale,
                        json.dumps(DEFAULT_PREFERENCES),
                        json.dumps(DEFAULT_PRIVACY),
                        now,
                        now,
                    ),
                )
        except sqlite3.IntegrityError as exc:
            raise ConflictError("An account with this email already exists") from exc
        return self.get_user(identifier)  # type: ignore[return-value]

    def get_user(self, user_id: str) -> dict[str, Any] | None:
        with self.transaction() as connection:
            return self._user(
                connection.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
            )

    def get_user_by_email(self, email: str) -> dict[str, Any] | None:
        with self.transaction() as connection:
            row = connection.execute(
                "SELECT * FROM users WHERE email=? COLLATE NOCASE", (email,)
            ).fetchone()
            return self._user(row)

    def update_user(self, user_id: str, changes: dict[str, Any]) -> dict[str, Any]:
        current = self.get_user(user_id)
        if not current:
            raise NotFoundError("Profile")
        display_name = changes.get("display_name", current["display_name"])
        locale = changes.get("locale", current["locale"])
        preferences = changes.get("preferences", current["preferences"])
        privacy = changes.get("privacy", current["privacy"])
        now = utc_now()
        with self.transaction() as connection:
            connection.execute(
                """UPDATE users SET display_name=?,locale=?,preferences_json=?,privacy_json=?,updated_at=?
                WHERE id=?""",
                (display_name, locale, json.dumps(preferences), json.dumps(privacy), now, user_id),
            )
        return self.get_user(user_id)  # type: ignore[return-value]

    def delete_user(self, user_id: str) -> bool:
        with self.transaction() as connection:
            return connection.execute("DELETE FROM users WHERE id=?", (user_id,)).rowcount > 0

    def upsert_interaction(
        self,
        user_id: str,
        movie_id: str,
        interaction_type: str,
        value: float | None,
        context: dict[str, Any],
    ) -> dict[str, Any]:
        identifier, now = str(uuid.uuid4()), utc_now()
        with self.transaction() as connection:
            connection.execute(
                """INSERT INTO user_interactions
                (id,user_id,movie_id,interaction_type,value,context_json,created_at,updated_at)
                VALUES (?,?,?,?,?,?,?,?)
                ON CONFLICT(user_id,movie_id,interaction_type) DO UPDATE SET
                  value=excluded.value, context_json=excluded.context_json, updated_at=excluded.updated_at""",
                (
                    identifier,
                    user_id,
                    movie_id,
                    interaction_type,
                    value,
                    json.dumps(context),
                    now,
                    now,
                ),
            )
            row = connection.execute(
                "SELECT * FROM user_interactions WHERE user_id=? AND movie_id=? AND interaction_type=?",
                (user_id, movie_id, interaction_type),
            ).fetchone()
        return self._interaction(row)

    @staticmethod
    def _interaction(row: sqlite3.Row) -> dict[str, Any]:
        result = dict(row)
        result["type"] = result.pop("interaction_type")
        result["context"] = json.loads(result.pop("context_json"))
        result.pop("user_id", None)
        return result

    def list_interactions(
        self, user_id: str, interaction_type: str | None = None, limit: int = 200, offset: int = 0
    ) -> list[dict[str, Any]]:
        sql = "SELECT * FROM user_interactions WHERE user_id=?"
        params: list[Any] = [user_id]
        if interaction_type:
            sql += " AND interaction_type=?"
            params.append(interaction_type)
        sql += " ORDER BY updated_at DESC LIMIT ? OFFSET ?"
        params.extend((limit, offset))
        with self.transaction() as connection:
            return [self._interaction(row) for row in connection.execute(sql, params).fetchall()]

    def delete_interaction(self, user_id: str, movie_id: str, interaction_type: str) -> bool:
        with self.transaction() as connection:
            return (
                connection.execute(
                    "DELETE FROM user_interactions WHERE user_id=? AND movie_id=? AND interaction_type=?",
                    (user_id, movie_id, interaction_type),
                ).rowcount
                > 0
            )

    def clear_interactions(self, user_id: str) -> int:
        with self.transaction() as connection:
            return connection.execute(
                "DELETE FROM user_interactions WHERE user_id=?", (user_id,)
            ).rowcount

    def create_collection(
        self, owner_id: str, name: str, description: str, visibility: str
    ) -> dict[str, Any]:
        identifier, now = str(uuid.uuid4()), utc_now()
        with self.transaction() as connection:
            connection.execute(
                "INSERT INTO collections VALUES (?,?,?,?,?,?,?,?)",
                (identifier, owner_id, name, description, visibility, None, now, now),
            )
        return self.get_collection(identifier)  # type: ignore[return-value]

    @staticmethod
    def _collection(row: sqlite3.Row | None) -> dict[str, Any] | None:
        return dict(row) if row else None

    def list_collections(self, owner_id: str) -> list[dict[str, Any]]:
        with self.transaction() as connection:
            rows = connection.execute(
                """SELECT c.*,u.display_name AS owner_display_name,
                (SELECT COUNT(*) FROM collection_items i WHERE i.collection_id=c.id) AS item_count
                FROM collections c JOIN users u ON u.id=c.owner_id
                WHERE c.owner_id=? ORDER BY c.updated_at DESC""",
                (owner_id,),
            ).fetchall()
            return [dict(row) for row in rows]

    def get_collection(self, collection_id: str) -> dict[str, Any] | None:
        with self.transaction() as connection:
            row = connection.execute(
                """SELECT c.*,u.display_name AS owner_display_name,
                (SELECT COUNT(*) FROM collection_items i WHERE i.collection_id=c.id) AS item_count
                FROM collections c JOIN users u ON u.id=c.owner_id WHERE c.id=?""",
                (collection_id,),
            ).fetchone()
            return self._collection(row)

    def get_shared_collection(self, token: str) -> dict[str, Any] | None:
        with self.transaction() as connection:
            row = connection.execute(
                """SELECT c.*,u.display_name AS owner_display_name,
                (SELECT COUNT(*) FROM collection_items i WHERE i.collection_id=c.id) AS item_count
                FROM collections c JOIN users u ON u.id=c.owner_id
                WHERE c.share_token=? AND c.visibility IN ('unlisted','public')""",
                (token,),
            ).fetchone()
            return self._collection(row)

    def update_collection(self, collection_id: str, changes: dict[str, Any]) -> dict[str, Any]:
        current = self.get_collection(collection_id)
        if not current:
            raise NotFoundError("Collection")
        values = (
            changes.get("name", current["name"]),
            changes.get("description", current["description"]),
            changes.get("visibility", current["visibility"]),
            utc_now(),
            collection_id,
        )
        with self.transaction() as connection:
            connection.execute(
                "UPDATE collections SET name=?,description=?,visibility=?,updated_at=? WHERE id=?",
                values,
            )
            if values[2] == "private":
                connection.execute(
                    "UPDATE collections SET share_token=NULL WHERE id=?", (collection_id,)
                )
        return self.get_collection(collection_id)  # type: ignore[return-value]

    def share_collection(self, collection_id: str) -> dict[str, Any]:
        current = self.get_collection(collection_id)
        if not current:
            raise NotFoundError("Collection")
        token = current.get("share_token") or secrets.token_urlsafe(24)
        visibility = "unlisted" if current["visibility"] == "private" else current["visibility"]
        with self.transaction() as connection:
            connection.execute(
                "UPDATE collections SET share_token=?,visibility=?,updated_at=? WHERE id=?",
                (token, visibility, utc_now(), collection_id),
            )
        return self.get_collection(collection_id)  # type: ignore[return-value]

    def delete_collection(self, collection_id: str) -> bool:
        with self.transaction() as connection:
            return (
                connection.execute("DELETE FROM collections WHERE id=?", (collection_id,)).rowcount
                > 0
            )

    def add_collection_item(self, collection_id: str, movie_id: str, position: int | None) -> None:
        with self.transaction() as connection:
            if position is None:
                row = connection.execute(
                    "SELECT COALESCE(MAX(position),-1)+1 FROM collection_items WHERE collection_id=?",
                    (collection_id,),
                ).fetchone()
                position = int(row[0])
            connection.execute(
                """INSERT INTO collection_items(collection_id,movie_id,position,note,added_at)
                VALUES (?,?,?,?,?) ON CONFLICT(collection_id,movie_id) DO UPDATE SET position=excluded.position""",
                (collection_id, movie_id, position, None, utc_now()),
            )
            connection.execute(
                "UPDATE collections SET updated_at=? WHERE id=?", (utc_now(), collection_id)
            )

    def remove_collection_item(self, collection_id: str, movie_id: str) -> bool:
        with self.transaction() as connection:
            deleted = (
                connection.execute(
                    "DELETE FROM collection_items WHERE collection_id=? AND movie_id=?",
                    (collection_id, movie_id),
                ).rowcount
                > 0
            )
            if deleted:
                connection.execute(
                    "UPDATE collections SET updated_at=? WHERE id=?", (utc_now(), collection_id)
                )
            return deleted

    def collection_items(self, collection_id: str) -> list[dict[str, Any]]:
        with self.transaction() as connection:
            return [
                dict(row)
                for row in connection.execute(
                    "SELECT * FROM collection_items WHERE collection_id=? ORDER BY position,added_at",
                    (collection_id,),
                ).fetchall()
            ]

    def add_search_history(
        self,
        user_id: str,
        query_text: str,
        normalized_query: str,
        language: str,
        filters: dict[str, Any],
        result_ids: list[str],
        ranking_version: str,
        latency_ms: float,
    ) -> None:
        with self.transaction() as connection:
            connection.execute(
                """INSERT INTO search_history VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (
                    str(uuid.uuid4()),
                    user_id,
                    query_text,
                    normalized_query,
                    language,
                    json.dumps(filters),
                    json.dumps(result_ids),
                    ranking_version,
                    latency_ms,
                    utc_now(),
                ),
            )

    def list_search_history(self, user_id: str, limit: int = 100) -> list[dict[str, Any]]:
        with self.transaction() as connection:
            rows = connection.execute(
                "SELECT * FROM search_history WHERE user_id=? ORDER BY created_at DESC LIMIT ?",
                (user_id, limit),
            ).fetchall()
        results = []
        for row in rows:
            result = dict(row)
            result["filters"] = json.loads(result.pop("filters_json"))
            result["result_ids"] = json.loads(result.pop("result_ids_json"))
            result.pop("user_id", None)
            results.append(result)
        return results

    def clear_search_history(self, user_id: str) -> int:
        with self.transaction() as connection:
            return connection.execute(
                "DELETE FROM search_history WHERE user_id=?", (user_id,)
            ).rowcount

    def record_ingestion_run(
        self,
        transformation_version: str,
        dry_run: bool,
        report: dict[str, Any],
        status: str = "completed",
    ) -> dict[str, Any]:
        identifier, now = str(uuid.uuid4()), utc_now()
        with self.transaction() as connection:
            content_hash = str(report.get("content_hash") or "")
            if content_hash:
                connection.execute(
                    """INSERT INTO dataset_versions
                    (id,content_hash,record_count,status,report_json,created_at)
                    VALUES (?,?,?,?,?,?)
                    ON CONFLICT(content_hash) DO UPDATE SET
                      record_count=excluded.record_count,
                      status=excluded.status,
                      report_json=excluded.report_json""",
                    (
                        report.get("dataset_version") or str(uuid.uuid4()),
                        content_hash,
                        int(report.get("accepted_count", 0)),
                        "validated" if dry_run else "active",
                        json.dumps(report),
                        now,
                    ),
                )
            connection.execute(
                "INSERT INTO ingestion_runs VALUES (?,?,?,?,?,?,?,?)",
                (
                    identifier,
                    report.get("dataset_version"),
                    transformation_version,
                    status,
                    int(dry_run),
                    json.dumps(report),
                    now,
                    now,
                ),
            )
        return {
            "id": identifier,
            "status": status,
            "dry_run": dry_run,
            "report": report,
            "created_at": now,
        }

    def list_dataset_versions(self) -> list[dict[str, Any]]:
        with self.transaction() as connection:
            rows = connection.execute(
                "SELECT * FROM dataset_versions ORDER BY created_at DESC"
            ).fetchall()
        values = []
        for row in rows:
            value = dict(row)
            value["report"] = json.loads(value.pop("report_json"))
            values.append(value)
        return values

    def export_user(self, user_id: str) -> dict[str, Any]:
        user = self.get_user(user_id)
        if not user:
            raise NotFoundError("Profile")
        user.pop("password_hash", None)
        return {
            "profile": user,
            "interactions": self.list_interactions(user_id, limit=10_000),
            "collections": self.list_collections(user_id),
            "search_history": self.list_search_history(user_id, limit=10_000),
            "exported_at": utc_now(),
        }

    def revoke_token(self, jti: str, user_id: str, expires_at: int) -> None:
        with self.transaction() as connection:
            connection.execute(
                "DELETE FROM revoked_access_tokens WHERE expires_at <= ?",
                (int(datetime.now(UTC).timestamp()),),
            )
            connection.execute(
                "INSERT OR REPLACE INTO revoked_access_tokens(jti,user_id,expires_at,created_at) VALUES (?,?,?,?)",
                (jti, user_id, expires_at, utc_now()),
            )

    def is_token_revoked(self, jti: str) -> bool:
        with self.transaction() as connection:
            row = connection.execute(
                "SELECT 1 FROM revoked_access_tokens WHERE jti=? AND expires_at>?",
                (jti, int(datetime.now(UTC).timestamp())),
            ).fetchone()
            return row is not None


def create_store(database_url: str) -> Any:
    """Select the transactional repository without importing optional drivers eagerly."""

    if database_url.startswith("sqlite:///"):
        return SQLiteStore(Path(database_url.removeprefix("sqlite:///")))
    if database_url.startswith(("postgresql://", "postgres://", "postgresql+psycopg://")):
        from .postgres import PostgresStore

        return PostgresStore(database_url.replace("postgresql+psycopg://", "postgresql://", 1))
    raise ValueError("DATABASE_URL must use sqlite:/// or postgresql://")
