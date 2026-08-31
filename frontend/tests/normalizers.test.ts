import { describe, expect, it } from "vitest";
import {
  normalizeAuthResponse,
  normalizeCollection,
  normalizeMovie,
  normalizeSearchResponse,
} from "@/lib/normalizers";

describe("API response validation", () => {
  it("normalizes snake_case search payloads into the stable UI model", () => {
    const response = normalizeSearchResponse({
      query: "night chase",
      normalized_query: "night chase",
      detected_language: "english",
      results: [
        {
          movie_id: "movie-1",
          title: "Test",
          genre: "Action / Thriller",
          overview: "A trusted synopsis",
          cast: "Actor One, Actor Two",
          prominence_score: 0.2,
          final_score: 0.83,
          explanation: {
            summary: "Matched night and chase.",
            evidence: ["Theme: chase"],
          },
        },
      ],
      meta: {
        request_id: "req-1",
        ranking_version: "rrf-v2",
        total: 1,
        page: 1,
        page_size: 20,
        latency_ms: 12,
      },
    });
    expect(response.detectedLanguage).toBe("en");
    expect(response.results[0]).toMatchObject({
      id: "movie-1",
      genres: ["Action", "Thriller"],
    });
    expect(response.results[0].scores.final).toBeCloseTo(0.83);
    expect(response.meta.requestId).toBe("req-1");
  });

  it("uses safe fallbacks for incomplete or malformed optional fields", () => {
    expect(normalizeMovie(null)).toMatchObject({
      title: "Untitled film",
      overview: "Synopsis unavailable.",
      genres: [],
      cast: [],
    });
    const response = normalizeSearchResponse({
      results: [{ id: 4, title: "Numeric id", prominence_score: 8 }],
    });
    expect(response.results[0].id).toBe("4");
    expect(response.results[0].prominenceScore).toBe(1);
    expect(response.meta.total).toBe(1);
  });

  it("normalizes account preferences and collection visibility", () => {
    const auth = normalizeAuthResponse({
      access_token: "token",
      profile: {
        id: "u1",
        email: "a@example.com",
        preferences: { favorite_genres: ["Drama"], preferred_eras: ["1990s"] },
        privacy: { store_search_history: false },
      },
    });
    expect(auth.profile.preferences).toMatchObject({
      favoriteGenres: ["Drama"],
      eraFrom: 1990,
      eraTo: 1999,
    });
    expect(auth.profile.privacy.saveSearchHistory).toBe(false);
    expect(
      normalizeCollection({ id: "c1", visibility: "unexpected", items: [] })
        .visibility,
    ).toBe("private");
  });
});
