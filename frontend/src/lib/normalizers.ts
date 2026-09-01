import type {
  AuthResponse,
  CollectionItem,
  DataQualityReport,
  MatchExplanation,
  Movie,
  MovieCollection,
  MovieResult,
  PaginationMeta,
  RecommendationResponse,
  SearchLanguage,
  SearchResponse,
  ChatResponse,
  UserPreferences,
  UserProfile,
} from "../types/api";

type UnknownRecord = Record<string, unknown>;

const isRecord = (value: unknown): value is UnknownRecord =>
  typeof value === "object" && value !== null && !Array.isArray(value);

const asRecord = (value: unknown): UnknownRecord =>
  isRecord(value) ? value : {};

const firstDefined = (...values: unknown[]) =>
  values.find((value) => value !== undefined && value !== null);

const asString = (value: unknown, fallback = ""): string =>
  typeof value === "string"
    ? value
    : typeof value === "number"
      ? String(value)
      : fallback;

const asOptionalString = (value: unknown): string | undefined => {
  const result = asString(value).trim();
  return result || undefined;
};

const asNumber = (value: unknown, fallback = 0): number => {
  const parsed = typeof value === "number" ? value : Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
};

const asOptionalNumber = (value: unknown): number | undefined => {
  const parsed = asNumber(value, Number.NaN);
  return Number.isFinite(parsed) ? parsed : undefined;
};

const splitList = (value: unknown): string[] => {
  if (Array.isArray(value)) {
    return value
      .map((item) =>
        typeof item === "string"
          ? item.trim()
          : asString(asRecord(item).name).trim(),
      )
      .filter(Boolean);
  }

  if (typeof value === "string") {
    return value
      .split(/[,/|]/)
      .map((item) => item.trim())
      .filter(Boolean);
  }

  return [];
};

const clampScore = (value: unknown): number =>
  Math.min(1, Math.max(0, asNumber(value)));

const normalizeLanguage = (value: unknown): SearchLanguage => {
  const language = asString(value).toLowerCase();
  if (language === "en" || language === "english") return "en";
  if (language === "ta" || language === "tamil") return "ta";
  if (language === "tanglish" || language === "romanized_tamil")
    return "tanglish";
  if (language === "mixed") return "mixed";
  return "unknown";
};

export function normalizeMovie(value: unknown, fallbackId = "unknown"): Movie {
  const raw = asRecord(value);
  const genres = splitList(firstDefined(raw.genres, raw.genre));
  const themes = splitList(firstDefined(raw.themes, raw.keywords));
  const cast = splitList(raw.cast);

  return {
    id: asString(firstDefined(raw.id, raw.movie_id, raw.index), fallbackId),
    title: asString(
      firstDefined(raw.canonical_title, raw.title),
      "Untitled film",
    ),
    originalTitle: asOptionalString(
      firstDefined(raw.original_title, raw.originalTitle),
    ),
    releaseYear: asOptionalNumber(firstDefined(raw.release_year, raw.year)),
    runtimeMinutes: asOptionalNumber(
      firstDefined(raw.runtime_minutes, raw.runtime),
    ),
    certificate: asOptionalString(
      firstDefined(raw.certificate, raw.certification),
    ),
    overview: asString(
      firstDefined(raw.overview, raw.synopsis),
      "Synopsis unavailable.",
    ),
    language: asString(raw.language, "Tamil"),
    posterUrl: asOptionalString(firstDefined(raw.poster_url, raw.posterUrl)),
    sourceUrl: asOptionalString(firstDefined(raw.source_url, raw.sourceUrl)),
    sourceUpdatedAt: asOptionalString(
      firstDefined(raw.source_updated_at, raw.sourceUpdatedAt),
    ),
    dataQualityStatus: asOptionalString(
      firstDefined(raw.data_quality_status, raw.dataQualityStatus),
    ),
    genres,
    themes,
    director: asOptionalString(raw.director),
    cast,
    prominenceScore: clampScore(
      firstDefined(
        raw.prominence_score,
        raw.popularity_score,
        raw.prominenceScore,
      ),
    ),
    qualityScore: asOptionalNumber(
      firstDefined(raw.quality_score, raw.data_quality_score, raw.qualityScore),
    ),
  };
}

function normalizeExplanation(value: unknown, movie: Movie): MatchExplanation {
  const raw = asRecord(value);
  const evidence = splitList(raw.evidence);
  return {
    summary:
      asOptionalString(firstDefined(raw.summary, raw.text, raw.explanation)) ??
      `A catalog match based on ${movie.genres.slice(0, 2).join(" and ") || "your discovery preferences"}.`,
    evidence,
  };
}

export function normalizeMovieResult(
  value: unknown,
  fallbackId = "unknown",
): MovieResult {
  const raw = asRecord(value);
  const movieSource = isRecord(raw.movie) ? { ...raw.movie, ...raw } : raw;
  const movie = normalizeMovie(movieSource, fallbackId);
  const scores = asRecord(raw.scores);
  const final = firstDefined(
    scores.final,
    raw.final_score,
    raw.similarity_score,
  );

  return {
    ...movie,
    scores: {
      semantic: clampScore(
        firstDefined(scores.semantic, raw.similarity_score, raw.semantic_score),
      ),
      lexical: clampScore(firstDefined(scores.lexical, raw.lexical_score)),
      preference: clampScore(
        firstDefined(scores.preference, raw.preference_score),
      ),
      quality: clampScore(
        firstDefined(scores.quality, movie.qualityScore, 0.8),
      ),
      hiddenGem: clampScore(
        firstDefined(
          scores.hidden_gem,
          scores.hiddenGem,
          1 - movie.prominenceScore,
        ),
      ),
      final: clampScore(final),
    },
    explanation: normalizeExplanation(
      firstDefined(raw.explanation, raw.match_explanation),
      movie,
    ),
    plotX: asOptionalNumber(firstDefined(raw.plot_x, raw.plotX)),
    plotY: asOptionalNumber(firstDefined(raw.plot_y, raw.plotY)),
  };
}

function normalizeMeta(value: unknown, resultCount: number): PaginationMeta {
  const raw = asRecord(value);
  const pageSize = Math.max(
    1,
    asNumber(firstDefined(raw.page_size, raw.pageSize), resultCount || 20),
  );
  const total = Math.max(0, asNumber(raw.total, resultCount));
  return {
    requestId: asString(
      firstDefined(raw.request_id, raw.requestId),
      "local-request",
    ),
    rankingVersion: asString(
      firstDefined(raw.ranking_version, raw.rankingVersion),
      "v2",
    ),
    total,
    page: Math.max(1, asNumber(raw.page, 1)),
    pageSize,
    totalPages: Math.max(
      1,
      asNumber(
        firstDefined(raw.total_pages, raw.totalPages),
        Math.ceil(total / pageSize) || 1,
      ),
    ),
    latencyMs: Math.max(
      0,
      asNumber(firstDefined(raw.latency_ms, raw.latencyMs), 0),
    ),
  };
}

export function normalizeSearchResponse(value: unknown): SearchResponse {
  const raw = asRecord(value);
  const sourceResults = Array.isArray(raw.results)
    ? raw.results
    : Array.isArray(raw.items)
      ? raw.items
      : [];
  const results = sourceResults.map((item, index) =>
    normalizeMovieResult(item, `result-${index + 1}`),
  );
  const queryPlot = asRecord(raw.query_plot);
  const plotX = asOptionalNumber(queryPlot.x);
  const plotY = asOptionalNumber(queryPlot.y);

  return {
    query: asString(raw.query),
    normalizedQuery: asString(
      firstDefined(raw.normalized_query, raw.normalizedQuery, raw.query),
    ),
    detectedLanguage: normalizeLanguage(
      firstDefined(raw.detected_language, raw.detectedLanguage),
    ),
    queryPlot:
      plotX !== undefined && plotY !== undefined
        ? { x: plotX, y: plotY }
        : undefined,
    results,
    meta: normalizeMeta(raw.meta, results.length),
    source: "api",
  };
}

export function normalizeRecommendationResponse(
  value: unknown,
): RecommendationResponse {
  const normalized = normalizeSearchResponse(value);
  return { results: normalized.results, meta: normalized.meta, source: "api" };
}

export function normalizeChatResponse(value: unknown): ChatResponse {
  const raw = asRecord(value);
  const sourceCitations = Array.isArray(raw.citations) ? raw.citations : [];
  const citations = sourceCitations.map((item, index) =>
    normalizeMovieResult(item, `citation-${index + 1}`),
  );

  return {
    answer: asString(raw.answer),
    query: asString(raw.query),
    citations,
  };
}

const defaultPreferences: UserPreferences = {
  favoriteGenres: [],
  favoriteThemes: [],
  eraFrom: 2015,
  eraTo: new Date().getFullYear(),
  hiddenGemPreference: 0.55,
  preferredLanguages: ["Tamil"],
  acceptsDubbed: false,
  analyticsConsent: false,
  onboardingMovieIds: [],
};

function eraBounds(value: unknown): { from: number; to: number } {
  const eras = splitList(value);
  const years = eras.flatMap((era) => {
    const match = era.match(/(19|20)\d{2}/);
    if (!match) return [];
    const start = Number(match[0]);
    return [start, era.includes("s") ? start + 9 : start];
  });
  return years.length
    ? { from: Math.min(...years), to: Math.max(...years) }
    : { from: defaultPreferences.eraFrom, to: defaultPreferences.eraTo };
}

export function normalizeProfile(value: unknown): UserProfile {
  const raw = asRecord(value);
  const preferences = asRecord(raw.preferences);
  const privacy = asRecord(firstDefined(raw.privacy, raw.privacy_settings));
  const eras = eraBounds(
    firstDefined(preferences.preferred_eras, preferences.preferredEras),
  );
  const onboardingMovieIds = splitList(
    firstDefined(
      preferences.onboarding_movie_ids,
      preferences.onboardingMovieIds,
    ),
  );
  return {
    id: asString(raw.id, "demo-user"),
    email: asString(raw.email),
    displayName: asString(
      firstDefined(raw.display_name, raw.displayName),
      "TamilTrove member",
    ),
    locale: asString(raw.locale, "en-IN"),
    onboardingComplete: Boolean(
      firstDefined(
        raw.onboarding_complete,
        raw.onboardingComplete,
        onboardingMovieIds.length > 0 ||
          splitList(preferences.favorite_genres).length > 0,
      ),
    ),
    isAdmin: Boolean(firstDefined(raw.is_admin, raw.isAdmin, false)),
    preferences: {
      favoriteGenres: splitList(
        firstDefined(preferences.favorite_genres, preferences.favoriteGenres),
      ),
      favoriteThemes: splitList(
        firstDefined(preferences.favorite_themes, preferences.favoriteThemes),
      ),
      eraFrom: asNumber(
        firstDefined(preferences.era_from, preferences.eraFrom),
        eras.from,
      ),
      eraTo: asNumber(
        firstDefined(preferences.era_to, preferences.eraTo),
        eras.to,
      ),
      hiddenGemPreference: clampScore(
        firstDefined(
          preferences.hidden_gem_preference,
          preferences.hiddenGemPreference,
          defaultPreferences.hiddenGemPreference,
        ),
      ),
      preferredLanguages:
        splitList(
          firstDefined(
            preferences.languages,
            preferences.preferred_languages,
            preferences.preferredLanguages,
          ),
        ).length > 0
          ? splitList(
              firstDefined(
                preferences.languages,
                preferences.preferred_languages,
                preferences.preferredLanguages,
              ),
            )
          : defaultPreferences.preferredLanguages,
      acceptsDubbed: Boolean(
        firstDefined(
          preferences.dubbing_tolerance,
          preferences.accepts_dubbed,
          preferences.acceptsDubbed,
          false,
        ),
      ),
      analyticsConsent: Boolean(
        firstDefined(
          privacy.analytics_consent,
          preferences.analytics_consent,
          preferences.analyticsConsent,
          false,
        ),
      ),
      onboardingMovieIds,
    },
    privacy: {
      profileVisible: Boolean(
        firstDefined(privacy.profile_visible, privacy.profileVisible, false),
      ),
      saveSearchHistory: Boolean(
        firstDefined(
          privacy.store_search_history,
          privacy.save_search_history,
          privacy.saveSearchHistory,
          true,
        ),
      ),
      personalizeRecommendations: Boolean(
        firstDefined(
          privacy.use_interactions_for_recommendations,
          privacy.personalize_recommendations,
          privacy.personalizeRecommendations,
          true,
        ),
      ),
    },
    createdAt: asOptionalString(firstDefined(raw.created_at, raw.createdAt)),
    updatedAt: asOptionalString(firstDefined(raw.updated_at, raw.updatedAt)),
  };
}

export function normalizeAuthResponse(value: unknown): AuthResponse {
  const raw = asRecord(value);
  return {
    accessToken: asOptionalString(
      firstDefined(raw.access_token, raw.accessToken),
    ),
    tokenType: asString(firstDefined(raw.token_type, raw.tokenType), "bearer"),
    expiresIn: asOptionalNumber(firstDefined(raw.expires_in, raw.expiresIn)),
    profile: normalizeProfile(raw.profile),
  };
}

function normalizeCollectionItem(
  value: unknown,
  index: number,
): CollectionItem {
  const raw = asRecord(value);
  const nestedMovie = isRecord(raw.movie)
    ? normalizeMovie(raw.movie, `collection-movie-${index}`)
    : undefined;
  return {
    movieId: asString(
      firstDefined(raw.movie_id, raw.movieId, nestedMovie?.id),
      `collection-movie-${index}`,
    ),
    position: asNumber(raw.position, index),
    movie: nestedMovie,
    addedAt: asOptionalString(firstDefined(raw.added_at, raw.addedAt)),
  };
}

export function normalizeCollection(value: unknown): MovieCollection {
  const raw = asRecord(value);
  const items = Array.isArray(raw.items)
    ? raw.items.map((item, index) => normalizeCollectionItem(item, index))
    : [];
  const visibility = asString(raw.visibility, "private");
  return {
    id: asString(raw.id, "collection"),
    ownerId: asOptionalString(firstDefined(raw.owner_id, raw.ownerId)),
    ownerDisplayName: asOptionalString(
      firstDefined(raw.owner_display_name, raw.ownerDisplayName),
    ),
    name: asString(raw.name, "Untitled collection"),
    description: asString(raw.description),
    visibility:
      visibility === "public" || visibility === "unlisted"
        ? visibility
        : "private",
    items,
    shareToken: asOptionalString(
      firstDefined(raw.share_token, raw.shareToken, raw.token),
    ),
    shareUrl: asOptionalString(firstDefined(raw.share_url, raw.shareUrl)),
    createdAt: asOptionalString(firstDefined(raw.created_at, raw.createdAt)),
    updatedAt: asOptionalString(firstDefined(raw.updated_at, raw.updatedAt)),
  };
}

export function normalizeCollectionList(value: unknown): MovieCollection[] {
  if (Array.isArray(value)) return value.map(normalizeCollection);
  const raw = asRecord(value);
  const collections = firstDefined(raw.collections, raw.items);
  return Array.isArray(collections) ? collections.map(normalizeCollection) : [];
}

export function normalizeDataQualityReport(value: unknown): DataQualityReport {
  const raw = asRecord(value);
  const distribution = asRecord(raw.quality_distribution);
  const invalidRecords = Array.isArray(raw.invalid_records)
    ? raw.invalid_records.map((item) => {
        const issue = asRecord(item);
        return {
          index: asNumber(issue.index),
          reason: asString(issue.reason, "Unknown validation failure"),
        };
      })
    : [];

  return {
    datasetVersion: asString(raw.dataset_version, "unknown"),
    generatedAt: asString(raw.generated_at),
    sourceRecords: asNumber(raw.source_records),
    acceptedRecords: asNumber(raw.accepted_records),
    invalidRecords,
    duplicateIdentities: splitList(raw.duplicate_identities),
    needsReview: asNumber(raw.needs_review),
    missingPosters: asNumber(raw.missing_posters),
    shortOverviews: asNumber(raw.short_overviews),
    embeddingErrors: splitList(raw.embedding_errors),
    qualityDistribution: {
      validated: asNumber(distribution.validated),
      needsReview: asNumber(distribution.needs_review),
      quarantined: asNumber(distribution.quarantined),
    },
    semanticBackend: asString(raw.semantic_backend, "unknown"),
    degradedReasons: splitList(raw.degraded_reasons),
  };
}
