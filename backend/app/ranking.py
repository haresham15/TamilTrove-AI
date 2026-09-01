from __future__ import annotations

import math
import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import numpy as np
from sklearn.decomposition import TruncatedSVD
from sklearn.feature_extraction.text import HashingVectorizer, TfidfVectorizer
from sklearn.preprocessing import normalize

from .catalog import Catalog, Movie
from .config import Settings
from .normalization import NormalizedQuery, normalize_text, parse_query_hints
from .schemas import SearchFilters, SearchRequest, SearchSort


@dataclass(slots=True)
class UserSignals:
    favorite_genres: tuple[str, ...] = ()
    favorite_themes: tuple[str, ...] = ()
    hidden_gem_preference: float = 0.5
    positive_movie_ids: tuple[str, ...] = ()
    negative_movie_ids: tuple[str, ...] = ()
    dismissed_movie_ids: tuple[str, ...] = ()
    watched_movie_ids: tuple[str, ...] = ()


@dataclass(slots=True)
class RankedMovie:
    movie: Movie
    semantic: float
    lexical: float
    preference: float
    quality: float
    hidden_gem: float
    final: float
    evidence: list[dict[str, Any]]
    semantic_vector: np.ndarray
    plot_x: float | None = None
    plot_y: float | None = None


def cosine_rows(matrix: Any, vector: Any) -> np.ndarray:
    values = matrix @ vector.T
    if hasattr(values, "toarray"):
        values = values.toarray()
    return np.asarray(values).reshape(-1).astype(float)


def reciprocal_rank_fusion(
    semantic: np.ndarray,
    lexical: np.ndarray,
    semantic_weight: float,
    lexical_weight: float,
    k: int = 60,
) -> np.ndarray:
    if semantic.shape != lexical.shape:
        raise ValueError("Score vectors must have the same shape")
    semantic_order = np.argsort(-semantic, kind="stable")
    lexical_order = np.argsort(-lexical, kind="stable")
    semantic_rank = np.empty_like(semantic_order)
    lexical_rank = np.empty_like(lexical_order)
    semantic_rank[semantic_order] = np.arange(len(semantic_order)) + 1
    lexical_rank[lexical_order] = np.arange(len(lexical_order)) + 1
    fused = semantic_weight / (k + semantic_rank) + lexical_weight / (k + lexical_rank)
    maximum = fused.max(initial=0.0)
    return fused / maximum if maximum else fused


def hidden_gem_score(prominence: float, relevance: float, preference: float) -> float:
    obscurity = 1.0 - max(0.0, min(1.0, prominence))
    return max(0.0, relevance) * obscurity * max(0.0, min(1.0, preference))


def phrase_in_query(phrase: str, query: str) -> bool:
    """Match normalized metadata as a complete phrase, never as a substring.

    This matters for legitimate one-character film titles such as ``I``: a
    substring check would otherwise boost that title for nearly every English
    query containing the letter i.
    """

    if not phrase or not query:
        return False
    return bool(re.search(rf"(?<!\w){re.escape(phrase)}(?!\w)", query, re.UNICODE))


CandidateProvider = Callable[[str, np.ndarray, int], dict[str, tuple[float, float]]]


def preference_score(
    movie: Movie,
    signals: UserSignals,
    positive_neighbors: set[str],
    negative_neighbors: set[str],
) -> float:
    genre_matches = len(set(movie.genres) & set(signals.favorite_genres))
    theme_matches = len(set(movie.themes) & set(signals.favorite_themes))
    explicit = 0.0
    if movie.id in signals.positive_movie_ids:
        explicit += 1.0
    if movie.id in signals.negative_movie_ids:
        explicit -= 1.0
    if movie.id in positive_neighbors:
        explicit += 0.35
    if movie.id in negative_neighbors:
        explicit -= 0.35
    return max(-1.0, min(1.0, 0.22 * genre_matches + 0.18 * theme_matches + explicit))


def mmr_rerank(items: list[RankedMovie], diversity: float, limit: int) -> list[RankedMovie]:
    if not items or limit <= 0:
        return []
    diversity = max(0.0, min(1.0, diversity))
    selection_limit = min(limit, len(items))
    vectors = np.vstack([item.semantic_vector for item in items]).astype(np.float32, copy=False)
    relevance = np.asarray([item.final for item in items], dtype=np.float32)
    available = np.ones(len(items), dtype=bool)
    selected_indexes = [0]
    available[0] = False
    maximum_similarity = vectors @ vectors[0]

    while len(selected_indexes) < selection_limit and available.any():
        scores = (1.0 - diversity) * relevance - diversity * np.maximum(
            0.0, maximum_similarity
        )
        scores[~available] = -np.inf
        best_index = int(np.argmax(scores))
        selected_indexes.append(best_index)
        available[best_index] = False
        maximum_similarity = np.maximum(maximum_similarity, vectors @ vectors[best_index])

    return [items[index] for index in selected_indexes]


class SearchIndex:
    """Deterministic local hybrid index; replaceable by a pgvector repository."""

    def __init__(self, catalog: Catalog, settings: Settings):
        self.catalog = catalog
        self.settings = settings
        texts = [movie.searchable_text for movie in catalog.movies]
        self.lexical_vectorizer = TfidfVectorizer(
            analyzer="word",
            ngram_range=(1, 2),
            lowercase=True,
            sublinear_tf=True,
            strip_accents=None,
            max_features=40_000,
        )
        self.lexical_matrix = self.lexical_vectorizer.fit_transform(texts)
        self.char_vectorizer = HashingVectorizer(
            analyzer="char_wb",
            ngram_range=(2, 5),
            lowercase=True,
            n_features=384,
            alternate_sign=False,
            norm="l2",
        )
        self.local_semantic_matrix = self.char_vectorizer.transform(texts)
        self.encoder: Any | None = None
        self.semantic_matrix: Any = self.local_semantic_matrix
        self.semantic_backend = "multilingual-character-fallback"
        self.cross_encoder: Any | None = None
        self.degraded_reasons: list[str] = []
        self.pca_components: np.ndarray | None = None
        self.pca_mean: np.ndarray | None = None
        self.pca_scale = 1.0
        if settings.enable_transformer:
            self._try_transformer()
        self._fit_projection()

    def _try_transformer(self) -> None:
        try:
            from sentence_transformers import CrossEncoder, SentenceTransformer

            encoder = SentenceTransformer(self.settings.model_name)
            dimension = int(encoder.get_sentence_embedding_dimension())
            source = self.catalog.source_embeddings
            bundled_model_compatible = self.settings.model_name.rstrip("/").endswith(
                "all-MiniLM-L6-v2"
            )
            if source is not None and source.shape[1] == dimension and bundled_model_compatible:
                matrix = normalize(np.asarray(source, dtype=np.float32))
            else:
                if source is not None and not bundled_model_compatible:
                    self.degraded_reasons.append("bundled_embeddings_model_mismatch_reembedded")
                matrix = encoder.encode(
                    [movie.searchable_text for movie in self.catalog.movies],
                    normalize_embeddings=True,
                    show_progress_bar=False,
                )
            self.encoder = encoder
            self.semantic_matrix = np.asarray(matrix, dtype=np.float32)
            self.semantic_backend = self.settings.model_name
            
            try:
                self.cross_encoder = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2", max_length=512)
            except Exception as ce_exc:
                self.degraded_reasons.append(f"cross_encoder_unavailable:{type(ce_exc).__name__}")
        except Exception as exc:
            self.degraded_reasons.append(f"transformer_unavailable:{type(exc).__name__}")

    def _fit_projection(self) -> None:
        try:
            projection = TruncatedSVD(
                n_components=2,
                algorithm="randomized",
                n_iter=7,
                random_state=42,
            )
            projected = projection.fit_transform(self.semantic_matrix)
            components = np.asarray(projection.components_, dtype=np.float32)
            mean = np.zeros(components.shape[1], dtype=np.float32)
            scale = float(np.abs(projected).max(initial=1.0))
            self.pca_mean, self.pca_components, self.pca_scale = mean, components, scale or 1.0
        except Exception as exc:
            self.degraded_reasons.append(f"projection_unavailable:{type(exc).__name__}")

    def encode_query(self, query: str) -> tuple[Any, np.ndarray]:
        if self.encoder is not None:
            vector = np.asarray(
                self.encoder.encode([query], normalize_embeddings=True, show_progress_bar=False),
                dtype=np.float32,
            )
            return vector, vector[0]
        sparse = self.char_vectorizer.transform([query])
        return sparse, sparse.toarray()[0]

    def coordinates(self, vector: np.ndarray) -> tuple[float | None, float | None]:
        if (
            self.pca_components is None
            or self.pca_mean is None
            or vector.shape != self.pca_mean.shape
        ):
            return None, None
        point = (vector - self.pca_mean) @ self.pca_components.T
        return (
            round(float(np.clip(point[0] / self.pca_scale, -1, 1)), 4),
            round(float(np.clip(point[1] / self.pca_scale, -1, 1)), 4),
        )

    def movie_vector(self, index: int) -> np.ndarray:
        row = self.semantic_matrix[index]
        if hasattr(row, "toarray"):
            return row.toarray()[0]
        return np.asarray(row)

    def dense_embeddings(self) -> np.ndarray:
        """Return the exact active retrieval matrix for pgvector synchronization."""

        if hasattr(self.semantic_matrix, "toarray"):
            return np.asarray(self.semantic_matrix.toarray(), dtype=np.float32)
        return np.asarray(self.semantic_matrix, dtype=np.float32)

    def _profile_neighbors(
        self,
        positive_ids: tuple[str, ...],
        negative_ids: tuple[str, ...],
        limit: int = 60,
    ) -> tuple[set[str], set[str]]:
        index_by_id = {movie.id: index for index, movie in enumerate(self.catalog.movies)}

        def neighbors(movie_ids: tuple[str, ...]) -> set[str]:
            indexes = [index_by_id[movie_id] for movie_id in movie_ids if movie_id in index_by_id]
            if not indexes:
                return set()
            vectors = np.vstack([self.movie_vector(index) for index in indexes])
            centroid = np.asarray(vectors.mean(axis=0), dtype=np.float32)
            norm = float(np.linalg.norm(centroid))
            if not math.isfinite(norm) or norm <= 0:
                return set()
            centroid /= norm
            similarities = cosine_rows(self.semantic_matrix, centroid)
            ordered = np.argsort(-similarities, kind="stable")
            return {
                self.catalog.movies[index].id
                for index in ordered[:limit]
                if similarities[index] >= 0.18 and self.catalog.movies[index].id not in movie_ids
            }

        return neighbors(positive_ids), neighbors(negative_ids)

    def _matches_filters(
        self,
        movie: Movie,
        filters: SearchFilters,
        hints: dict[str, Any],
        signals: UserSignals,
    ) -> bool:
        year_min = filters.year_min if filters.year_min is not None else hints.get("year_min")
        year_max = filters.year_max if filters.year_max is not None else hints.get("year_max")
        if year_min is not None and (movie.release_year is None or movie.release_year < year_min):
            return False
        if year_max is not None and (movie.release_year is None or movie.release_year > year_max):
            return False
        # Only structured filters are hard constraints. Genre words inferred
        # from plot text remain ranking evidence instead of causing avoidable
        # zero-result searches.
        requested_genres = filters.genres
        if requested_genres and not set(map(normalize_text, requested_genres)) & set(movie.genres):
            return False
        if filters.themes and not set(map(normalize_text, filters.themes)) & set(movie.themes):
            return False
        cast_text = normalize_text(movie.cast)
        if filters.actors and not any(
            normalize_text(actor) in cast_text for actor in filters.actors
        ):
            return False
        director_text = normalize_text(movie.director)
        if filters.directors and not any(
            normalize_text(name) in director_text for name in filters.directors
        ):
            return False
        if filters.runtime_min is not None and (
            movie.runtime_minutes is None or movie.runtime_minutes < filters.runtime_min
        ):
            return False
        if filters.runtime_max is not None and (
            movie.runtime_minutes is None or movie.runtime_minutes > filters.runtime_max
        ):
            return False
        if filters.certificates and (movie.certificate or "").casefold() not in {
            x.casefold() for x in filters.certificates
        }:
            return False
        if filters.prominence_min is not None and movie.prominence_score < filters.prominence_min:
            return False
        if filters.prominence_max is not None and movie.prominence_score > filters.prominence_max:
            return False
        if filters.min_quality is not None and movie.data_quality_score < filters.min_quality:
            return False
        if filters.exclude_dismissed and movie.id in signals.dismissed_movie_ids:
            return False
        return not (filters.exclude_watched and movie.id in signals.watched_movie_ids)

    def rank(
        self,
        query: NormalizedQuery,
        request: SearchRequest,
        signals: UserSignals | None = None,
        seed_movie_id: str | None = None,
        candidate_provider: CandidateProvider | None = None,
        ranking_version: str = "v2-local-hybrid-1",
    ) -> tuple[list[RankedMovie], dict[str, Any], tuple[float | None, float | None]]:
        signals = signals or UserSignals()
        hints = parse_query_hints(query.normalized)
        effective_query = query.normalized.strip()
        if not effective_query:
            profile_terms = " ".join((*signals.favorite_genres, *signals.favorite_themes))
            effective_query = profile_terms or "diverse tamil cinema"
        query_matrix, query_dense = self.encode_query(effective_query)
        semantic = cosine_rows(self.semantic_matrix, query_matrix)
        lexical_query = self.lexical_vectorizer.transform([effective_query])
        lexical = cosine_rows(self.lexical_matrix, lexical_query)

        # PostgreSQL deployments retrieve the bounded candidate set through
        # pgvector and weighted full-text search. The deterministic local
        # matrices remain the development fallback and the reranking feature
        # source, which keeps SQLite tests reproducible.
        candidate_ids: set[str] | None = None
        if candidate_provider is not None:
            retrieved = candidate_provider(
                effective_query,
                np.asarray(query_dense, dtype=np.float32),
                self.settings.ranking_candidate_limit,
            )
            if retrieved:
                candidate_ids = set(retrieved)
                for index, movie in enumerate(self.catalog.movies):
                    scores = retrieved.get(movie.id)
                    if scores is None:
                        continue
                    semantic[index] = max(0.0, min(1.0, float(scores[0])))
                    lexical[index] = max(0.0, min(1.0, float(scores[1])))

        # Exact metadata evidence gets a bounded lexical lift.
        normalized_query = normalize_text(effective_query)
        query_tokens = set(normalized_query.split())
        exact_evidence: list[list[dict[str, Any]]] = [[] for _ in self.catalog.movies]
        for index, movie in enumerate(self.catalog.movies):
            title = normalize_text(movie.canonical_title)
            if phrase_in_query(title, normalized_query):
                lexical[index] = min(1.0, lexical[index] + 0.35)
                exact_evidence[index].append(
                    {
                        "type": "title",
                        "value": movie.canonical_title,
                        "source_field": "canonical_title",
                        "contribution": 0.35,
                    }
                )
            for field_name, values in (("genre", movie.genres), ("theme", movie.themes)):
                matches = [value for value in values if value in query_tokens]
                if matches:
                    contribution = min(0.2, 0.08 * len(matches))
                    lexical[index] = min(1.0, lexical[index] + contribution)
                    exact_evidence[index].append(
                        {
                            "type": field_name,
                            "value": ", ".join(matches),
                            "source_field": f"{field_name}s",
                            "contribution": contribution,
                        }
                    )
            if movie.director and phrase_in_query(normalize_text(movie.director), normalized_query):
                lexical[index] = min(1.0, lexical[index] + 0.28)
                exact_evidence[index].append(
                    {
                        "type": "director",
                        "value": movie.director,
                        "source_field": "director",
                        "contribution": 0.28,
                    }
                )
            cast_matches = [
                name
                for name in movie.cast_members
                if phrase_in_query(normalize_text(name), normalized_query)
            ]
            if cast_matches:
                lexical[index] = min(1.0, lexical[index] + 0.28)
                exact_evidence[index].append(
                    {
                        "type": "actor",
                        "value": cast_matches[0],
                        "source_field": "cast",
                        "contribution": 0.28,
                    }
                )

        semantic_weight = self.settings.ranking_semantic_weight * request.alpha
        lexical_weight = self.settings.ranking_lexical_weight * (1.0 - request.alpha + 0.42)
        fused = reciprocal_rank_fusion(semantic, lexical, semantic_weight, lexical_weight)
        positive_neighbors, negative_neighbors = self._profile_neighbors(
            signals.positive_movie_ids,
            signals.negative_movie_ids,
        )
        ranked: list[RankedMovie] = []
        for index, movie in enumerate(self.catalog.movies):
            if candidate_ids is not None and movie.id not in candidate_ids:
                continue
            if seed_movie_id and movie.id == seed_movie_id:
                continue
            if not self._matches_filters(movie, request.filters, hints, signals):
                continue
            pref = preference_score(movie, signals, positive_neighbors, negative_neighbors)
            hidden = hidden_gem_score(
                movie.prominence_score,
                max(semantic[index], lexical[index]),
                min(1.0, signals.hidden_gem_preference * request.beta),
            )
            score = (
                0.80 * float(fused[index])
                + self.settings.ranking_preference_weight * max(-0.5, pref)
                + self.settings.ranking_quality_weight * movie.data_quality_score
                + self.settings.ranking_hidden_gem_weight * hidden
            )
            evidence = list(exact_evidence[index])
            if pref > 0:
                evidence.append(
                    {
                        "type": "preference",
                        "value": "profile preferences",
                        "source_field": "user_profile",
                        "contribution": round(pref, 4),
                    }
                )
            if hidden > 0.08:
                evidence.append(
                    {
                        "type": "hidden_gem",
                        "value": "lower mainstream prominence",
                        "source_field": "prominence_score",
                        "contribution": round(hidden, 4),
                    }
                )
            vector = self.movie_vector(index)
            x, y = self.coordinates(vector)
            ranked.append(
                RankedMovie(
                    movie=movie,
                    semantic=round(float(np.clip(semantic[index], 0, 1)), 6),
                    lexical=round(float(np.clip(lexical[index], 0, 1)), 6),
                    preference=round(pref, 6),
                    quality=movie.data_quality_score,
                    hidden_gem=round(hidden, 6),
                    final=round(float(max(0.0, min(1.0, score))), 6),
                    evidence=evidence,
                    semantic_vector=vector,
                    plot_x=x,
                    plot_y=y,
                )
            )
            
        if request.sort == SearchSort.relevance and self.cross_encoder is not None and ranking_version.startswith("v3"):
            ranked.sort(key=lambda item: (item.final, item.movie.data_quality_score), reverse=True)
            candidate_limit = min(len(ranked), self.settings.ranking_candidate_limit)
            top_candidates = ranked[:candidate_limit]
            if top_candidates:
                pairs = [[query.original, item.movie.searchable_text] for item in top_candidates]
                try:
                    cross_scores = self.cross_encoder.predict(pairs, show_progress_bar=False)
                    cross_probs = 1 / (1 + np.exp(-cross_scores))
                    for i, item in enumerate(top_candidates):
                        ce_score = float(cross_probs[i])
                        item.final = round(0.7 * ce_score + 0.3 * item.final, 6)
                except Exception:
                    pass

        if request.sort == SearchSort.year_desc:
            ranked.sort(key=lambda item: (item.movie.release_year or 0, item.final), reverse=True)
        elif request.sort == SearchSort.year_asc:
            ranked.sort(key=lambda item: (item.movie.release_year or 9999, -item.final))
        elif request.sort == SearchSort.popularity:
            ranked.sort(key=lambda item: (item.movie.prominence_score, item.final), reverse=True)
        elif request.sort == SearchSort.hidden_gems:
            ranked.sort(key=lambda item: (item.hidden_gem, item.final), reverse=True)
        else:
            ranked.sort(key=lambda item: (item.final, item.movie.data_quality_score), reverse=True)

        candidate_limit = min(len(ranked), self.settings.ranking_candidate_limit)
        diversity = (
            request.diversity if request.diversity is not None else self.settings.ranking_diversity
        )
        if request.sort == SearchSort.relevance:
            ranked = (
                mmr_rerank(ranked[:candidate_limit], diversity, candidate_limit)
                + ranked[candidate_limit:]
            )
        return ranked, hints, self.coordinates(query_dense)


def build_explanation(
    item: RankedMovie, query: NormalizedQuery, personalized: bool
) -> dict[str, Any]:
    evidence = sorted(item.evidence, key=lambda value: value["contribution"], reverse=True)[:4]
    labels = [
        entry["value"]
        for entry in evidence
        if entry["type"] in {"genre", "theme", "title", "actor", "director"}
    ]
    if labels:
        summary = f"Strong match for {', '.join(labels[:3])}."
    elif personalized and item.preference > 0:
        summary = "Recommended from your saved preferences and positive feedback."
    elif item.hidden_gem > 0.08:
        summary = "A relevant lower-prominence title that fits your Hidden Gem preference."
    elif item.semantic >= 0.25:
        summary = "Its trusted synopsis and metadata are semantically related to this search."
    else:
        summary = "A diverse discovery from the validated Tamil-film catalog."
    confidence = "high" if evidence and max(item.semantic, item.lexical) >= 0.35 else "medium"
    if max(item.semantic, item.lexical) < 0.08 and not evidence:
        confidence = "low"
    return {"summary": summary, "evidence": evidence, "confidence": confidence}
