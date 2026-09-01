import {
  normalizeAuthResponse,
  normalizeCollection,
  normalizeCollectionList,
  normalizeDataQualityReport,
  normalizeMovie,
  normalizeRecommendationResponse,
  normalizeSearchResponse,
  normalizeChatResponse,
  normalizeProfile,
} from "./normalizers";
import type {
  AuthResponse,
  CollectionVisibility,
  DataQualityReport,
  Interaction,
  InteractionType,
  Movie,
  MovieCollection,
  RecommendationResponse,
  SearchRequest,
  SearchResponse,
  ChatResponse,
  UserProfile,
} from "../types/api";

const API_ORIGIN = (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000")
  .replace(/\/+$/, "")
  .replace(/\/api\/v1$/, "");

export class ApiClientError extends Error {
  readonly status: number;
  readonly code?: string;
  readonly requestId?: string;
  readonly details?: unknown;

  constructor(
    message: string,
    options: {
      status: number;
      code?: string;
      requestId?: string;
      details?: unknown;
    },
  ) {
    super(message);
    this.name = "ApiClientError";
    this.status = options.status;
    this.code = options.code;
    this.requestId = options.requestId;
    this.details = options.details;
  }
}

export const isAbortError = (error: unknown): boolean =>
  error instanceof DOMException && error.name === "AbortError";

export const isNetworkError = (error: unknown): boolean =>
  error instanceof TypeError && !isAbortError(error);

type RequestOptions = Omit<RequestInit, "body"> & {
  token?: string | null;
  body?: unknown;
};

function errorMessage(payload: unknown, status: number): ApiClientError {
  const envelope =
    typeof payload === "object" && payload !== null
      ? (payload as Record<string, unknown>)
      : {};
  const nested =
    typeof envelope.error === "object" && envelope.error !== null
      ? (envelope.error as Record<string, unknown>)
      : {};
  const detail = envelope.detail;
  const validationMessage = Array.isArray(detail)
    ? detail
        .map((item) =>
          typeof item === "object" && item !== null && "msg" in item
            ? String((item as { msg: unknown }).msg)
            : "",
        )
        .filter(Boolean)
        .join("; ")
    : undefined;

  return new ApiClientError(
    (typeof nested.message === "string" && nested.message) ||
      (typeof detail === "string" && detail) ||
      validationMessage ||
      (typeof envelope.message === "string" && envelope.message) ||
      `Request failed (${status})`,
    {
      status,
      code: typeof nested.code === "string" ? nested.code : undefined,
      requestId:
        typeof nested.request_id === "string" ? nested.request_id : undefined,
      details: nested.details,
    },
  );
}

async function request<T>(
  path: string,
  options: RequestOptions = {},
): Promise<T> {
  const headers = new Headers(options.headers);
  if (options.body !== undefined)
    headers.set("Content-Type", "application/json");
  if (options.token) headers.set("Authorization", `Bearer ${options.token}`);
  const method = (options.method || "GET").toUpperCase();
  if (
    typeof document !== "undefined" &&
    !["GET", "HEAD", "OPTIONS"].includes(method)
  ) {
    const csrfCookie = document.cookie
      .split("; ")
      .find((cookie) => cookie.startsWith("tt_csrf="))
      ?.split("=")
      .slice(1)
      .join("=");
    if (csrfCookie) headers.set("X-CSRF-Token", decodeURIComponent(csrfCookie));
  }
  headers.set("Accept", "application/json");

  const response = await fetch(`${API_ORIGIN}${path}`, {
    ...options,
    headers,
    body: options.body === undefined ? undefined : JSON.stringify(options.body),
    credentials: "include",
  });

  if (response.status === 204) return undefined as T;
  const payload = (await response.json().catch(() => undefined)) as unknown;
  if (!response.ok) throw errorMessage(payload, response.status);
  return payload as T;
}

export const apiClient = {
  async search(
    input: SearchRequest,
    signal?: AbortSignal,
    token?: string | null,
  ): Promise<SearchResponse> {
    const payload = await request<unknown>("/api/v1/search", {
      method: "POST",
      body: input,
      signal,
      token,
    });
    return normalizeSearchResponse(payload);
  },

  async chat(
    query: string,
    signal?: AbortSignal,
    token?: string | null,
  ): Promise<ChatResponse> {
    const payload = await request<unknown>("/api/v1/chat", {
      method: "POST",
      body: { query },
      signal,
      token,
    });
    return normalizeChatResponse(payload);
  },

  async movie(
    id: string,
    signal?: AbortSignal,
    token?: string | null,
  ): Promise<Movie> {
    const payload = await request<unknown>(
      `/api/v1/movies/${encodeURIComponent(id)}`,
      { signal, token },
    );
    const raw =
      typeof payload === "object" && payload !== null && "movie" in payload
        ? (payload as { movie: unknown }).movie
        : payload;
    return normalizeMovie(raw, id);
  },

  async similar(
    id: string,
    page = 1,
    pageSize = 8,
    signal?: AbortSignal,
    token?: string | null,
  ): Promise<RecommendationResponse> {
    const payload = await request<unknown>(
      `/api/v1/movies/${encodeURIComponent(id)}/similar?page=${page}&page_size=${pageSize}`,
      { signal, token },
    );
    return normalizeRecommendationResponse(payload);
  },

  async recommendations(
    surface: "for_you" | "hidden_gems" | "recent" = "for_you",
    page = 1,
    pageSize = 20,
    signal?: AbortSignal,
    token?: string | null,
  ): Promise<RecommendationResponse> {
    const payload = await request<unknown>(
      `/api/v1/recommendations?surface=${surface}&page=${page}&page_size=${pageSize}`,
      { signal, token },
    );
    return normalizeRecommendationResponse(payload);
  },

  async login(email: string, password: string): Promise<AuthResponse> {
    const payload = await request<unknown>("/api/v1/auth/login", {
      method: "POST",
      body: { email, password },
    });
    return normalizeAuthResponse(payload);
  },

  async register(
    email: string,
    password: string,
    displayName: string,
  ): Promise<AuthResponse> {
    const payload = await request<unknown>("/api/v1/auth/register", {
      method: "POST",
      body: { email, password, display_name: displayName },
    });
    return normalizeAuthResponse(payload);
  },

  async logout(token?: string | null): Promise<void> {
    await request<void>("/api/v1/auth/logout", { method: "POST", token });
  },

  async profile(token?: string | null): Promise<UserProfile> {
    return normalizeProfile(
      await request<unknown>("/api/v1/profile", { token }),
    );
  },

  async updateProfile(
    profile: Partial<UserProfile>,
    token?: string | null,
  ): Promise<UserProfile> {
    const preferredEras: string[] = [];
    if (profile.preferences) {
      for (
        let decade = Math.floor(profile.preferences.eraFrom / 10) * 10;
        decade <= profile.preferences.eraTo;
        decade += 10
      ) {
        preferredEras.push(`${decade}s`);
      }
    }
    const body = {
      display_name: profile.displayName,
      locale: profile.locale,
      preferences: profile.preferences
        ? {
            favorite_genres: profile.preferences.favoriteGenres,
            favorite_themes: profile.preferences.favoriteThemes,
            preferred_eras: preferredEras,
            hidden_gem_preference: profile.preferences.hiddenGemPreference,
            languages: profile.preferences.preferredLanguages,
            dubbing_tolerance: profile.preferences.acceptsDubbed,
            onboarding_movie_ids: profile.preferences.onboardingMovieIds,
          }
        : undefined,
      privacy: profile.privacy
        ? {
            store_search_history: profile.privacy.saveSearchHistory,
            use_interactions_for_recommendations:
              profile.privacy.personalizeRecommendations,
            analytics_consent: profile.preferences?.analyticsConsent,
          }
        : undefined,
    };
    return normalizeProfile(
      await request<unknown>("/api/v1/profile", {
        method: "PATCH",
        body,
        token,
      }),
    );
  },

  async exportProfile(token?: string | null): Promise<unknown> {
    return request<unknown>("/api/v1/profile/export", { token });
  },

  async deleteProfile(token?: string | null): Promise<void> {
    await request<void>("/api/v1/profile", { method: "DELETE", token });
  },

  async interaction(
    movieId: string,
    type: InteractionType,
    value?: number,
    context?: Record<string, unknown>,
    token?: string | null,
  ): Promise<Interaction | undefined> {
    return request<Interaction | undefined>("/api/v1/interactions", {
      method: "POST",
      body: { movie_id: movieId, type, value, context },
      token,
    });
  },

  async deleteInteraction(
    type: InteractionType,
    movieId: string,
    token?: string | null,
  ): Promise<void> {
    await request<void>(
      `/api/v1/interactions/${type}/${encodeURIComponent(movieId)}`,
      {
        method: "DELETE",
        token,
      },
    );
  },

  async addWatchlist(movieId: string, token?: string | null): Promise<void> {
    await request<void>(`/api/v1/watchlist/${encodeURIComponent(movieId)}`, {
      method: "PUT",
      token,
    });
  },

  async removeWatchlist(movieId: string, token?: string | null): Promise<void> {
    await request<void>(`/api/v1/watchlist/${encodeURIComponent(movieId)}`, {
      method: "DELETE",
      token,
    });
  },

  async collections(token?: string | null): Promise<MovieCollection[]> {
    return normalizeCollectionList(
      await request<unknown>("/api/v1/collections", { token }),
    );
  },

  async createCollection(
    name: string,
    description: string,
    visibility: CollectionVisibility,
    token?: string | null,
  ): Promise<MovieCollection> {
    return normalizeCollection(
      await request<unknown>("/api/v1/collections", {
        method: "POST",
        body: { name, description, visibility },
        token,
      }),
    );
  },

  async updateCollection(
    id: string,
    changes: Partial<
      Pick<MovieCollection, "name" | "description" | "visibility">
    >,
    token?: string | null,
  ): Promise<MovieCollection> {
    return normalizeCollection(
      await request<unknown>(`/api/v1/collections/${encodeURIComponent(id)}`, {
        method: "PATCH",
        body: changes,
        token,
      }),
    );
  },

  async deleteCollection(id: string, token?: string | null): Promise<void> {
    await request<void>(`/api/v1/collections/${encodeURIComponent(id)}`, {
      method: "DELETE",
      token,
    });
  },

  async addCollectionItem(
    collectionId: string,
    movieId: string,
    position?: number,
    token?: string | null,
  ): Promise<void> {
    await request<void>(
      `/api/v1/collections/${encodeURIComponent(collectionId)}/items`,
      {
        method: "POST",
        body: { movie_id: movieId, position },
        token,
      },
    );
  },

  async removeCollectionItem(
    collectionId: string,
    movieId: string,
    token?: string | null,
  ): Promise<void> {
    await request<void>(
      `/api/v1/collections/${encodeURIComponent(collectionId)}/items/${encodeURIComponent(movieId)}`,
      { method: "DELETE", token },
    );
  },

  async shareCollection(
    id: string,
    token?: string | null,
  ): Promise<MovieCollection> {
    return normalizeCollection(
      await request<unknown>(
        `/api/v1/collections/${encodeURIComponent(id)}/share`,
        {
          method: "POST",
          token,
        },
      ),
    );
  },

  async sharedCollection(
    token: string,
    signal?: AbortSignal,
  ): Promise<MovieCollection> {
    return normalizeCollection(
      await request<unknown>(
        `/api/v1/collections/shared/${encodeURIComponent(token)}`,
        { signal },
      ),
    );
  },

  async clearSearchHistory(token?: string | null): Promise<void> {
    await request<void>("/api/v1/history/search", { method: "DELETE", token });
  },

  async resetInteractions(token?: string | null): Promise<UserProfile> {
    return normalizeProfile(
      await request<unknown>("/api/v1/profile", {
        method: "PATCH",
        body: { reset_interactions: true },
        token,
      }),
    );
  },

  async dataQuality(
    token?: string | null,
    signal?: AbortSignal,
  ): Promise<DataQualityReport> {
    return normalizeDataQualityReport(
      await request<unknown>("/api/v1/admin/data-quality", { token, signal }),
    );
  },
};

export const apiOrigin = API_ORIGIN;
