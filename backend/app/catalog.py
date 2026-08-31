from __future__ import annotations

import hashlib
import json
import math
import re
import uuid
from collections.abc import Iterable
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .normalization import normalize_text

CATALOG_NAMESPACE = uuid.UUID("b915615d-5d47-4a95-aed5-c54e35775ce1")
YEAR_RE = re.compile(r"\b((?:19|20)\d{2})\b")
CERT_SUFFIX_RE = re.compile(r"\s*\((?:U|A|UA|U/A)\)\s*$", re.IGNORECASE)
THEME_TERMS = {
    "revenge": ("revenge", "vengeance", "avenge"),
    "friendship": ("friend", "friendship", "companionship"),
    "family": ("family", "father", "mother", "siblings"),
    "politics": ("politic", "minister", "election", "government"),
    "crime": ("crime", "criminal", "murder", "gangster", "police"),
    "courtroom": ("court", "lawyer", "trial", "justice"),
    "village": ("village", "rural", "farmer"),
    "one-night": ("one night", "single night", "overnight"),
    "chase": ("chase", "pursuit", "escape"),
    "prison": ("prison", "prisoner", "convict", "jail"),
    "coming-of-age": ("coming of age", "growing up", "teenager"),
}


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def stable_movie_id(
    title: str, director: str = "", year: int | None = None, language: str = "ta"
) -> str:
    identity = "|".join(
        (normalize_text(title), str(year or ""), normalize_text(director), language.casefold())
    )
    return str(uuid.uuid5(CATALOG_NAMESPACE, identity))


def content_hash(movie: dict[str, Any]) -> str:
    payload = "|".join(
        str(movie.get(key) or "")
        for key in (
            "canonical_title",
            "original_title",
            "overview",
            "genres",
            "themes",
            "director",
            "cast",
        )
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def validated_https_url(value: object) -> str | None:
    candidate = str(value or "").strip()
    if not candidate:
        return None
    parsed = urlparse(candidate)
    if (
        parsed.scheme.casefold() != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
    ):
        return None
    return candidate


def _split_names(value: object) -> tuple[str, ...]:
    items = value if isinstance(value, list) else re.split(r"[,;|]", str(value or ""))
    return tuple(dict.fromkeys(item.strip() for item in items if item and item.strip()))


def _split_genres(value: object) -> tuple[str, ...]:
    if isinstance(value, list):
        items = value
    else:
        items = re.findall(r"[A-Za-z]+(?:[ -][A-Za-z]+)?", str(value or ""))
    normalized: list[str] = []
    known = {
        "action",
        "adventure",
        "animation",
        "biography",
        "comedy",
        "crime",
        "documentary",
        "drama",
        "family",
        "fantasy",
        "history",
        "horror",
        "music",
        "musical",
        "mystery",
        "political",
        "romance",
        "sport",
        "thriller",
        "war",
    }
    for item in items:
        words = normalize_text(str(item)).split()
        for word in words:
            if word in known and word not in normalized:
                normalized.append(word)
    return tuple(normalized or [normalize_text(str(value or "unknown"))])


def infer_themes(overview: str) -> tuple[str, ...]:
    text = normalize_text(overview)
    return tuple(
        theme for theme, needles in THEME_TERMS.items() if any(needle in text for needle in needles)
    )


def quality_score(raw: dict[str, Any], overview: str, poster_url: str | None) -> float:
    score = 0.25
    if raw.get("title"):
        score += 0.15
    if raw.get("director"):
        score += 0.10
    if raw.get("cast"):
        score += 0.10
    if raw.get("genre"):
        score += 0.10
    if len(overview) >= 120:
        score += 0.20
    elif len(overview) >= 60:
        score += 0.10
    if poster_url and urlparse(poster_url).scheme == "https":
        score += 0.10
    return round(min(score, 1.0), 4)


@dataclass(slots=True)
class Movie:
    id: str
    title: str
    canonical_title: str
    original_title: str | None
    release_year: int | None
    runtime_minutes: int | None
    certificate: str | None
    overview: str
    language: str
    genres: tuple[str, ...]
    themes: tuple[str, ...]
    director: str
    cast_members: tuple[str, ...]
    poster_url: str | None
    source_url: str | None
    source_updated_at: str | None
    data_quality_status: str
    data_quality_score: float
    prominence_score: float
    content_hash: str
    dataset_version: str
    provenance: dict[str, Any] = field(default_factory=dict)
    source_index: int | None = None

    @property
    def genre(self) -> str:
        return " ".join(item.title() for item in self.genres)

    @property
    def cast(self) -> str:
        return ", ".join(self.cast_members)

    @property
    def searchable_text(self) -> str:
        return " ".join(
            (
                self.canonical_title,
                self.original_title or "",
                self.genre,
                " ".join(self.themes),
                self.director,
                self.cast,
                self.overview,
            )
        )

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["genre"] = self.genre
        data["cast"] = self.cast
        data["genres"] = list(self.genres)
        data["themes"] = list(self.themes)
        data.pop("cast_members", None)
        return data


@dataclass(slots=True)
class Catalog:
    movies: list[Movie]
    dataset_version: str
    source_path: Path
    source_embeddings: Any | None = None
    validation_report: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def load(cls, source_path: Path, embeddings_path: Path | None = None) -> Catalog:
        with source_path.open("r", encoding="utf-8-sig") as handle:
            records = json.load(handle)
        if not isinstance(records, list) or not records:
            raise RuntimeError("Movie dataset must be a non-empty JSON list")

        digest = hashlib.sha256(source_path.read_bytes()).hexdigest()[:12]
        dataset_version = f"json-{digest}"
        movies: list[Movie] = []
        seen_ids: set[str] = set()
        duplicate_ids: list[str] = []
        invalid_rows: list[dict[str, Any]] = []
        for index, raw in enumerate(records):
            if not isinstance(raw, dict):
                invalid_rows.append({"index": index, "reason": "record_not_object"})
                continue
            title = str(raw.get("canonical_title") or raw.get("title") or "").strip()
            overview = str(raw.get("overview") or "").strip()
            if not title:
                invalid_rows.append({"index": index, "reason": "missing_title"})
                continue
            canonical_title = CERT_SUFFIX_RE.sub("", title).strip()
            director = str(raw.get("director") or "").strip()
            explicit_year = raw.get("release_year")
            try:
                release_year = int(explicit_year) if explicit_year else None
            except (TypeError, ValueError):
                release_year = None
            if release_year is None:
                title_year = YEAR_RE.search(title)
                opening_year = YEAR_RE.search(overview[:160])
                match = title_year or opening_year
                release_year = int(match.group(1)) if match else None
            if release_year is not None and not 1900 <= release_year <= datetime.now().year + 3:
                release_year = None
            language = str(raw.get("language") or "Tamil").strip()
            movie_id = str(
                raw.get("id") or stable_movie_id(canonical_title, director, release_year, language)
            )
            if movie_id in seen_ids:
                duplicate_ids.append(movie_id)
                movie_id = str(uuid.uuid5(CATALOG_NAMESPACE, f"{movie_id}|{index}"))
            seen_ids.add(movie_id)
            poster_url = validated_https_url(raw.get("poster_url"))
            try:
                prominence = float(raw.get("prominence_score", 0.5))
                if not math.isfinite(prominence):
                    raise ValueError
            except (TypeError, ValueError):
                prominence = 0.5
            prominence = max(0.0, min(1.0, prominence))
            genres = _split_genres(raw.get("genres") or raw.get("genre"))
            raw_themes = raw.get("themes")
            if isinstance(raw_themes, str):
                themes = tuple(
                    dict.fromkeys(
                        normalize_text(item)
                        for item in re.split(r"[,;|]", raw_themes)
                        if normalize_text(item)
                    )
                )
            elif isinstance(raw_themes, (list, tuple, set)):
                themes = tuple(
                    dict.fromkeys(
                        normalize_text(str(item))
                        for item in raw_themes
                        if normalize_text(str(item))
                    )
                )
            else:
                themes = infer_themes(overview)
            q_score = quality_score(raw, overview, poster_url)
            status = str(
                raw.get("data_quality_status")
                or ("validated" if q_score >= 0.65 else "needs_review")
            )
            normalized_for_hash = {
                "canonical_title": canonical_title,
                "original_title": raw.get("original_title"),
                "overview": overview,
                "genres": genres,
                "themes": themes,
                "director": director,
                "cast": raw.get("cast"),
            }
            provenance = raw.get("provenance") or {
                "source_system": "legacy_dataset",
                "source_identifier": str(index),
                "retrieved_at": None,
                "transformation_version": "v2-import-1",
                "confidence": q_score,
            }
            runtime = raw.get("runtime_minutes")
            try:
                runtime_minutes = int(runtime) if runtime is not None else None
            except (TypeError, ValueError):
                runtime_minutes = None
            movies.append(
                Movie(
                    id=movie_id,
                    title=canonical_title,
                    canonical_title=canonical_title,
                    original_title=str(raw.get("original_title") or "").strip() or None,
                    release_year=release_year,
                    runtime_minutes=runtime_minutes,
                    certificate=str(raw.get("certificate") or "").strip() or None,
                    overview=overview,
                    language=language,
                    genres=genres,
                    themes=themes,
                    director=director,
                    cast_members=_split_names(raw.get("cast")),
                    poster_url=poster_url,
                    source_url=validated_https_url(raw.get("source_url")),
                    source_updated_at=str(raw.get("source_updated_at") or "").strip() or None,
                    data_quality_status=status,
                    data_quality_score=q_score,
                    prominence_score=round(prominence, 4),
                    content_hash=content_hash(normalized_for_hash),
                    dataset_version=dataset_version,
                    provenance=provenance,
                    source_index=index,
                )
            )

        embeddings: Any | None = None
        embedding_errors: list[str] = []
        if embeddings_path and embeddings_path.exists():
            try:
                import numpy as np

                loaded = np.load(embeddings_path, allow_pickle=False)
                if loaded.ndim != 2 or loaded.shape[0] != len(records):
                    embedding_errors.append("embedding_count_or_rank_mismatch")
                elif not np.isfinite(loaded).all():
                    embedding_errors.append("embedding_contains_non_finite_values")
                else:
                    # Invalid legacy rows are rare; retain exact stable-ID alignment.
                    indexes = [movie.source_index for movie in movies]
                    embeddings = loaded[indexes]
            except Exception as exc:  # readiness reports the degraded mode
                embedding_errors.append(f"embedding_load_failed:{type(exc).__name__}")

        report = {
            "dataset_version": dataset_version,
            "source_records": len(records),
            "accepted_records": len(movies),
            "invalid_records": invalid_rows,
            "duplicate_identities": duplicate_ids,
            "needs_review": sum(movie.data_quality_status != "validated" for movie in movies),
            "missing_posters": sum(not movie.poster_url for movie in movies),
            "short_overviews": sum(len(movie.overview) < 80 for movie in movies),
            "embedding_errors": embedding_errors,
            "generated_at": utc_now(),
        }
        return cls(movies, dataset_version, source_path, embeddings, report)

    @classmethod
    def from_records(cls, records: Iterable[dict[str, Any]], temporary_path: Path) -> Catalog:
        temporary_path.write_text(json.dumps(list(records), ensure_ascii=False), encoding="utf-8")
        return cls.load(temporary_path)

    def get(self, movie_id: str) -> Movie | None:
        return next((movie for movie in self.movies if movie.id == movie_id), None)

    def by_source_index(self, index: int) -> Movie | None:
        return next((movie for movie in self.movies if movie.source_index == index), None)
