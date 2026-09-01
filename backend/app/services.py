from __future__ import annotations

import math
import time
from dataclasses import dataclass
from typing import Any

from .catalog import Catalog, Movie
from .config import Settings
from .errors import AuthenticationError, AuthorizationError, NotFoundError
from .normalization import normalize_query
from .observability import MetricRegistry, Tracer, stage_timer
from .ranking import SearchIndex, UserSignals, build_explanation
from .recommendation import ALSRecommender
from .schemas import SearchRequest, SearchSort
from .security import (
    DUMMY_PASSWORD_HASH,
    hash_password,
    issue_token,
    validate_password_strength,
    verify_password,
)


@dataclass(slots=True)
class ServiceContainer:
    settings: Settings
    catalog: Catalog
    store: Any
    index: SearchIndex
    metrics: MetricRegistry
    tracer: Tracer
    ingestion: Any
    recommender: ALSRecommender | None = None


class AuthService:
    def __init__(self, container: ServiceContainer):
        self.container = container

    def _profile(self, user: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": user["id"],
            "email": user["email"],
            "display_name": user["display_name"],
            "locale": user["locale"],
            "preferences": user["preferences"],
            "privacy": user["privacy"],
            "is_admin": user["email"].casefold() in self.container.settings.admin_emails,
            "created_at": user["created_at"],
            "updated_at": user["updated_at"],
        }

    def register(self, email: str, password: str, display_name: str, locale: str) -> dict[str, Any]:
        try:
            validate_password_strength(password, email)
        except ValueError as exc:
            from .errors import AppError

            raise AppError(422, "weak_password", str(exc)) from exc
        user = self.container.store.create_user(
            email, hash_password(password), display_name, locale
        )
        return self.auth_response(user)

    def login(self, email: str, password: str) -> dict[str, Any]:
        user = self.container.store.get_user_by_email(email)
        # Always perform a KDF to reduce account enumeration timing differences.
        expected = user["password_hash"] if user else DUMMY_PASSWORD_HASH
        valid = verify_password(password, expected)
        if not user or not valid:
            raise AuthenticationError("Email or password is incorrect")
        return self.auth_response(user)

    def auth_response(self, user: dict[str, Any]) -> dict[str, Any]:
        settings = self.container.settings
        return {
            "access_token": issue_token(
                user["id"], settings.secret_key, settings.auth_token_ttl_seconds
            ),
            "token_type": "bearer",
            "expires_in": settings.auth_token_ttl_seconds,
            "profile": self._profile(user),
        }

    def profile(self, user_id: str) -> dict[str, Any]:
        user = self.container.store.get_user(user_id)
        if not user:
            raise AuthenticationError()
        return self._profile(user)

    def update_profile(self, user_id: str, changes: dict[str, Any]) -> dict[str, Any]:
        if changes.pop("reset_interactions", False):
            self.container.store.clear_interactions(user_id)
        return self._profile(self.container.store.update_user(user_id, changes))


def _user_signals(container: ServiceContainer, user_id: str | None) -> UserSignals:
    if not user_id:
        return UserSignals()
    profile = container.store.get_user(user_id)
    interactions = container.store.list_interactions(user_id, limit=10_000)
    if not profile or not profile["privacy"].get("use_interactions_for_recommendations", True):
        interactions = []
    positive, negative, dismissed, watched = set(), set(), set(), set()
    for interaction in interactions:
        kind, movie_id, value = (
            interaction["type"],
            interaction["movie_id"],
            interaction.get("value"),
        )
        if kind in {"like", "save"} or (kind == "rating" and (value or 0) >= 3.5):
            positive.add(movie_id)
        if kind == "dislike" or (kind == "rating" and (value or 5) <= 2.0):
            negative.add(movie_id)
        if kind == "dismiss":
            dismissed.add(movie_id)
            negative.add(movie_id)
        if kind == "viewed":
            watched.add(movie_id)
    preferences = profile["preferences"] if profile else {}
    return UserSignals(
        favorite_genres=tuple(preferences.get("favorite_genres", [])),
        favorite_themes=tuple(preferences.get("favorite_themes", [])),
        hidden_gem_preference=float(preferences.get("hidden_gem_preference", 0.5)),
        positive_movie_ids=tuple(positive | set(preferences.get("onboarding_movie_ids", []))),
        negative_movie_ids=tuple(negative),
        dismissed_movie_ids=tuple(dismissed),
        watched_movie_ids=tuple(watched),
    )


def movie_payload(
    movie: Movie, user_state: dict[str, Any] | None = None, provenance: bool = False
) -> dict[str, Any]:
    value = movie.to_dict()
    value["provenance"] = value.get("provenance") if provenance else None
    value["user_state"] = user_state
    value.pop("content_hash", None)
    value.pop("source_index", None)
    return value


def interaction_state(
    container: ServiceContainer, user_id: str | None
) -> dict[str, dict[str, Any]]:
    if not user_id:
        return {}
    values: dict[str, dict[str, Any]] = {}
    for item in container.store.list_interactions(user_id, limit=10_000):
        state = values.setdefault(item["movie_id"], {})
        kind = item["type"]
        if kind == "save":
            state["in_watchlist"] = True
        elif kind == "rating":
            state["rating"] = item["value"]
        else:
            state[kind] = True
    return values


class SearchService:
    def __init__(self, container: ServiceContainer):
        self.container = container

    def search(
        self,
        request: SearchRequest,
        request_id: str,
        user_id: str | None = None,
        seed_movie_id: str | None = None,
    ) -> dict[str, Any]:
        started = time.perf_counter()
        
        ranking_version = self.container.settings.ranking_version
        if user_id:
            # A/B Testing routing based on user hash
            if hash(user_id) % 100 < 50:
                ranking_version = "v3-cross-encoder"
            else:
                ranking_version = "v2-local-hybrid-1"
                
        timings: dict[str, float] = {}
        with self.container.tracer.span(
            "search.request",
            {
                "search.language": "pending",
                "ranking.version": ranking_version,
            },
        ):
            with stage_timer(timings, "normalize"):
                query = normalize_query(request.query)
            with stage_timer(timings, "profile"):
                signals = _user_signals(self.container, user_id)
            with (
                self.container.tracer.span("search.retrieve_and_rerank"),
                stage_timer(timings, "retrieve_and_rerank"),
            ):
                candidate_provider = None
                if hasattr(self.container.store, "hybrid_candidates"):

                    def retrieve_candidates(
                        query_text: str,
                        query_vector: Any,
                        limit: int,
                    ) -> dict[str, tuple[float, float]]:
                        with (
                            self.container.tracer.span("search.database_hybrid_retrieval"),
                            stage_timer(timings, "database_retrieval"),
                        ):
                            started_database = time.perf_counter()
                            values = self.container.store.hybrid_candidates(
                                query_text,
                                query_vector,
                                limit,
                            )
                            self.container.metrics.observe(
                                "tamiltrove_database_query_duration_seconds",
                                time.perf_counter() - started_database,
                                {"operation": "hybrid_candidates"},
                            )
                            return values

                    candidate_provider = retrieve_candidates
                ranked, hints, query_coordinates = self.container.index.rank(
                    query,
                    request,
                    signals,
                    seed_movie_id=seed_movie_id,
                    candidate_provider=candidate_provider,
                    ranking_version=ranking_version,
                )
            total = len(ranked)
            offset = (request.page - 1) * request.page_size
            page_items = ranked[offset : offset + request.page_size]
            states = interaction_state(self.container, user_id)
            with stage_timer(timings, "explain_and_serialize"):
                results = []
                for item in page_items:
                    payload = movie_payload(item.movie, states.get(item.movie.id))
                    scores = {
                        "semantic": item.semantic,
                        "lexical": item.lexical,
                        "preference": item.preference,
                        "quality": item.quality,
                        "hidden_gem": item.hidden_gem,
                        "final": item.final,
                    }
                    payload.update(
                        {
                            "index": item.movie.source_index,
                            "similarity_score": item.semantic,
                            "lexical_score": item.lexical,
                            "final_score": item.final,
                            "plot_x": item.plot_x,
                            "plot_y": item.plot_y,
                            "scores": scores,
                            "explanation": build_explanation(item, query, bool(user_id)),
                            "debug": (
                                {
                                    "semantic_backend": self.container.index.semantic_backend,
                                    "expanded_terms": list(query.expanded_terms),
                                    "ranking_weights": {
                                        "semantic": self.container.settings.ranking_semantic_weight,
                                        "lexical": self.container.settings.ranking_lexical_weight,
                                        "preference": self.container.settings.ranking_preference_weight,
                                        "quality": self.container.settings.ranking_quality_weight,
                                        "hidden_gem": self.container.settings.ranking_hidden_gem_weight,
                                    },
                                }
                                if request.include_debug and self.container.settings.debug_scores
                                else None
                            ),
                        }
                    )
                    results.append(payload)
        elapsed_ms = round((time.perf_counter() - started) * 1000, 3)
        timings["total"] = elapsed_ms
        total_pages = math.ceil(total / request.page_size) if total else 0
        response = {
            "query": query.original,
            "normalized_query": query.normalized,
            "detected_language": query.detected_language,
            "query_plot": (
                {"x": query_coordinates[0], "y": query_coordinates[1]}
                if query_coordinates[0] is not None and query_coordinates[1] is not None
                else None
            ),
            "results": results,
            "meta": {
                "request_id": request_id,
                "ranking_version": ranking_version,
                "dataset_version": self.container.catalog.dataset_version,
                "total": total,
                "page": request.page,
                "page_size": request.page_size,
                "total_pages": total_pages,
                "latency_ms": elapsed_ms,
                "inferred_filters": hints,
                "personalized": bool(user_id),
                "stage_timings_ms": timings,
                "experiment": {
                    "ranking_version": ranking_version,
                    "feature_flags": {
                        "transformer": self.container.settings.enable_transformer,
                        "diversity": (
                            request.diversity or self.container.settings.ranking_diversity
                        )
                        > 0,
                        "personalization": bool(user_id),
                    },
                },
            },
        }
        labels = {
            "language": query.detected_language,
            "ranking_version": ranking_version,
        }
        self.container.metrics.increment("tamiltrove_search_requests_total", labels)
        self.container.metrics.observe(
            "tamiltrove_search_duration_seconds", elapsed_ms / 1000, labels
        )
        if not results:
            self.container.metrics.increment("tamiltrove_search_zero_results_total", labels)
        if user_id:
            profile = self.container.store.get_user(user_id)
            if profile and profile["privacy"].get("store_search_history", True):
                self.container.store.add_search_history(
                    user_id,
                    query.original,
                    query.normalized,
                    query.detected_language,
                    request.filters.model_dump(mode="json"),
                    [result["id"] for result in results],
                    ranking_version,
                    elapsed_ms,
                )
        return response

    def recommendations(
        self, request_id: str, user_id: str, surface: str, page: int, page_size: int
    ) -> dict[str, Any]:
        if surface == "for_you" and self.container.recommender and self.container.recommender.model:
            als_ids = self.container.recommender.recommend(user_id, k=page_size)
            if als_ids:
                results = []
                states = interaction_state(self.container, user_id)
                for mid in als_ids:
                    movie = self.container.catalog.get(mid)
                    if movie:
                        payload = movie_payload(movie, states.get(mid))
                        payload["scores"] = {"semantic": 0, "lexical": 0, "preference": 1, "quality": 1, "hidden_gem": 0, "final": 1}
                        payload["final_score"] = 1.0
                        payload["explanation"] = {"summary": "Recommended based on your activity", "confidence": "high", "evidence": []}
                        results.append(payload)
                return {
                    "query": "", "normalized_query": "", "detected_language": "en", "query_plot": None,
                    "results": results,
                    "surface": surface,
                    "meta": {
                        "total": len(results), "page": 1, "page_size": page_size, "total_pages": 1,
                        "latency_ms": 0, "inferred_filters": {}, "personalized": True, "stage_timings_ms": {},
                        "request_id": request_id, "ranking_version": self.container.settings.ranking_version,
                        "experiment": {"ranking_version": self.container.settings.ranking_version}
                    }
                }

        profile = self.container.store.get_user(user_id)
        if not profile:
            raise AuthenticationError()
        preferences = profile["preferences"]
        query = " ".join(
            (*preferences.get("favorite_genres", []), *preferences.get("favorite_themes", []))
        )
        sort = SearchSort.hidden_gems if surface == "hidden_gems" else SearchSort.relevance
        if surface in {"recent", "recently_added"}:
            sort = SearchSort.year_desc
        request = SearchRequest(
            query=query,
            sort=sort,
            page=page,
            page_size=page_size,
            beta=2.0 if surface == "hidden_gems" else 0.8,
        )
        result = self.search(request, request_id, user_id)
        result["surface"] = surface
        return result

    def similar(
        self, movie_id: str, request_id: str, page: int, page_size: int, user_id: str | None
    ) -> dict[str, Any]:
        movie = self.container.catalog.get(movie_id)
        if not movie:
            raise NotFoundError("Movie")
        query = " ".join((movie.genre, " ".join(movie.themes), movie.overview[:700]))
        request = SearchRequest(query=query, page=page, page_size=page_size, diversity=0.12)
        response = self.search(request, request_id, user_id, seed_movie_id=movie_id)
        response["seed_movie"] = movie_payload(movie)
        for item in response["results"]:
            shared_genres = sorted(set(movie.genres) & set(item["genres"]))
            if shared_genres:
                item["explanation"] = {
                    "summary": f"Similar to {movie.title} through shared {', '.join(shared_genres)} elements.",
                    "evidence": [
                        {
                            "type": "shared_genre",
                            "value": ", ".join(shared_genres),
                            "source_field": "genres",
                            "contribution": 0.2,
                        }
                    ],
                    "confidence": "high",
                }
        return response


class CollectionService:
    def __init__(self, container: ServiceContainer):
        self.container = container

    def _owned(self, collection_id: str, user_id: str) -> dict[str, Any]:
        collection = self.container.store.get_collection(collection_id)
        if not collection:
            raise NotFoundError("Collection")
        if collection["owner_id"] != user_id:
            raise AuthorizationError()
        return collection

    def hydrate(self, collection: dict[str, Any], public: bool = False) -> dict[str, Any]:
        items = []
        for row in self.container.store.collection_items(collection["id"]):
            movie = self.container.catalog.get(row["movie_id"])
            if movie:
                items.append(
                    {
                        "movie": movie_payload(movie),
                        "position": row["position"],
                        "note": row.get("note"),
                        "added_at": row["added_at"],
                    }
                )
        result = dict(collection)
        result["items"] = items
        result["item_count"] = len(items)
        if public:
            result["owner_id"] = None
            # Share secrets are never reflected from the public endpoint.
            result["share_token"] = None
        return result

    def get(self, collection_id: str, user_id: str | None) -> dict[str, Any]:
        collection = self.container.store.get_collection(collection_id)
        if not collection:
            raise NotFoundError("Collection")
        if collection["visibility"] != "public" and collection["owner_id"] != user_id:
            raise NotFoundError("Collection")
        return self.hydrate(collection, public=collection["owner_id"] != user_id)

    def shared(self, token: str) -> dict[str, Any]:
        collection = self.container.store.get_shared_collection(token)
        if not collection:
            raise NotFoundError("Shared collection")
        return self.hydrate(collection, public=True)

    def add_item(
        self, collection_id: str, user_id: str, movie_id: str, position: int | None
    ) -> dict[str, Any]:
        self._owned(collection_id, user_id)
        if not self.container.catalog.get(movie_id):
            raise NotFoundError("Movie")
        self.container.store.add_collection_item(collection_id, movie_id, position)
        return self.hydrate(self.container.store.get_collection(collection_id))

    def list_owned(self, user_id: str) -> list[dict[str, Any]]:
        return [
            self.hydrate(collection)
            for collection in self.container.store.list_collections(user_id)
        ]

    def create(self, user_id: str, values: dict[str, Any]) -> dict[str, Any]:
        collection = self.container.store.create_collection(
            user_id,
            values["name"],
            values.get("description", ""),
            values.get("visibility", "private"),
        )
        return self.hydrate(collection)

    def update(self, collection_id: str, user_id: str, changes: dict[str, Any]) -> dict[str, Any]:
        self._owned(collection_id, user_id)
        return self.hydrate(self.container.store.update_collection(collection_id, changes))

    def delete(self, collection_id: str, user_id: str) -> bool:
        self._owned(collection_id, user_id)
        return self.container.store.delete_collection(collection_id)

    def share(self, collection_id: str, user_id: str) -> dict[str, Any]:
        self._owned(collection_id, user_id)
        return self.hydrate(self.container.store.share_collection(collection_id))

    def remove_item(self, collection_id: str, user_id: str, movie_id: str) -> dict[str, Any]:
        self._owned(collection_id, user_id)
        self.container.store.remove_collection_item(collection_id, movie_id)
        return self.hydrate(self.container.store.get_collection(collection_id))
