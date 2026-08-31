"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { apiClient, isAbortError, isNetworkError } from "../lib/api-client";
import { getDemoMovie } from "../lib/demo-data";
import { demoSimilar, waitForDemo } from "../lib/demo-search";
import type { Movie, RecommendationResponse } from "../types/api";
import { useApp } from "./app-provider";
import { Icon } from "./icons";
import { MovieActions } from "./movie-actions";
import { MovieCard } from "./movie-card";
import { MoviePoster } from "./movie-poster";

export function MovieDetail({ id }: { id: string }) {
  const { token, markViewed } = useApp();
  const [movie, setMovie] = useState<Movie | null>(null);
  const [similar, setSimilar] = useState<RecommendationResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const marked = useRef(false);

  const load = useCallback(async () => {
    const controller = new AbortController();
    setLoading(true);
    setError(null);
    try {
      let selected: Movie;
      try {
        selected = await apiClient.movie(id, controller.signal, token);
      } catch (apiError) {
        if (isAbortError(apiError)) throw apiError;
        if (!isNetworkError(apiError)) throw apiError;
        await waitForDemo(controller.signal, 180);
        const demo = getDemoMovie(id);
        if (!demo) throw new Error("This film is not in the current catalog.");
        selected = demo;
      }
      setMovie(selected);
      if (!marked.current) {
        marked.current = true;
        markViewed(selected);
      }
      try {
        setSimilar(await apiClient.similar(id, 1, 6, controller.signal, token));
      } catch (similarError) {
        if (!isAbortError(similarError)) setSimilar(demoSimilar(id));
      }
    } catch (loadError) {
      if (!isAbortError(loadError))
        setError(
          loadError instanceof Error
            ? loadError.message
            : "Movie details are unavailable.",
        );
    } finally {
      setLoading(false);
    }
    return () => controller.abort();
  }, [id, markViewed, token]);

  useEffect(() => {
    const timer = window.setTimeout(() => void load(), 0);
    return () => window.clearTimeout(timer);
  }, [load]);

  if (loading)
    return (
      <div className="page-shell">
        <div className="detail-skeleton">
          <div className="skeleton skeleton-detail-poster" />
          <div className="skeleton-stack">
            <div className="skeleton skeleton-line short" />
            <div className="skeleton skeleton-line wide" />
            <div className="skeleton skeleton-copy large" />
          </div>
        </div>
        <span className="visually-hidden" role="status">
          Loading movie details
        </span>
      </div>
    );
  if (error || !movie)
    return (
      <div className="page-shell">
        <section className="state-panel error-panel" role="alert">
          <Icon name="film" width={38} height={38} />
          <h1>Film not available</h1>
          <p>{error ?? "This catalog record could not be found."}</p>
          <div className="state-actions">
            <Link className="button button-secondary" href="/">
              Back to discovery
            </Link>
            <button
              className="button button-primary"
              onClick={() => void load()}
            >
              Try again
            </button>
          </div>
        </section>
      </div>
    );

  return (
    <div className="page-shell detail-page">
      <nav className="breadcrumbs" aria-label="Breadcrumb">
        <Link href="/">Discover</Link>
        <Icon name="chevron" width={14} height={14} />
        <span aria-current="page">{movie.title}</span>
      </nav>
      <article className="movie-detail-hero">
        <div className="detail-poster-wrap">
          <MoviePoster movie={movie} priority />
          <span
            className={`quality-badge quality-${movie.dataQualityStatus ?? "unknown"}`}
          >
            <Icon name="shield" width={15} height={15} />
            {movie.dataQualityStatus === "verified"
              ? "Verified record"
              : "Catalog record"}
          </span>
        </div>
        <div className="detail-copy">
          <span className="eyebrow">
            {movie.language} cinema · {movie.releaseYear ?? "Year unavailable"}
          </span>
          <h1>{movie.title}</h1>
          {movie.originalTitle && movie.originalTitle !== movie.title && (
            <p className="detail-original" lang="ta">
              {movie.originalTitle}
            </p>
          )}
          <div className="detail-facts">
            <span>{movie.certificate ?? "Not rated"}</span>
            {movie.runtimeMinutes && (
              <span>{movie.runtimeMinutes} minutes</span>
            )}
            <span>
              {Math.round(movie.prominenceScore * 100)} mainstream score
            </span>
          </div>
          <div className="chip-row">
            {[...movie.genres, ...movie.themes].map((tag) => (
              <span className="chip" key={tag}>
                {tag}
              </span>
            ))}
          </div>
          <p className="detail-overview">{movie.overview}</p>
          <dl className="credit-list">
            <div>
              <dt>Directed by</dt>
              <dd>{movie.director ?? "Not available"}</dd>
            </div>
            <div>
              <dt>Cast</dt>
              <dd>
                {movie.cast.length ? movie.cast.join(", ") : "Not available"}
              </dd>
            </div>
          </dl>
          <MovieActions movie={movie} allowDismiss={false} />
        </div>
      </article>

      <div className="detail-columns">
        <section
          className="evidence-panel"
          aria-labelledby="match-evidence-title"
        >
          <span className="eyebrow">
            <Icon name="sparkle" width={15} height={15} /> Transparent
            recommendation
          </span>
          <h2 id="match-evidence-title">Why this film appears</h2>
          <p>
            On a search result, this section uses matched phrases, genres,
            themes, and score contributions. Direct visits use only trusted
            catalog metadata.
          </p>
          <ul>
            {movie.themes.slice(0, 3).map((theme) => (
              <li key={theme}>
                <Icon name="check" width={16} height={16} />
                <span>
                  <strong>{theme}</strong> is attached to this canonical catalog
                  record.
                </span>
              </li>
            ))}
            {movie.genres.slice(0, 2).map((genre) => (
              <li key={genre}>
                <Icon name="check" width={16} height={16} />
                <span>
                  Classified as <strong>{genre}</strong>.
                </span>
              </li>
            ))}
          </ul>
        </section>
        <aside className="source-panel">
          <span className="eyebrow">Catalog transparency</span>
          <h2>About this record</h2>
          <dl>
            <div>
              <dt>Quality score</dt>
              <dd>
                {movie.qualityScore !== undefined
                  ? `${Math.round(movie.qualityScore * 100)}%`
                  : "Not scored"}
              </dd>
            </div>
            <div>
              <dt>Last updated</dt>
              <dd>
                {movie.sourceUpdatedAt
                  ? new Date(movie.sourceUpdatedAt).toLocaleDateString()
                  : "Versioned import"}
              </dd>
            </div>
            <div>
              <dt>Source</dt>
              <dd>
                {movie.sourceUrl ? (
                  <a href={movie.sourceUrl} target="_blank" rel="noreferrer">
                    View provenance <span aria-hidden="true">↗</span>
                  </a>
                ) : (
                  "Internal catalog"
                )}
              </dd>
            </div>
          </dl>
        </aside>
      </div>

      <section className="similar-section" aria-labelledby="similar-title">
        <div className="results-heading">
          <div>
            <span className="eyebrow">Shared stories and themes</span>
            <h2 id="similar-title">More like {movie.title}</h2>
          </div>
          <Link href={`/?q=${encodeURIComponent(movie.title)}`}>
            Search related films <Icon name="arrow" width={16} height={16} />
          </Link>
        </div>
        {similar?.results.length ? (
          <div className="movie-grid compact-grid">
            {similar.results.map((item, index) => (
              <MovieCard key={item.id} movie={item} index={index} compact />
            ))}
          </div>
        ) : (
          <div className="inline-notice">
            <Icon name="info" width={18} height={18} />
            Similar films are temporarily unavailable.
          </div>
        )}
      </section>
    </div>
  );
}
