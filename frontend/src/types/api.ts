export type SearchLanguage = "en" | "ta" | "tanglish" | "mixed" | "unknown";

export type InteractionType =
  | "impression"
  | "click"
  | "save"
  | "rating"
  | "like"
  | "dislike"
  | "dismiss"
  | "viewed";

export type CollectionVisibility = "private" | "unlisted" | "public";

export type SearchSort =
  | "relevance"
  | "release_year_desc"
  | "release_year_asc"
  | "hidden_gems"
  | "popularity";

export interface RankingScores {
  semantic: number;
  lexical: number;
  preference: number;
  quality: number;
  hiddenGem: number;
  final: number;
}

export interface MatchExplanation {
  summary: string;
  evidence: string[];
}

export interface Movie {
  id: string;
  title: string;
  originalTitle?: string;
  releaseYear?: number;
  runtimeMinutes?: number;
  certificate?: string;
  overview: string;
  language: string;
  posterUrl?: string;
  sourceUrl?: string;
  sourceUpdatedAt?: string;
  dataQualityStatus?: string;
  genres: string[];
  themes: string[];
  director?: string;
  cast: string[];
  prominenceScore: number;
  qualityScore?: number;
}

export interface MovieResult extends Movie {
  scores: RankingScores;
  explanation: MatchExplanation;
  plotX?: number;
  plotY?: number;
}

export interface SearchFilters {
  year_from?: number;
  year_to?: number;
  genres?: string[];
  themes?: string[];
  actor?: string;
  director?: string;
  runtime_min?: number;
  runtime_max?: number;
  certifications?: string[];
  popularity_min?: number;
  popularity_max?: number;
  data_quality_min?: number;
  exclude_watched?: boolean;
  exclude_dismissed?: boolean;
}

export interface SearchRequest {
  query: string;
  filters?: SearchFilters;
  sort?: SearchSort;
  page?: number;
  page_size?: number;
  alpha?: number;
  beta?: number;
  diversity?: number;
  include_debug?: boolean;
}

export interface PaginationMeta {
  requestId: string;
  rankingVersion: string;
  total: number;
  page: number;
  pageSize: number;
  totalPages: number;
  latencyMs: number;
}

export interface SearchResponse {
  query: string;
  normalizedQuery: string;
  detectedLanguage: SearchLanguage;
  queryPlot?: { x: number; y: number };
  results: MovieResult[];
  meta: PaginationMeta;
  source: "api" | "demo";
}

export interface RecommendationResponse {
  results: MovieResult[];
  meta: PaginationMeta;
  source: "api" | "demo";
}

export interface UserPreferences {
  favoriteGenres: string[];
  favoriteThemes: string[];
  eraFrom: number;
  eraTo: number;
  hiddenGemPreference: number;
  preferredLanguages: string[];
  acceptsDubbed: boolean;
  analyticsConsent: boolean;
  onboardingMovieIds: string[];
}

export interface PrivacySettings {
  profileVisible: boolean;
  saveSearchHistory: boolean;
  personalizeRecommendations: boolean;
}

export interface UserProfile {
  id: string;
  email: string;
  displayName: string;
  locale: string;
  onboardingComplete: boolean;
  isAdmin: boolean;
  preferences: UserPreferences;
  privacy: PrivacySettings;
  createdAt?: string;
  updatedAt?: string;
}

export interface DataQualityIssue {
  index: number;
  reason: string;
}

export interface DataQualityReport {
  datasetVersion: string;
  generatedAt: string;
  sourceRecords: number;
  acceptedRecords: number;
  invalidRecords: DataQualityIssue[];
  duplicateIdentities: string[];
  needsReview: number;
  missingPosters: number;
  shortOverviews: number;
  embeddingErrors: string[];
  qualityDistribution: {
    validated: number;
    needsReview: number;
    quarantined: number;
  };
  semanticBackend: string;
  degradedReasons: string[];
}

export interface AuthResponse {
  accessToken?: string;
  tokenType: string;
  expiresIn?: number;
  profile: UserProfile;
}

export interface Interaction {
  id?: string;
  movieId: string;
  type: InteractionType;
  value?: number;
  context?: Record<string, unknown>;
  createdAt: string;
}

export interface SearchHistoryItem {
  id: string;
  query: string;
  detectedLanguage: SearchLanguage;
  resultCount: number;
  filters: SearchFilters;
  createdAt: string;
}

export interface CollectionItem {
  movieId: string;
  position: number;
  movie?: Movie;
  addedAt?: string;
}

export interface MovieCollection {
  id: string;
  ownerId?: string;
  ownerDisplayName?: string;
  name: string;
  description: string;
  visibility: CollectionVisibility;
  items: CollectionItem[];
  shareToken?: string;
  shareUrl?: string;
  createdAt?: string;
  updatedAt?: string;
}

export interface ApiErrorEnvelope {
  error?: {
    code?: string;
    message?: string;
    details?: unknown;
    request_id?: string;
  };
  detail?: string | Array<{ msg?: string }>;
  message?: string;
}
