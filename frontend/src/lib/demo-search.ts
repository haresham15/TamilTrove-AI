import { DEMO_MOVIES } from "./demo-data";
import type {
  MatchExplanation,
  Movie,
  MovieResult,
  RecommendationResponse,
  SearchFilters,
  SearchLanguage,
  SearchRequest,
  SearchResponse,
  UserPreferences,
} from "../types/api";

const TAMIL_PATTERN = /[\u0B80-\u0BFF]/u;
const TANGLISH_MARKERS = new Set([
  "maari",
  "mathiri",
  "padam",
  "oru",
  "kathai",
  "kaadhal",
  "sirippu",
  "semma",
  "mass",
  "gramam",
  "venum",
  "la",
]);

const QUERY_REPLACEMENTS: Array<[RegExp, string]> = [
  [/அநீதி/gu, " injustice "],
  [/நீதிமன்ற/gu, " courtroom "],
  [/அரசியல்/gu, " political "],
  [/போராட/gu, " resistance "],
  [/இரவு/gu, " night "],
  [/கிராம/gu, " village "],
  [/குடும்ப/gu, " family "],
  [/உணர்ச்சி/gu, " emotional drama "],
  [/காதல்/gu, " romance "],
  [/நகைச்சுவை/gu, " comedy "],
  [/maari|mathiri/giu, " like "],
  [/padam/giu, " movie "],
  [/oru/giu, " one "],
  [/kathai/giu, " story "],
  [/kaadhal/giu, " romance "],
  [/sirippu/giu, " comedy "],
  [/gramam/giu, " village "],
  [/setting-la/giu, " setting "],
];

const STOP_WORDS = new Set([
  "a",
  "an",
  "and",
  "about",
  "film",
  "find",
  "for",
  "like",
  "movie",
  "of",
  "one",
  "story",
  "the",
  "with",
]);

const SEARCH_ALIASES: Record<string, string> = {
  "kaithi-2019":
    "lorry drugs siege daughter lokesh cinematic universe high stakes action",
  "jai-bhim-2021":
    "law lawyer political oppression injustice human rights police custody courtroom",
  "aruvi-2017":
    "woman feminist consumerism television emotional social outsider hidden gem",
  "96-2018":
    "school love bittersweet emotional slow burn memory reunion night romance",
  "pariyerum-perumal-2018":
    "law college discrimination political dignity dog friendship caste",
  "super-deluxe-2019":
    "anthology interconnected quirky surreal trans identity dark comedy family",
  "vikram-vedha-2017":
    "cop criminal cat and mouse philosophical action moral grey folklore",
  "kadaisi-vivasayi-2022":
    "rural countryside slow life farmer land village emotional hidden gem",
  "maaveeran-2023":
    "superhero comic book housing corruption fantasy funny political",
  "por-thozhil-2023":
    "detective murder procedural serial killer investigation suspense",
  "sarpatta-parambarai-2021":
    "boxing sports north madras working class period political comeback",
  "kuttrame-thandanai-2016":
    "minimalist noir eyesight moral dilemma witness murder hidden gem",
};

export function detectSearchLanguage(query: string): SearchLanguage {
  const hasTamil = TAMIL_PATTERN.test(query);
  const latinWords = query.toLowerCase().match(/[a-z]+/g) ?? [];
  if (hasTamil && latinWords.length > 0) return "mixed";
  if (hasTamil) return "ta";
  if (latinWords.some((word) => TANGLISH_MARKERS.has(word))) return "tanglish";
  return query.trim() ? "en" : "unknown";
}

export function normalizeDiscoveryQuery(query: string): string {
  return QUERY_REPLACEMENTS.reduce(
    (value, [pattern, replacement]) => value.replace(pattern, replacement),
    query,
  )
    .normalize("NFKC")
    .toLocaleLowerCase("en")
    .replace(/[^\p{L}\p{N}]+/gu, " ")
    .trim();
}

function queryTokens(query: string): string[] {
  return [
    ...new Set(
      normalizeDiscoveryQuery(query)
        .split(/\s+/)
        .filter((token) => token.length > 2 && !STOP_WORDS.has(token)),
    ),
  ];
}

function searchableMovieText(movie: Movie): string {
  return normalizeDiscoveryQuery(
    [
      movie.title,
      movie.originalTitle,
      movie.overview,
      movie.genres.join(" "),
      movie.themes.join(" "),
      movie.director,
      movie.cast.join(" "),
      SEARCH_ALIASES[movie.id],
    ]
      .filter(Boolean)
      .join(" "),
  );
}

function containsAny(values: string[], selected: string[]): boolean {
  const haystack = values.map((value) => value.toLowerCase());
  return selected.some((selection) =>
    haystack.includes(selection.toLowerCase()),
  );
}

function applyFilters(movie: Movie, filters: SearchFilters = {}): boolean {
  if (filters.year_from && (movie.releaseYear ?? 0) < filters.year_from)
    return false;
  if (
    filters.year_to &&
    (movie.releaseYear ?? Number.MAX_SAFE_INTEGER) > filters.year_to
  )
    return false;
  if (filters.genres?.length && !containsAny(movie.genres, filters.genres))
    return false;
  if (filters.themes?.length && !containsAny(movie.themes, filters.themes))
    return false;
  if (filters.runtime_min && (movie.runtimeMinutes ?? 0) < filters.runtime_min)
    return false;
  if (
    filters.runtime_max &&
    (movie.runtimeMinutes ?? Number.MAX_SAFE_INTEGER) > filters.runtime_max
  )
    return false;
  if (
    filters.certifications?.length &&
    (!movie.certificate || !filters.certifications.includes(movie.certificate))
  ) {
    return false;
  }
  if (
    filters.popularity_min !== undefined &&
    movie.prominenceScore < filters.popularity_min
  )
    return false;
  if (
    filters.popularity_max !== undefined &&
    movie.prominenceScore > filters.popularity_max
  )
    return false;
  if (
    filters.data_quality_min !== undefined &&
    (movie.qualityScore ?? 0) < filters.data_quality_min
  )
    return false;
  if (
    filters.actor &&
    !movie.cast.some((name) =>
      name.toLowerCase().includes(filters.actor!.toLowerCase()),
    )
  )
    return false;
  if (
    filters.director &&
    !movie.director?.toLowerCase().includes(filters.director.toLowerCase())
  )
    return false;
  return true;
}

function explanationFor(
  movie: Movie,
  matchedTokens: string[],
  query: string,
): MatchExplanation {
  const normalized = normalizeDiscoveryQuery(query);
  const matchedMetadata = [...movie.genres, ...movie.themes].filter((label) =>
    normalized.includes(normalizeDiscoveryQuery(label)),
  );
  const groundedSignals = [
    ...new Set([...matchedMetadata, ...matchedTokens]),
  ].slice(0, 3);

  if (!query.trim()) {
    return {
      summary: `A high-quality ${movie.genres.slice(0, 2).join(" · ").toLowerCase()} pick for open-ended discovery.`,
      evidence: [
        `${Math.round((movie.qualityScore ?? 0.8) * 100)}% catalog confidence`,
        movie.prominenceScore < 0.35
          ? "Lower mainstream-popularity score"
          : "Strong catalog engagement",
      ],
    };
  }

  const signalText = groundedSignals.length
    ? groundedSignals.join(", ")
    : movie.genres.slice(0, 2).join(" and ");
  return {
    summary: `Strong match for ${signalText || "the intent in your query"}.`,
    evidence: [
      ...matchedMetadata
        .slice(0, 2)
        .map((label) => `${label} appears in verified metadata`),
      ...(matchedTokens.length
        ? [`Matched query language: ${matchedTokens.slice(0, 3).join(", ")}`]
        : []),
    ].slice(0, 3),
  };
}

function scoreMovie(
  movie: Movie,
  query: string,
  beta: number,
): MovieResult | undefined {
  const normalized = normalizeDiscoveryQuery(query);
  const tokens = queryTokens(query);
  const movieText = searchableMovieText(movie);
  const matchedTokens = tokens.filter((token) => movieText.includes(token));
  const exactTitle = normalized.includes(normalizeDiscoveryQuery(movie.title));
  const lexical = tokens.length
    ? Math.min(
        1,
        matchedTokens.length / tokens.length + (exactTitle ? 0.35 : 0),
      )
    : 0.58;
  const semantic = tokens.length
    ? Math.min(1, lexical * 0.78 + (matchedTokens.length ? 0.18 : 0))
    : 0.72;
  const hiddenGem = 1 - movie.prominenceScore;
  const quality = movie.qualityScore ?? 0.8;
  const final = Math.min(
    1,
    semantic * 0.54 + lexical * 0.2 + quality * 0.18 + hiddenGem * beta * 0.08,
  );

  if (tokens.length && matchedTokens.length === 0 && !exactTitle)
    return undefined;

  return {
    ...movie,
    scores: {
      semantic,
      lexical,
      preference: 0,
      quality,
      hiddenGem,
      final,
    },
    explanation: explanationFor(movie, matchedTokens, query),
    plotX: Math.sin(movie.id.length * 1.73) * 0.78,
    plotY: Math.cos(movie.title.length * 1.31) * 0.78,
  };
}

function sortResults(
  results: MovieResult[],
  sort: SearchRequest["sort"],
): MovieResult[] {
  return [...results].sort((a, b) => {
    if (sort === "release_year_desc")
      return (b.releaseYear ?? 0) - (a.releaseYear ?? 0);
    if (sort === "release_year_asc")
      return (a.releaseYear ?? 0) - (b.releaseYear ?? 0);
    if (sort === "hidden_gems") return a.prominenceScore - b.prominenceScore;
    if (sort === "popularity") return b.prominenceScore - a.prominenceScore;
    return b.scores.final - a.scores.final;
  });
}

export function demoSearch(request: SearchRequest): SearchResponse {
  const startedAt = performance.now();
  const page = Math.max(1, request.page ?? 1);
  const pageSize = Math.max(1, request.page_size ?? 20);
  const scored = DEMO_MOVIES.filter((movie) =>
    applyFilters(movie, request.filters),
  )
    .map((movie) => scoreMovie(movie, request.query, request.beta ?? 0.55))
    .filter((movie): movie is MovieResult => Boolean(movie));
  const ordered = sortResults(scored, request.sort);
  const start = (page - 1) * pageSize;
  const results = ordered.slice(start, start + pageSize);

  return {
    query: request.query,
    normalizedQuery: normalizeDiscoveryQuery(request.query),
    detectedLanguage: detectSearchLanguage(request.query),
    queryPlot: request.query.trim() ? { x: 0, y: 0 } : undefined,
    results,
    meta: {
      requestId: `demo-${Date.now().toString(36)}`,
      rankingVersion: "demo-rff-v2.1",
      total: ordered.length,
      page,
      pageSize,
      totalPages: Math.max(1, Math.ceil(ordered.length / pageSize)),
      latencyMs: Math.max(1, Math.round(performance.now() - startedAt)),
    },
    source: "demo",
  };
}

export function demoRecommendations(
  surface: "for_you" | "hidden_gems" | "recent",
  preferences?: UserPreferences,
): RecommendationResponse {
  const movies = [...DEMO_MOVIES];
  if (surface === "hidden_gems")
    movies.sort((a, b) => a.prominenceScore - b.prominenceScore);
  if (surface === "recent")
    movies.sort((a, b) => (b.releaseYear ?? 0) - (a.releaseYear ?? 0));
  if (surface === "for_you" && preferences) {
    movies.sort((a, b) => {
      const preferenceScore = (movie: Movie) =>
        movie.genres.filter((genre) =>
          preferences.favoriteGenres.includes(genre),
        ).length *
          2 +
        movie.themes.filter((theme) =>
          preferences.favoriteThemes.includes(theme),
        ).length +
        (1 - movie.prominenceScore) * preferences.hiddenGemPreference;
      return preferenceScore(b) - preferenceScore(a);
    });
  }

  const results = movies.map((movie) => {
    const preferenceMatches = preferences
      ? [...movie.genres, ...movie.themes].filter(
          (value) =>
            preferences.favoriteGenres.includes(value) ||
            preferences.favoriteThemes.includes(value),
        )
      : [];
    const result = scoreMovie(
      movie,
      "",
      preferences?.hiddenGemPreference ?? 0.55,
    )!;
    result.scores.preference = Math.min(1, preferenceMatches.length * 0.28);
    result.scores.final = Math.min(
      1,
      result.scores.final + result.scores.preference * 0.12,
    );
    result.explanation = {
      summary:
        preferenceMatches.length > 0
          ? `Recommended because it shares your ${preferenceMatches.slice(0, 2).join(" and ")} preferences.`
          : surface === "hidden_gems"
            ? "Lower mainstream-popularity score matches this Hidden Gems shelf."
            : surface === "recent"
              ? "A recent, high-confidence addition to the TamilTrove catalog."
              : "A diverse, high-quality cold-start recommendation.",
      evidence: [
        ...preferenceMatches
          .slice(0, 2)
          .map((value) => `Saved preference: ${value}`),
        `${Math.round((movie.qualityScore ?? 0.8) * 100)}% catalog confidence`,
      ].slice(0, 3),
    };
    return result;
  });

  return {
    results,
    meta: {
      requestId: `demo-recs-${Date.now().toString(36)}`,
      rankingVersion: "demo-content-v2.1",
      total: results.length,
      page: 1,
      pageSize: results.length,
      totalPages: 1,
      latencyMs: 4,
    },
    source: "demo",
  };
}

export function demoSimilar(movieId: string): RecommendationResponse {
  const source = DEMO_MOVIES.find((movie) => movie.id === movieId);
  if (!source) return demoRecommendations("for_you");

  const results = DEMO_MOVIES.filter((movie) => movie.id !== movieId)
    .map((movie) => {
      const shared = [...movie.genres, ...movie.themes].filter(
        (value) =>
          source.genres.includes(value) || source.themes.includes(value),
      );
      const result = scoreMovie(
        movie,
        shared.join(" ") || source.genres.join(" "),
        0.4,
      );
      if (!result) return undefined;
      result.explanation = {
        summary: `Similar to ${source.title} through ${shared.slice(0, 2).join(" and ") || "overall story tone"}.`,
        evidence: shared
          .slice(0, 3)
          .map((value) => `Shared metadata: ${value}`),
      };
      return result;
    })
    .filter((movie): movie is MovieResult => Boolean(movie))
    .sort((a, b) => b.scores.final - a.scores.final)
    .slice(0, 6);

  return {
    results,
    meta: {
      requestId: `demo-similar-${movieId}`,
      rankingVersion: "demo-similar-v2.1",
      total: results.length,
      page: 1,
      pageSize: results.length,
      totalPages: 1,
      latencyMs: 2,
    },
    source: "demo",
  };
}

export function waitForDemo(
  signal?: AbortSignal,
  milliseconds = 420,
): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal?.aborted) {
      reject(new DOMException("The request was cancelled.", "AbortError"));
      return;
    }
    const timer = window.setTimeout(resolve, milliseconds);
    signal?.addEventListener(
      "abort",
      () => {
        window.clearTimeout(timer);
        reject(new DOMException("The request was cancelled.", "AbortError"));
      },
      { once: true },
    );
  });
}
