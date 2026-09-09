"""TamilTrove V4 — Agent Tool Registry.

Exposes typed, callable tools for the autonomous RecommendationAgent:
- search_movies: Execute hybrid multilingual + cross-modal search
- get_movie_details: Look up complete film metadata
- get_similar_movies: Find nearest-neighbor titles
- get_user_preferences: Read user taste profile and history
- record_feedback: Save likes, ratings, or dismissals mid-conversation
- add_to_collection: Add recommended title directly to a user's collection
"""

from __future__ import annotations

import logging
from typing import Any

from .schemas import CollectionItemRequest, InteractionType, SearchFilters, SearchRequest
from .services import CollectionService, SearchService, ServiceContainer

logger = logging.getLogger("tamiltrove.agent_tools")


class AgentToolRegistry:
    """Type-safe tool execution engine grounded in TamilTrove service container."""

    def __init__(self, container: ServiceContainer):
        self.container = container
        self.search_service = SearchService(container)
        self.collection_service = CollectionService(container)

    def search_movies(
        self,
        query: str,
        filters: dict[str, Any] | None = None,
        visual_query: str = "",
        audio_query: str = "",
        alpha: float = 0.58,
        page_size: int = 5,
        user_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Search the validated Tamil cinema catalog using hybrid textual and multimodal queries."""
        filter_obj = SearchFilters(**(filters or {}))
        request = SearchRequest(
            query=query,
            filters=filter_obj,
            visual_query=visual_query,
            audio_query=audio_query,
            alpha=alpha,
            page_size=min(page_size, 10),
        )
        response = self.search_service.search(request, request_id="agent-tool-search", user_id=user_id)
        results = []
        for r in response.get("results", []):
            results.append(
                {
                    "id": r.get("id"),
                    "title": r.get("title"),
                    "release_year": r.get("release_year"),
                    "genres": r.get("genres", []),
                    "themes": r.get("themes", []),
                    "director": r.get("director"),
                    "cast": r.get("cast"),
                    "overview": r.get("overview", "")[:250],
                    "poster_url": r.get("poster_url"),
                    "similarity_score": r.get("similarity_score"),
                    "final_score": r.get("final_score"),
                    "explanation": r.get("explanation", {}).get("summary", ""),
                    "visual_tone": r.get("visual_palette", {}).get("aesthetic_tags", []),
                    "audio_mood": r.get("audio_profile", {}).get("mood", ""),
                }
            )
        return results

    def get_movie_details(self, movie_id: str) -> dict[str, Any] | None:
        """Retrieve full verified metadata and multimodal profile for a specific film ID or title."""
        for movie in self.container.catalog.movies:
            if movie.id == movie_id or movie.canonical_title.casefold() == movie_id.casefold():
                data = movie.to_dict()
                data["index"] = movie.source_index
                return data
        return None

    def get_similar_movies(self, movie_id: str, limit: int = 5) -> list[dict[str, Any]]:
        """Retrieve films structurally and semantically similar to a given movie."""
        target_movie = None
        for movie in self.container.catalog.movies:
            if movie.id == movie_id or movie.canonical_title.casefold() == movie_id.casefold():
                target_movie = movie
                break
        if not target_movie:
            return []

        search_req = SearchRequest(
            query=f"{target_movie.genre} {target_movie.director}",
            page_size=limit + 1,
        )
        response = self.search_service.search(
            search_req,
            request_id="agent-similar-search",
            seed_movie_id=target_movie.id,
        )
        results = []
        for r in response.get("results", []):
            if r.get("id") != target_movie.id:
                results.append(
                    {
                        "id": r.get("id"),
                        "title": r.get("title"),
                        "release_year": r.get("release_year"),
                        "genres": r.get("genres", []),
                        "director": r.get("director"),
                        "overview": r.get("overview", "")[:200],
                        "similarity_score": r.get("similarity_score"),
                    }
                )
        return results[:limit]

    def get_user_preferences(self, user_id: str) -> dict[str, Any]:
        """Read the user's taste profile, liked genres, and saved movies."""
        user = self.container.store.get_user(user_id)
        if not user:
            return {"favorite_genres": [], "favorite_themes": [], "positive_movies": []}

        interactions = self.container.store.list_interactions(user_id, limit=50)
        positive_movie_ids = [
            i["movie_id"] for i in interactions if i["type"] in {"like", "save", "rating"}
        ]
        positive_titles = []
        for mid in positive_movie_ids[:5]:
            for m in self.container.catalog.movies:
                if m.id == mid:
                    positive_titles.append(m.canonical_title)
                    break

        prefs = user.get("preferences", {})
        return {
            "favorite_genres": prefs.get("favorite_genres", []),
            "favorite_themes": prefs.get("favorite_themes", []),
            "hidden_gem_preference": prefs.get("hidden_gem_preference", 0.5),
            "positive_movies": positive_titles,
        }

    def record_feedback(
        self, user_id: str, movie_id: str, feedback_type: str, value: float | None = None
    ) -> dict[str, Any]:
        """Record user interaction mid-conversation."""
        try:
            itype = InteractionType(feedback_type)
        except ValueError:
            itype = InteractionType.like

        item = self.container.store.record_interaction(
            user_id, movie_id, itype.value, value, {"source": "agent"}
        )
        return {"status": "success", "interaction_id": item["id"], "type": itype.value}

    def add_to_collection(
        self, user_id: str, collection_id: str, movie_id: str
    ) -> dict[str, Any]:
        """Add a recommended film directly to an authenticated user collection."""
        req = CollectionItemRequest(movie_id=movie_id)
        res = self.collection_service.add_item(user_id, collection_id, req)
        return {"status": "success", "movie_title": res["movie"]["title"], "collection_id": collection_id}
