import { describe, expect, it } from "vitest";
import {
  demoSearch,
  detectSearchLanguage,
  normalizeDiscoveryQuery,
} from "@/lib/demo-search";

describe("multilingual demo retrieval", () => {
  it("detects Tamil, Tanglish, mixed, and English queries", () => {
    expect(detectSearchLanguage("கிராம வாழ்க்கை படம்")).toBe("ta");
    expect(detectSearchLanguage("oru semma village padam")).toBe("tanglish");
    expect(detectSearchLanguage("தமிழ் courtroom drama")).toBe("mixed");
    expect(detectSearchLanguage("a courtroom drama")).toBe("en");
  });

  it("normalizes known Tamil and Tanglish vocabulary", () => {
    expect(normalizeDiscoveryQuery("கிராம கதை")).toContain("village");
    expect(normalizeDiscoveryQuery("kaadhal padam")).toContain("romance");
  });

  it("applies structured filters and returns grounded explanations", () => {
    const response = demoSearch({
      query: "village farmer",
      filters: { genres: ["Drama"], runtime_max: 150 },
      page_size: 20,
    });
    expect(response.results.length).toBeGreaterThan(0);
    expect(
      response.results.every(
        (movie) =>
          movie.genres.includes("Drama") && (movie.runtimeMinutes ?? 0) <= 150,
      ),
    ).toBe(true);
    expect(response.results[0].explanation.summary).not.toHaveLength(0);
    expect(response.source).toBe("demo");
  });

  it("returns a stable empty state for mutually exclusive filters", () => {
    const response = demoSearch({
      query: "boxing",
      filters: { year_to: 1950 },
      page_size: 20,
    });
    expect(response.results).toEqual([]);
    expect(response.meta.total).toBe(0);
  });
});
