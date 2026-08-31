"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { apiClient, isAbortError, isNetworkError } from "../lib/api-client";
import { demoRecommendations, waitForDemo } from "../lib/demo-search";
import type { RecommendationResponse } from "../types/api";
import { useApp } from "./app-provider";
import { Icon } from "./icons";
import { MovieCard } from "./movie-card";

type Surface = "for_you" | "hidden_gems" | "recent";
const TABS: Array<{ id: Surface; label: string; description: string }> = [
  {
    id: "for_you",
    label: "For you",
    description: "Based on preferences and explicit feedback",
  },
  {
    id: "hidden_gems",
    label: "Hidden gems",
    description: "High-quality films outside the mainstream",
  },
  {
    id: "recent",
    label: "Recently added",
    description: "Fresh, validated catalog additions",
  },
];

export function RecommendationsPage() {
  const { profile, token, dismissed, liked, ratings } = useApp();
  const [surface, setSurface] = useState<Surface>("for_you");
  const [response, setResponse] = useState<RecommendationResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const requestRef = useRef<AbortController | null>(null);

  const load = useCallback(async () => {
    requestRef.current?.abort();
    const controller = new AbortController();
    requestRef.current = controller;
    setLoading(true);
    setError(null);
    try {
      let result: RecommendationResponse;
      try {
        result = await apiClient.recommendations(
          surface,
          1,
          20,
          controller.signal,
          token,
        );
      } catch (apiError) {
        if (isAbortError(apiError)) throw apiError;
        if (!isNetworkError(apiError)) throw apiError;
        await waitForDemo(controller.signal, 280);
        result = demoRecommendations(surface, profile?.preferences);
      }
      setResponse(result);
    } catch (loadError) {
      if (!isAbortError(loadError))
        setError(
          loadError instanceof Error
            ? loadError.message
            : "Recommendations are unavailable.",
        );
    } finally {
      if (requestRef.current === controller) setLoading(false);
    }
  }, [profile, surface, token]);

  useEffect(() => {
    const timer = window.setTimeout(() => void load(), 0);
    return () => {
      window.clearTimeout(timer);
      requestRef.current?.abort();
    };
  }, [load]);

  const results =
    response?.results.filter((movie) => !dismissed.includes(movie.id)) ?? [];
  const explicitSignals =
    liked.length +
    Object.keys(ratings).length +
    (profile?.preferences.favoriteGenres.length ?? 0);

  return (
    <div className="page-shell">
      <header className="page-hero compact-hero">
        <span className="eyebrow">
          <Icon name="sparkle" width={16} height={16} /> Personal discovery
        </span>
        <h1>
          Films chosen <em>with you,</em> not for you.
        </h1>
        <p>
          Recommendations use only the preferences and feedback you choose to
          share. Every reason is grounded in catalog evidence.
        </p>
      </header>

      {!profile?.onboardingComplete && (
        <aside className="onboarding-banner">
          <div className="banner-icon">
            <Icon name="user" width={25} height={25} />
          </div>
          <div>
            <strong>Make this shelf feel like yours</strong>
            <p>
              Pick a few genres, themes, eras, and films. It takes about a
              minute.
            </p>
          </div>
          <Link className="button button-primary" href="/onboarding">
            Tune my recommendations
          </Link>
        </aside>
      )}

      <div className="recommendation-toolbar">
        <div
          className="tab-list"
          role="tablist"
          aria-label="Recommendation shelves"
        >
          {TABS.map((tab) => (
            <button
              role="tab"
              aria-selected={surface === tab.id}
              key={tab.id}
              onClick={() => setSurface(tab.id)}
            >
              <span>{tab.label}</span>
              <small>{tab.description}</small>
            </button>
          ))}
        </div>
        <div className="signal-meter" title="Count of explicit taste signals">
          <span>{explicitSignals}</span>
          <small>taste signals</small>
        </div>
      </div>

      <div
        className="search-status visually-hidden"
        role="status"
        aria-live="polite"
      >
        {loading
          ? "Loading recommendations"
          : error
            ? `Unable to load recommendations: ${error}`
            : `${results.length} recommendations loaded`}
      </div>

      {loading && (
        <div className="movie-grid">
          {Array.from({ length: 6 }, (_, index) => (
            <div className="movie-card skeleton-card" key={index}>
              <div className="skeleton skeleton-poster" />
              <div className="skeleton-stack">
                <div className="skeleton skeleton-line wide" />
                <div className="skeleton skeleton-line" />
                <div className="skeleton skeleton-copy" />
              </div>
            </div>
          ))}
        </div>
      )}
      {!loading && error && (
        <section className="state-panel error-panel" role="alert">
          <Icon name="retry" width={34} height={34} />
          <h2>Your shelf couldn’t load</h2>
          <p>{error}</p>
          <button className="button button-primary" onClick={() => void load()}>
            <Icon name="retry" width={17} height={17} />
            Retry
          </button>
        </section>
      )}
      {!loading && !error && results.length === 0 && (
        <section className="state-panel">
          <Icon name="film" width={36} height={36} />
          <h2>You’re all caught up</h2>
          <p>
            You dismissed every film on this shelf. Restore titles from your
            profile or try another shelf.
          </p>
          <Link href="/profile#dismissed" className="button button-primary">
            Review dismissed films
          </Link>
        </section>
      )}
      {!loading && !error && results.length > 0 && (
        <section aria-labelledby="recommendations-title">
          <div className="results-heading">
            <div>
              <span className="eyebrow">
                {response?.source === "demo"
                  ? "On-device preview"
                  : response?.meta.rankingVersion}
              </span>
              <h2 id="recommendations-title">
                {TABS.find((tab) => tab.id === surface)?.label}
              </h2>
            </div>
            <p>Updated from your explicit feedback</p>
          </div>
          {response?.source === "demo" && (
            <div className="inline-notice">
              <Icon name="info" width={18} height={18} />
              Live recommendations are offline. This preview is computed locally
              from your saved preferences.
            </div>
          )}
          <div className="movie-grid">
            {results.map((movie, index) => (
              <MovieCard key={movie.id} movie={movie} index={index} />
            ))}
          </div>
        </section>
      )}
    </div>
  );
}
