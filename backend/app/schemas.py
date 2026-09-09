from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class InteractionType(StrEnum):
    impression = "impression"
    click = "click"
    save = "save"
    rating = "rating"
    like = "like"
    dislike = "dislike"
    dismiss = "dismiss"
    viewed = "viewed"


class CollectionVisibility(StrEnum):
    private = "private"
    unlisted = "unlisted"
    public = "public"


class SearchSort(StrEnum):
    relevance = "relevance"
    year_desc = "year_desc"
    year_asc = "year_asc"
    popularity = "popularity"
    hidden_gems = "hidden_gems"


class VisualPalette(StrictModel):
    dominant_colors: list[str] = Field(default_factory=list, max_length=10)
    contrast: float = Field(default=0.5, ge=0, le=1)
    saturation: float = Field(default=0.5, ge=0, le=1)
    brightness: float = Field(default=0.5, ge=0, le=1)
    aesthetic_tags: list[str] = Field(default_factory=list, max_length=20)


class AudioProfile(StrictModel):
    bpm: int | None = Field(default=None, ge=40, le=240)
    energy: float = Field(default=0.5, ge=0, le=1)
    dynamic_range: float = Field(default=0.5, ge=0, le=1)
    instruments: list[str] = Field(default_factory=list, max_length=20)
    mood: str = Field(default="balanced", max_length=50)
    mix_tags: list[str] = Field(default_factory=list, max_length=20)


class SearchFilters(StrictModel):
    year_min: int | None = Field(default=None, ge=1900, le=2100)
    year_max: int | None = Field(default=None, ge=1900, le=2100)
    genres: list[str] = Field(default_factory=list, max_length=20)
    themes: list[str] = Field(default_factory=list, max_length=20)
    actors: list[str] = Field(default_factory=list, max_length=20)
    directors: list[str] = Field(default_factory=list, max_length=20)
    runtime_min: int | None = Field(default=None, ge=1, le=1000)
    runtime_max: int | None = Field(default=None, ge=1, le=1000)
    certificates: list[str] = Field(default_factory=list, max_length=10)
    prominence_min: float | None = Field(default=None, ge=0, le=1)
    prominence_max: float | None = Field(default=None, ge=0, le=1)
    min_quality: float | None = Field(default=None, ge=0, le=1)
    exclude_watched: bool = False
    exclude_dismissed: bool = True
    # V4 Multimodal filters
    visual_aesthetic: str | None = Field(default=None, max_length=80)
    audio_mood: str | None = Field(default=None, max_length=80)
    audio_instruments: list[str] = Field(default_factory=list, max_length=10)

    @model_validator(mode="after")
    def validate_ranges(self) -> SearchFilters:
        ranges = (
            ("year", self.year_min, self.year_max),
            ("runtime", self.runtime_min, self.runtime_max),
            ("prominence", self.prominence_min, self.prominence_max),
        )
        for name, minimum, maximum in ranges:
            if minimum is not None and maximum is not None and minimum > maximum:
                raise ValueError(f"{name}_min cannot be greater than {name}_max")
        return self


class SearchRequest(StrictModel):
    query: str = Field(default="", max_length=500)
    filters: SearchFilters = Field(default_factory=SearchFilters)
    sort: SearchSort = SearchSort.relevance
    page: int = Field(default=1, ge=1, le=10_000)
    page_size: int = Field(default=20, ge=1, le=50)
    alpha: float = Field(default=0.58, ge=0, le=1)
    beta: float = Field(default=0.5, ge=0, le=2)
    diversity: float | None = Field(default=None, ge=0, le=1)
    include_debug: bool = False
    # V4 Cross-modal query inputs & weights
    visual_query: str | None = Field(default=None, max_length=500)
    audio_query: str | None = Field(default=None, max_length=500)
    visual_weight: float = Field(default=0.0, ge=0, le=1)
    audio_weight: float = Field(default=0.0, ge=0, le=1)


class EvidenceOut(BaseModel):
    type: str
    value: str
    source_field: str
    contribution: float = 0.0
    modality: Literal["text", "visual", "audio"] = "text"


class ExplanationOut(BaseModel):
    summary: str
    evidence: list[EvidenceOut] = Field(default_factory=list)
    confidence: Literal["low", "medium", "high"] = "medium"


class ScoreOut(BaseModel):
    semantic: float
    lexical: float
    preference: float
    quality: float
    hidden_gem: float
    final: float
    visual: float = 0.0
    audio: float = 0.0


class MovieOut(BaseModel):
    index: int | None = None
    id: str
    title: str
    canonical_title: str
    original_title: str | None = None
    release_year: int | None = None
    runtime_minutes: int | None = None
    certificate: str | None = None
    overview: str
    language: str
    genre: str
    genres: list[str]
    themes: list[str]
    director: str
    cast: str
    poster_url: str | None = None
    source_url: str | None = None
    source_updated_at: str | None = None
    data_quality_status: str
    data_quality_score: float
    prominence_score: float
    dataset_version: str
    provenance: dict[str, Any] | None = None
    user_state: dict[str, Any] | None = None
    # V4 Multimodal profiles
    visual_palette: dict[str, Any] | None = None
    audio_profile: dict[str, Any] | None = None


class SearchResultOut(MovieOut):
    index: int | None = None
    similarity_score: float
    lexical_score: float
    final_score: float
    plot_x: float | None = None
    plot_y: float | None = None
    scores: ScoreOut
    explanation: ExplanationOut
    debug: dict[str, Any] | None = None


# V4 Real-Time Streaming & Event Schemas
class InteractionEvent(StrictModel):
    event_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    event_type: str
    movie_id: str
    timestamp: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    session_id: str | None = None
    context: dict[str, Any] = Field(default_factory=dict)


# V4 Agent Schemas
class ToolCall(BaseModel):
    id: str
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class ToolResult(BaseModel):
    tool_call_id: str
    name: str
    output: Any
    error: str | None = None


class AgentMessage(BaseModel):
    role: Literal["user", "assistant", "system", "tool"]
    content: str
    tool_calls: list[ToolCall] = Field(default_factory=list)
    tool_results: list[ToolResult] = Field(default_factory=list)
    timestamp: str | None = None


class ClarificationQuestion(BaseModel):
    question: str
    options: list[str] = Field(default_factory=list)
    dimension: str = "genre"


class AgentChatRequest(StrictModel):
    message: str = Field(min_length=1, max_length=2000)
    session_id: str | None = None
    user_id: str | None = None


class AgentChatResponse(BaseModel):
    session_id: str
    message: str
    needs_clarification: bool = False
    clarification: ClarificationQuestion | None = None
    recommendations: list[SearchResultOut] = Field(default_factory=list)
    citations: list[MovieOut] = Field(default_factory=list)
    tool_calls_executed: list[ToolCall] = Field(default_factory=list)
    latency_ms: float = 0.0
    grounding_verified: bool = True


class PaginationMeta(BaseModel):
    request_id: str
    ranking_version: str
    dataset_version: str
    total: int
    page: int
    page_size: int
    total_pages: int
    latency_ms: float
    inferred_filters: dict[str, Any] = Field(default_factory=dict)
    personalized: bool = False
    stage_timings_ms: dict[str, float] = Field(default_factory=dict)
    experiment: dict[str, Any] = Field(default_factory=dict)


class SearchResponse(BaseModel):
    query: str
    normalized_query: str
    detected_language: str
    query_plot: dict[str, float] | None = None
    results: list[SearchResultOut]
    meta: PaginationMeta
    seed_movie: MovieOut | None = None
    surface: str | None = None


class RegisterRequest(StrictModel):
    email: str = Field(min_length=3, max_length=254)
    # Strength is validated in AuthService so clients receive the stable,
    # actionable ``weak_password`` error instead of a generic schema error.
    password: str = Field(min_length=1, max_length=256)
    display_name: str = Field(min_length=1, max_length=80)
    locale: str = Field(default="en", min_length=2, max_length=16)

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        value = value.casefold()
        if value.count("@") != 1 or "." not in value.rsplit("@", 1)[1]:
            raise ValueError("Enter a valid email address")
        return value


class LoginRequest(StrictModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=256)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.casefold()


class ProfilePreferences(StrictModel):
    favorite_genres: list[str] = Field(default_factory=list, max_length=30)
    favorite_themes: list[str] = Field(default_factory=list, max_length=30)
    preferred_eras: list[str] = Field(default_factory=list, max_length=10)
    hidden_gem_preference: float = Field(default=0.5, ge=0, le=1)
    languages: list[str] = Field(default_factory=lambda: ["Tamil"], max_length=10)
    dubbing_tolerance: bool = False
    onboarding_movie_ids: list[str] = Field(default_factory=list, max_length=50)


class PrivacySettings(StrictModel):
    store_search_history: bool = True
    use_interactions_for_recommendations: bool = True
    analytics_consent: bool = False


class ProfilePatch(StrictModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=80)
    locale: str | None = Field(default=None, min_length=2, max_length=16)
    preferences: ProfilePreferences | None = None
    privacy: PrivacySettings | None = None
    reset_interactions: bool = False


class ProfileOut(BaseModel):
    id: str
    email: str
    display_name: str
    locale: str
    preferences: ProfilePreferences
    privacy: PrivacySettings
    is_admin: bool = False
    created_at: str
    updated_at: str


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    profile: ProfileOut


class InteractionRequest(StrictModel):
    movie_id: str = Field(min_length=1, max_length=100)
    type: InteractionType
    value: float | None = None
    context: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_value(self) -> InteractionRequest:
        if self.type == InteractionType.rating:
            if self.value is None or not 0.5 <= self.value <= 5 or (self.value * 2) % 1:
                raise ValueError("Ratings must be between 0.5 and 5 in half-star increments")
        elif self.value is not None and not -1 <= self.value <= 1:
            raise ValueError("Interaction value must be between -1 and 1")
        if len(str(self.context)) > 4_000:
            raise ValueError("Interaction context is too large")
        return self


class InteractionOut(BaseModel):
    id: str
    movie_id: str
    type: InteractionType
    value: float | None = None
    context: dict[str, Any]
    created_at: str
    updated_at: str


class CollectionCreate(StrictModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=1000)
    visibility: CollectionVisibility = CollectionVisibility.private


class CollectionPatch(StrictModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=1000)
    visibility: CollectionVisibility | None = None


class CollectionItemRequest(StrictModel):
    movie_id: str = Field(min_length=1, max_length=100)
    position: int | None = Field(default=None, ge=0, le=10_000)


class CollectionItemOut(BaseModel):
    movie: MovieOut
    position: int
    note: str | None = None
    added_at: str


class CollectionOut(BaseModel):
    id: str
    owner_id: str | None = None
    owner_display_name: str | None = None
    name: str
    description: str
    visibility: CollectionVisibility
    share_token: str | None = None
    items: list[CollectionItemOut] = Field(default_factory=list)
    item_count: int = 0
    created_at: str
    updated_at: str


class IngestionRecord(StrictModel):
    source_system: str = Field(min_length=1, max_length=80)
    source_identifier: str = Field(min_length=1, max_length=200)
    movie: dict[str, Any]
    confidence: float = Field(default=1.0, ge=0, le=1)
    retrieved_at: datetime | None = None


class IngestionRequest(StrictModel):
    records: list[IngestionRecord] = Field(min_length=1, max_length=1000)
    dry_run: bool = True
    transformation_version: str = Field(default="v2-import-1", max_length=80)


class ErrorDetail(BaseModel):
    code: str
    message: str
    details: Any | None = None
    request_id: str


class ErrorEnvelope(BaseModel):
    error: ErrorDetail
