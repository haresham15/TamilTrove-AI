from __future__ import annotations

import hashlib
import math
import secrets
import threading
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from .catalog import Catalog, Movie
from .errors import ConflictError, NotFoundError
from .normalization import normalize_text
from .storage import DEFAULT_PREFERENCES, DEFAULT_PRIVACY, utc_now

PERSON_NAMESPACE = uuid.UUID("ceff381c-2db3-4f74-8aed-fbce4a72d213")


def _slug(value: str) -> str:
    normalized = normalize_text(value).replace(" ", "-")
    return (
        "".join(
            character for character in normalized if character.isalnum() or character == "-"
        ).strip("-")
        or "unknown"
    )


def _plain(value: Any) -> Any:
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, dict):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_plain(item) for item in value]
    return value


class PostgresStore:
    """Psycopg repository backed by the canonical PostgreSQL/pgvector schema."""

    def __init__(self, database_url: str, migration_path: Path | None = None):
        self.database_url = database_url
        self.migration_path = (
            migration_path
            or Path(__file__).resolve().parents[1] / "migrations" / "001_v2_schema.sql"
        )
        self._pool: Any | None = None
        self._initialization_lock = threading.Lock()

    def initialize(self) -> None:
        try:
            import psycopg
            from psycopg.rows import dict_row
            from psycopg_pool import ConnectionPool
        except ImportError as exc:  # pragma: no cover - exercised by deployment startup
            raise RuntimeError("PostgreSQL requires psycopg[binary,pool]") from exc

        with self._initialization_lock:
            if self._pool is not None:
                return
            with psycopg.connect(
                self.database_url, autocommit=True, row_factory=dict_row
            ) as connection:
                schema_row = connection.execute(
                    "SELECT to_regclass('public.users') AS name"
                ).fetchone()
                exists = schema_row["name"] if schema_row else None
                if exists is None:
                    connection.execute(
                        self.migration_path.read_text(encoding="utf-8"), prepare=False
                    )
                connection.execute(
                    """CREATE TABLE IF NOT EXISTS public.revoked_access_tokens (
                    jti text PRIMARY KEY,
                    user_id uuid NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
                    expires_at bigint NOT NULL,
                    created_at timestamptz NOT NULL DEFAULT clock_timestamp()
                    )"""
                )
                connection.execute(
                    "CREATE INDEX IF NOT EXISTS revoked_access_tokens_expiry_idx ON public.revoked_access_tokens(expires_at)"
                )
            self._pool = ConnectionPool(
                conninfo=self.database_url,
                min_size=1,
                max_size=10,
                kwargs={"row_factory": dict_row},
                open=True,
            )
            self._pool.wait(timeout=15)

    def close(self) -> None:
        if self._pool is not None:
            self._pool.close()
            self._pool = None

    @contextmanager
    def transaction(self) -> Iterator[Any]:
        if self._pool is None:
            raise RuntimeError("Database is not initialized")
        with self._pool.connection() as connection, connection.transaction():
            yield connection

    def ping(self) -> bool:
        try:
            with self.transaction() as connection:
                return connection.execute("SELECT 1 AS value").fetchone()["value"] == 1
        except Exception:
            return False

    @staticmethod
    def _user(row: dict[str, Any] | None) -> dict[str, Any] | None:
        if row is None:
            return None
        value = _plain(dict(row))
        value["preferences"] = value.pop("preferences_json") or dict(DEFAULT_PREFERENCES)
        value["privacy"] = value.pop("privacy_json") or dict(DEFAULT_PRIVACY)
        return value

    def create_user(
        self, email: str, password_hash: str, display_name: str, locale: str
    ) -> dict[str, Any]:
        from psycopg.errors import UniqueViolation
        from psycopg.types.json import Jsonb

        try:
            with self.transaction() as connection:
                row = connection.execute(
                    """INSERT INTO public.users
                    (auth_provider,email,password_hash,display_name,locale,preferences_json,privacy_json)
                    VALUES ('local',%s,%s,%s,%s,%s,%s)
                    RETURNING *""",
                    (
                        email.casefold(),
                        password_hash,
                        display_name,
                        locale,
                        Jsonb(DEFAULT_PREFERENCES),
                        Jsonb(DEFAULT_PRIVACY),
                    ),
                ).fetchone()
        except UniqueViolation as exc:
            raise ConflictError("An account with this email already exists") from exc
        return self._user(row)  # type: ignore[return-value]

    def get_user(self, user_id: str) -> dict[str, Any] | None:
        with self.transaction() as connection:
            row = connection.execute(
                "SELECT * FROM public.users WHERE id=%s AND deleted_at IS NULL", (user_id,)
            ).fetchone()
        return self._user(row)

    def get_user_by_email(self, email: str) -> dict[str, Any] | None:
        with self.transaction() as connection:
            row = connection.execute(
                "SELECT * FROM public.users WHERE lower(email)=lower(%s) AND deleted_at IS NULL",
                (email,),
            ).fetchone()
        return self._user(row)

    def update_user(self, user_id: str, changes: dict[str, Any]) -> dict[str, Any]:
        from psycopg.types.json import Jsonb

        current = self.get_user(user_id)
        if not current:
            raise NotFoundError("Profile")
        with self.transaction() as connection:
            connection.execute(
                """UPDATE public.users
                SET display_name=%s, locale=%s, preferences_json=%s, privacy_json=%s
                WHERE id=%s AND deleted_at IS NULL""",
                (
                    changes.get("display_name", current["display_name"]),
                    changes.get("locale", current["locale"]),
                    Jsonb(changes.get("preferences", current["preferences"])),
                    Jsonb(changes.get("privacy", current["privacy"])),
                    user_id,
                ),
            )
        return self.get_user(user_id)  # type: ignore[return-value]

    def delete_user(self, user_id: str) -> bool:
        # A hard delete honors the explicit account-deletion request and lets
        # foreign-key cascades remove private personalization state atomically.
        with self.transaction() as connection:
            return (
                connection.execute("DELETE FROM public.users WHERE id=%s", (user_id,)).rowcount > 0
            )

    @staticmethod
    def _interaction(row: dict[str, Any]) -> dict[str, Any]:
        value = _plain(dict(row))
        value["type"] = value.pop("interaction_type")
        value["context"] = value.pop("context_json") or {}
        value["created_at"] = value.pop("occurred_at")
        value["updated_at"] = value.get("updated_at") or value["created_at"]
        value.pop("user_id", None)
        return value

    def _update_movie_state(
        self,
        connection: Any,
        user_id: str,
        movie_id: str,
        interaction_type: str,
        value: float | None,
    ) -> None:
        current = (
            connection.execute(
                "SELECT * FROM public.user_movie_states WHERE user_id=%s AND movie_id=%s",
                (user_id, movie_id),
            ).fetchone()
            or {}
        )
        now = datetime.now(UTC)
        state = {
            "is_saved": bool(current.get("is_saved", False)),
            "like_state": int(current.get("like_state", 0)),
            "is_dismissed": bool(current.get("is_dismissed", False)),
            "is_viewed": bool(current.get("is_viewed", False)),
            "rating": current.get("rating"),
            "saved_at": current.get("saved_at"),
            "rated_at": current.get("rated_at"),
            "dismissed_at": current.get("dismissed_at"),
            "viewed_at": current.get("viewed_at"),
        }
        if interaction_type == "save":
            state.update(is_saved=True, saved_at=now)
        elif interaction_type == "rating":
            state.update(rating=value, rated_at=now)
        elif interaction_type == "like":
            state["like_state"] = 1
        elif interaction_type == "dislike":
            state["like_state"] = -1
        elif interaction_type == "dismiss":
            state.update(is_dismissed=True, dismissed_at=now)
        elif interaction_type == "viewed":
            state.update(is_viewed=True, viewed_at=now)
        connection.execute(
            """INSERT INTO public.user_movie_states
            (user_id,movie_id,is_saved,like_state,is_dismissed,is_viewed,rating,
             saved_at,rated_at,dismissed_at,viewed_at,last_interaction_at)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT(user_id,movie_id) DO UPDATE SET
              is_saved=excluded.is_saved,like_state=excluded.like_state,
              is_dismissed=excluded.is_dismissed,is_viewed=excluded.is_viewed,
              rating=excluded.rating,saved_at=excluded.saved_at,rated_at=excluded.rated_at,
              dismissed_at=excluded.dismissed_at,viewed_at=excluded.viewed_at,
              last_interaction_at=excluded.last_interaction_at""",
            (
                user_id,
                movie_id,
                state["is_saved"],
                state["like_state"],
                state["is_dismissed"],
                state["is_viewed"],
                state["rating"],
                state["saved_at"],
                state["rated_at"],
                state["dismissed_at"],
                state["viewed_at"],
                now,
            ),
        )

    def upsert_interaction(
        self,
        user_id: str,
        movie_id: str,
        interaction_type: str,
        value: float | None,
        context: dict[str, Any],
    ) -> dict[str, Any]:
        from psycopg.types.json import Jsonb

        with self.transaction() as connection:
            row = connection.execute(
                """INSERT INTO public.user_interactions
                (user_id,movie_id,interaction_type,value,context_json)
                VALUES (%s,%s,%s,%s,%s) RETURNING *""",
                (user_id, movie_id, interaction_type, value, Jsonb(context)),
            ).fetchone()
            self._update_movie_state(connection, user_id, movie_id, interaction_type, value)
        return self._interaction(row)

    def list_interactions(
        self, user_id: str, interaction_type: str | None = None, limit: int = 200, offset: int = 0
    ) -> list[dict[str, Any]]:
        sql = "SELECT * FROM public.user_interactions WHERE user_id=%s"
        params: list[Any] = [user_id]
        if interaction_type:
            sql += " AND interaction_type=%s"
            params.append(interaction_type)
        sql += " ORDER BY occurred_at DESC LIMIT %s OFFSET %s"
        params.extend((limit, offset))
        with self.transaction() as connection:
            rows = connection.execute(sql, params).fetchall()
        return [self._interaction(row) for row in rows]

    def list_all_interactions(self, interaction_type: str | None = None) -> list[dict[str, Any]]:
        sql = "SELECT user_id, movie_id, interaction_type, value FROM public.user_interactions"
        params: list[Any] = []
        if interaction_type:
            sql += " WHERE interaction_type=%s"
            params.append(interaction_type)
        with self.transaction() as connection:
            rows = connection.execute(sql, params).fetchall()
        return [_plain(dict(row)) for row in rows]

    def delete_interaction(self, user_id: str, movie_id: str, interaction_type: str) -> bool:
        with self.transaction() as connection:
            deleted = (
                connection.execute(
                    "DELETE FROM public.user_interactions WHERE user_id=%s AND movie_id=%s AND interaction_type=%s",
                    (user_id, movie_id, interaction_type),
                ).rowcount
                > 0
            )
            state_column = {
                "save": "is_saved=FALSE,saved_at=NULL",
                "rating": "rating=NULL,rated_at=NULL",
                "like": "like_state=0",
                "dislike": "like_state=0",
                "dismiss": "is_dismissed=FALSE,dismissed_at=NULL",
                "viewed": "is_viewed=FALSE,viewed_at=NULL",
            }.get(interaction_type)
            if state_column:
                connection.execute(
                    f"UPDATE public.user_movie_states SET {state_column} WHERE user_id=%s AND movie_id=%s",
                    (user_id, movie_id),
                )
            return deleted

    def clear_interactions(self, user_id: str) -> int:
        with self.transaction() as connection:
            count = connection.execute(
                "DELETE FROM public.user_interactions WHERE user_id=%s", (user_id,)
            ).rowcount
            connection.execute("DELETE FROM public.user_movie_states WHERE user_id=%s", (user_id,))
            return count

    @staticmethod
    def _collection(row: dict[str, Any] | None) -> dict[str, Any] | None:
        if row is None:
            return None
        value = _plain(dict(row))
        value["description"] = value.get("description") or ""
        return value

    def create_collection(
        self, owner_id: str, name: str, description: str, visibility: str
    ) -> dict[str, Any]:
        with self.transaction() as connection:
            row = connection.execute(
                """INSERT INTO public.collections(owner_id,name,description,visibility)
                VALUES (%s,%s,%s,%s) RETURNING id""",
                (owner_id, name, description, visibility),
            ).fetchone()
        return self.get_collection(str(row["id"]))  # type: ignore[return-value]

    def list_collections(self, owner_id: str) -> list[dict[str, Any]]:
        with self.transaction() as connection:
            rows = connection.execute(
                """SELECT c.*,u.display_name AS owner_display_name,
                (SELECT COUNT(*) FROM public.collection_items i WHERE i.collection_id=c.id) AS item_count
                FROM public.collections c JOIN public.users u ON u.id=c.owner_id
                WHERE c.owner_id=%s AND c.deleted_at IS NULL ORDER BY c.updated_at DESC""",
                (owner_id,),
            ).fetchall()
        return [collection for row in rows if (collection := self._collection(row)) is not None]

    def get_collection(self, collection_id: str) -> dict[str, Any] | None:
        with self.transaction() as connection:
            row = connection.execute(
                """SELECT c.*,u.display_name AS owner_display_name,
                (SELECT COUNT(*) FROM public.collection_items i WHERE i.collection_id=c.id) AS item_count
                FROM public.collections c JOIN public.users u ON u.id=c.owner_id
                WHERE c.id=%s AND c.deleted_at IS NULL""",
                (collection_id,),
            ).fetchone()
        return self._collection(row)

    def get_shared_collection(self, token: str) -> dict[str, Any] | None:
        with self.transaction() as connection:
            row = connection.execute(
                """SELECT c.*,u.display_name AS owner_display_name,
                (SELECT COUNT(*) FROM public.collection_items i WHERE i.collection_id=c.id) AS item_count
                FROM public.collections c JOIN public.users u ON u.id=c.owner_id
                WHERE c.share_token=%s AND c.visibility IN ('unlisted','public') AND c.deleted_at IS NULL""",
                (token,),
            ).fetchone()
        return self._collection(row)

    def update_collection(self, collection_id: str, changes: dict[str, Any]) -> dict[str, Any]:
        current = self.get_collection(collection_id)
        if not current:
            raise NotFoundError("Collection")
        visibility = changes.get("visibility", current["visibility"])
        with self.transaction() as connection:
            connection.execute(
                """UPDATE public.collections SET name=%s,description=%s,visibility=%s,
                share_token=CASE WHEN %s='private' THEN NULL ELSE share_token END
                WHERE id=%s AND deleted_at IS NULL""",
                (
                    changes.get("name", current["name"]),
                    changes.get("description", current["description"]),
                    visibility,
                    visibility,
                    collection_id,
                ),
            )
        return self.get_collection(collection_id)  # type: ignore[return-value]

    def share_collection(self, collection_id: str) -> dict[str, Any]:
        current = self.get_collection(collection_id)
        if not current:
            raise NotFoundError("Collection")
        token = current.get("share_token") or secrets.token_urlsafe(32)
        visibility = "unlisted" if current["visibility"] == "private" else current["visibility"]
        with self.transaction() as connection:
            connection.execute(
                "UPDATE public.collections SET share_token=%s,visibility=%s WHERE id=%s",
                (token, visibility, collection_id),
            )
        return self.get_collection(collection_id)  # type: ignore[return-value]

    def delete_collection(self, collection_id: str) -> bool:
        with self.transaction() as connection:
            return (
                connection.execute(
                    "UPDATE public.collections SET deleted_at=clock_timestamp(),share_token=NULL WHERE id=%s AND deleted_at IS NULL",
                    (collection_id,),
                ).rowcount
                > 0
            )

    def add_collection_item(self, collection_id: str, movie_id: str, position: int | None) -> None:
        with self.transaction() as connection:
            collection = connection.execute(
                "SELECT owner_id FROM public.collections WHERE id=%s AND deleted_at IS NULL",
                (collection_id,),
            ).fetchone()
            if not collection:
                raise NotFoundError("Collection")
            connection.execute("SET CONSTRAINTS collection_items_position_uidx DEFERRED")
            if position is None:
                position = connection.execute(
                    "SELECT COALESCE(MAX(position),-1)+1 AS position FROM public.collection_items WHERE collection_id=%s",
                    (collection_id,),
                ).fetchone()["position"]
            else:
                connection.execute(
                    "UPDATE public.collection_items SET position=position+1 WHERE collection_id=%s AND position >= %s",
                    (collection_id, position),
                )
            connection.execute(
                """INSERT INTO public.collection_items(collection_id,owner_id,movie_id,position)
                VALUES (%s,%s,%s,%s)
                ON CONFLICT(collection_id,movie_id) DO UPDATE SET position=excluded.position""",
                (collection_id, collection["owner_id"], movie_id, position),
            )

    def remove_collection_item(self, collection_id: str, movie_id: str) -> bool:
        with self.transaction() as connection:
            return (
                connection.execute(
                    "DELETE FROM public.collection_items WHERE collection_id=%s AND movie_id=%s",
                    (collection_id, movie_id),
                ).rowcount
                > 0
            )

    def collection_items(self, collection_id: str) -> list[dict[str, Any]]:
        with self.transaction() as connection:
            rows = connection.execute(
                "SELECT * FROM public.collection_items WHERE collection_id=%s ORDER BY position,added_at",
                (collection_id,),
            ).fetchall()
        return [_plain(dict(row)) for row in rows]

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
        from psycopg.types.json import Jsonb

        with self.transaction() as connection:
            connection.execute(
                """INSERT INTO public.search_history
                (user_id,query_text,normalized_query,detected_language,filters_json,result_ids_json,ranking_version,latency_ms)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
                (
                    user_id,
                    query_text,
                    normalized_query,
                    language,
                    Jsonb(filters),
                    Jsonb(result_ids),
                    ranking_version,
                    latency_ms,
                ),
            )

    def list_search_history(self, user_id: str, limit: int = 100) -> list[dict[str, Any]]:
        with self.transaction() as connection:
            rows = connection.execute(
                "SELECT * FROM public.search_history WHERE user_id=%s ORDER BY created_at DESC LIMIT %s",
                (user_id, limit),
            ).fetchall()
        results = []
        for row in rows:
            value = _plain(dict(row))
            value["filters"] = value.pop("filters_json")
            value["result_ids"] = value.pop("result_ids_json")
            value.pop("user_id", None)
            results.append(value)
        return results

    def clear_search_history(self, user_id: str) -> int:
        with self.transaction() as connection:
            return connection.execute(
                "DELETE FROM public.search_history WHERE user_id=%s", (user_id,)
            ).rowcount

    def record_ingestion_run(
        self,
        transformation_version: str,
        dry_run: bool,
        report: dict[str, Any],
        status: str = "completed",
    ) -> dict[str, Any]:
        from psycopg.types.json import Jsonb

        version = str(report["dataset_version"])
        digest = str(report["content_hash"])
        now = datetime.now(UTC)
        with self.transaction() as connection:
            previous = connection.execute(
                "SELECT id FROM public.dataset_versions WHERE status='active'"
            ).fetchone()
            row = connection.execute(
                """INSERT INTO public.dataset_versions
                (version,status,source_manifest,content_hash,report_json,record_count,validated_at,activated_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT(version) DO UPDATE SET report_json=excluded.report_json,
                  record_count=excluded.record_count,validated_at=excluded.validated_at
                RETURNING id""",
                (
                    version,
                    "validated" if dry_run else "staged",
                    Jsonb({"transformation_version": transformation_version}),
                    digest,
                    Jsonb(report),
                    int(report.get("accepted_count", 0)),
                    now,
                    None,
                ),
            ).fetchone()
            dataset_id = row["id"]
            if not dry_run:
                connection.execute(
                    "UPDATE public.dataset_versions SET status='retired',retired_at=%s WHERE status='active' AND id<>%s",
                    (now, dataset_id),
                )
                connection.execute(
                    "UPDATE public.dataset_versions SET status='active',activated_at=%s WHERE id=%s",
                    (now, dataset_id),
                )
            run_status = "validated" if dry_run else "promoted"
            run = connection.execute(
                """INSERT INTO public.ingestion_runs
                (target_dataset_version_id,previous_dataset_version_id,status,dry_run,
                 transformation_version,attempt_count,staged_count,promoted_count,
                 quarantined_count,error_count,report_json,started_at,completed_at)
                VALUES (%s,%s,%s,%s,%s,1,%s,%s,%s,0,%s,%s,%s) RETURNING id,created_at""",
                (
                    dataset_id,
                    previous["id"] if previous and previous["id"] != dataset_id else None,
                    run_status,
                    dry_run,
                    transformation_version,
                    int(report.get("accepted_count", 0)) + int(report.get("quarantined_count", 0)),
                    0 if dry_run else int(report.get("accepted_count", 0)),
                    int(report.get("quarantined_count", 0)),
                    Jsonb(report),
                    now,
                    now,
                ),
            ).fetchone()
        return {
            "id": str(run["id"]),
            "status": run_status,
            "dry_run": dry_run,
            "report": report,
            "created_at": run["created_at"].isoformat(),
        }

    def list_dataset_versions(self) -> list[dict[str, Any]]:
        with self.transaction() as connection:
            rows = connection.execute(
                "SELECT id,version,content_hash,record_count,status,report_json,created_at FROM public.dataset_versions ORDER BY created_at DESC"
            ).fetchall()
        values = []
        for row in rows:
            value = _plain(dict(row))
            value["report"] = value.pop("report_json")
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
        now_epoch = int(datetime.now(UTC).timestamp())
        with self.transaction() as connection:
            connection.execute(
                "DELETE FROM public.revoked_access_tokens WHERE expires_at <= %s", (now_epoch,)
            )
            connection.execute(
                """INSERT INTO public.revoked_access_tokens(jti,user_id,expires_at)
                VALUES (%s,%s,%s) ON CONFLICT(jti) DO NOTHING""",
                (jti, user_id, expires_at),
            )

    def is_token_revoked(self, jti: str) -> bool:
        with self.transaction() as connection:
            row = connection.execute(
                "SELECT 1 FROM public.revoked_access_tokens WHERE jti=%s AND expires_at>%s",
                (jti, int(datetime.now(UTC).timestamp())),
            ).fetchone()
        return row is not None

    def hybrid_candidates(
        self,
        query_text: str,
        query_vector: Any,
        limit: int,
    ) -> dict[str, tuple[float, float]]:
        """Retrieve a bounded union of pgvector and PostgreSQL FTS candidates."""

        vector = [float(value) for value in query_vector]
        if len(vector) != 384 or not all(math.isfinite(value) for value in vector):
            raise ValueError("The active retrieval vector must contain 384 finite values")
        norm = math.sqrt(sum(value * value for value in vector))
        if norm <= 0:
            raise ValueError("The active retrieval vector must have a non-zero norm")
        vector_literal = "[" + ",".join(f"{value:.9g}" for value in vector) + "]"
        candidate_limit = max(1, min(int(limit), 1_000))
        query_text = query_text[:2_000]
        with self.transaction() as connection:
            rows = connection.execute(
                """WITH query_input AS (
                       SELECT %s::vector AS embedding,
                              websearch_to_tsquery('simple'::regconfig, %s) AS terms,
                              lower(%s) AS normalized_query
                   ),
                   semantic AS (
                       SELECT embedding.movie_id,
                              GREATEST(0::double precision,
                                  1 - (embedding.embedding <=> query_input.embedding)
                              ) AS semantic_score,
                              0::double precision AS lexical_score
                       FROM public.movie_embeddings AS embedding
                       JOIN public.movies AS movie ON movie.id = embedding.movie_id
                       CROSS JOIN query_input
                       WHERE embedding.is_active
                         AND movie.archived_at IS NULL
                         AND movie.data_quality_status IN ('pending', 'validated')
                       ORDER BY embedding.embedding <=> query_input.embedding
                       LIMIT %s
                   ),
                   lexical AS (
                       SELECT movie.id AS movie_id,
                              0::double precision AS semantic_score,
                              GREATEST(
                                  ts_rank_cd(movie.search_document, query_input.terms, 32),
                                  similarity(movie.normalized_title, query_input.normalized_query)
                              )::double precision AS lexical_score
                       FROM public.movies AS movie
                       CROSS JOIN query_input
                       WHERE movie.archived_at IS NULL
                         AND movie.data_quality_status IN ('pending', 'validated')
                         AND (
                             movie.search_document @@ query_input.terms
                             OR similarity(movie.normalized_title, query_input.normalized_query) >= 0.18
                         )
                       ORDER BY lexical_score DESC, movie.data_quality_confidence DESC
                       LIMIT %s
                   ),
                   candidates AS (
                       SELECT * FROM semantic
                       UNION ALL
                       SELECT * FROM lexical
                   )
                   SELECT movie_id,
                          MAX(semantic_score) AS semantic_score,
                          MAX(lexical_score) AS lexical_score
                   FROM candidates
                   GROUP BY movie_id
                   ORDER BY MAX(semantic_score) + MAX(lexical_score) DESC, movie_id
                   LIMIT %s""",
                (
                    vector_literal,
                    query_text,
                    query_text,
                    candidate_limit,
                    candidate_limit,
                    candidate_limit,
                ),
            ).fetchall()
        return {
            str(row["movie_id"]): (
                float(row["semantic_score"] or 0),
                float(row["lexical_score"] or 0),
            )
            for row in rows
        }

    def sync_catalog(
        self,
        catalog: Catalog,
        model_name: str,
        model_version: str,
        embeddings: Any | None = None,
    ) -> dict[str, Any]:
        """Idempotently promote the bundled seed catalog into canonical tables."""

        from psycopg.types.json import Jsonb

        source_hash = hashlib.sha256(catalog.source_path.read_bytes()).hexdigest()
        now = datetime.now(UTC)
        with self.transaction() as connection:
            existing = connection.execute(
                "SELECT id FROM public.dataset_versions WHERE version=%s",
                (catalog.dataset_version,),
            ).fetchone()
            if existing:
                dataset_id = existing["id"]
                connection.execute(
                    "UPDATE public.dataset_versions SET report_json=%s,record_count=%s,validated_at=COALESCE(validated_at,%s) WHERE id=%s",
                    (Jsonb(catalog.validation_report), len(catalog.movies), now, dataset_id),
                )
            else:
                connection.execute(
                    "UPDATE public.dataset_versions SET status='retired',retired_at=%s WHERE status='active'",
                    (now,),
                )
                dataset_id = connection.execute(
                    """INSERT INTO public.dataset_versions
                    (version,status,source_manifest,content_hash,report_json,record_count,validated_at,activated_at)
                    VALUES (%s,'active',%s,%s,%s,%s,%s,%s) RETURNING id""",
                    (
                        catalog.dataset_version,
                        Jsonb(
                            {
                                "source": str(catalog.source_path.name),
                                "transformation_version": "v2-import-1",
                            }
                        ),
                        source_hash,
                        Jsonb(catalog.validation_report),
                        len(catalog.movies),
                        now,
                        now,
                    ),
                ).fetchone()["id"]
            connection.execute(
                "UPDATE public.dataset_versions SET status='retired',retired_at=%s WHERE status='active' AND id<>%s",
                (now, dataset_id),
            )
            connection.execute(
                "UPDATE public.dataset_versions SET status='active',activated_at=COALESCE(activated_at,%s),retired_at=NULL WHERE id=%s",
                (now, dataset_id),
            )
            # Archive rows removed by a newer dataset before inserting new
            # identities, which also releases the partial identity constraint.
            connection.execute(
                "UPDATE public.movies SET archived_at=%s WHERE dataset_version_id<>%s AND archived_at IS NULL",
                (now, dataset_id),
            )

            for movie in catalog.movies:
                status = movie.data_quality_status
                if status not in {"pending", "validated", "quarantined", "rejected"}:
                    status = "pending"
                metadata = {
                    "genres": list(movie.genres),
                    "themes": list(movie.themes),
                    "director": movie.director,
                    "cast": list(movie.cast_members),
                    "provenance": movie.provenance,
                    "content_hash": movie.content_hash,
                }
                connection.execute(
                    """INSERT INTO public.movies
                    (id,dataset_version_id,canonical_title,original_title,normalized_title,
                     release_year,runtime_minutes,certificate,overview,language,poster_url,
                     source_url,source_updated_at,data_quality_status,data_quality_confidence,
                     prominence_score,searchable_text,metadata)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT(id) DO UPDATE SET
                      dataset_version_id=excluded.dataset_version_id,
                      canonical_title=excluded.canonical_title,original_title=excluded.original_title,
                      normalized_title=excluded.normalized_title,release_year=excluded.release_year,
                      runtime_minutes=excluded.runtime_minutes,certificate=excluded.certificate,
                      overview=excluded.overview,language=excluded.language,poster_url=excluded.poster_url,
                      source_url=excluded.source_url,source_updated_at=excluded.source_updated_at,
                      data_quality_status=excluded.data_quality_status,
                      data_quality_confidence=excluded.data_quality_confidence,
                      prominence_score=excluded.prominence_score,searchable_text=excluded.searchable_text,
                      metadata=excluded.metadata,archived_at=NULL""",
                    (
                        movie.id,
                        dataset_id,
                        movie.canonical_title,
                        movie.original_title,
                        normalize_text(movie.canonical_title),
                        movie.release_year,
                        movie.runtime_minutes,
                        movie.certificate,
                        movie.overview,
                        movie.language,
                        movie.poster_url,
                        movie.source_url,
                        movie.source_updated_at or None,
                        status,
                        movie.data_quality_score,
                        movie.prominence_score,
                        movie.searchable_text,
                        Jsonb(metadata),
                    ),
                )
                self._sync_taxonomy_and_credits(connection, movie)

            embedding_count = self._sync_embeddings(
                connection,
                catalog,
                dataset_id,
                model_name,
                model_version,
                embeddings,
            )
        return {
            "dataset_version": catalog.dataset_version,
            "movie_count": len(catalog.movies),
            "embedding_count": embedding_count,
            "storage": "postgresql-pgvector",
        }

    @staticmethod
    def _sync_taxonomy_and_credits(connection: Any, movie: Movie) -> None:
        # Association rows reflect the active canonical record exactly; stale
        # generated taxonomy or credits must not survive a source correction.
        connection.execute("DELETE FROM public.movie_genres WHERE movie_id=%s", (movie.id,))
        connection.execute("DELETE FROM public.movie_themes WHERE movie_id=%s", (movie.id,))
        connection.execute("DELETE FROM public.movie_credits WHERE movie_id=%s", (movie.id,))
        for genre in movie.genres:
            slug = _slug(genre)
            genre_id = connection.execute(
                """INSERT INTO public.genres(slug,display_name) VALUES (%s,%s)
                ON CONFLICT(slug) DO UPDATE SET display_name=excluded.display_name RETURNING id""",
                (slug, genre.title()),
            ).fetchone()["id"]
            connection.execute(
                """INSERT INTO public.movie_genres(movie_id,genre_id,confidence)
                VALUES (%s,%s,1) ON CONFLICT(movie_id,genre_id) DO NOTHING""",
                (movie.id, genre_id),
            )
        for theme in movie.themes:
            slug = _slug(theme)
            theme_id = connection.execute(
                """INSERT INTO public.themes(slug,display_name) VALUES (%s,%s)
                ON CONFLICT(slug) DO UPDATE SET display_name=excluded.display_name RETURNING id""",
                (slug, theme.replace("-", " ").title()),
            ).fetchone()["id"]
            connection.execute(
                """INSERT INTO public.movie_themes(movie_id,theme_id,confidence,is_generated)
                VALUES (%s,%s,0.75,TRUE) ON CONFLICT(movie_id,theme_id) DO NOTHING""",
                (movie.id, theme_id),
            )
        credits = [(movie.director, "director", 0)] if movie.director else []
        credits.extend(
            (name, "actor", order) for order, name in enumerate(movie.cast_members, start=1)
        )
        for name, role, order in credits:
            normalized = normalize_text(name)
            person_id = uuid.uuid5(PERSON_NAMESPACE, normalized)
            connection.execute(
                """INSERT INTO public.people(id,name,normalized_name)
                VALUES (%s,%s,%s) ON CONFLICT(id) DO UPDATE SET name=excluded.name""",
                (person_id, name, normalized),
            )
            connection.execute(
                """INSERT INTO public.movie_credits(movie_id,person_id,role_type,billing_order)
                VALUES (%s,%s,%s,%s) ON CONFLICT DO NOTHING""",
                (movie.id, person_id, role, order),
            )

    @staticmethod
    def _sync_embeddings(
        connection: Any,
        catalog: Catalog,
        dataset_id: Any,
        model_name: str,
        model_version: str,
        embeddings: Any | None = None,
    ) -> int:
        matrix = embeddings if embeddings is not None else catalog.source_embeddings
        if (
            matrix is None
            or getattr(matrix, "ndim", 0) != 2
            or matrix.shape != (len(catalog.movies), 384)
        ):
            return 0
        connection.execute(
            "UPDATE public.embedding_model_versions SET is_active=FALSE WHERE is_active"
        )
        model_id = connection.execute(
            """INSERT INTO public.embedding_model_versions
            (provider,model_name,model_version,dimension,input_template,metadata,is_active)
            VALUES (%s,%s,%s,384,%s,'{}'::jsonb,TRUE)
            ON CONFLICT(provider,model_name,model_version) DO UPDATE SET is_active=TRUE
            RETURNING id""",
            (
                "sentence-transformers" if "sentence-transformers" in model_name else "tamiltrove",
                model_name,
                model_version,
                "{canonical_title} {genres} {themes} {overview}",
            ),
        ).fetchone()["id"]
        count = 0
        for index, movie in enumerate(catalog.movies):
            vector = matrix[index]
            norm = math.sqrt(sum(float(value) ** 2 for value in vector))
            if not math.isfinite(norm) or norm <= 0:
                continue
            literal = "[" + ",".join(f"{float(value):.9g}" for value in vector) + "]"
            connection.execute(
                "UPDATE public.movie_embeddings SET is_active=FALSE WHERE movie_id=%s AND is_active",
                (movie.id,),
            )
            connection.execute(
                """INSERT INTO public.movie_embeddings
                (movie_id,model_version_id,dataset_version_id,content_sha256,embedding,is_active)
                VALUES (%s,%s,%s,%s,%s::vector,TRUE)
                ON CONFLICT(movie_id,model_version_id,content_sha256)
                DO UPDATE SET dataset_version_id=excluded.dataset_version_id,
                  embedding=excluded.embedding,is_active=TRUE""",
                (movie.id, model_id, dataset_id, bytes.fromhex(movie.content_hash), literal),
            )
            count += 1
        return count
