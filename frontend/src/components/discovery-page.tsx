"use client";

import {
  FormEvent,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import {
  apiClient,
  ApiClientError,
  isAbortError,
  isNetworkError,
} from "../lib/api-client";
import { demoSearch, waitForDemo } from "../lib/demo-search";
import { GENRE_OPTIONS, THEME_OPTIONS } from "../lib/demo-data";
import type {
  SearchFilters,
  SearchRequest,
  SearchResponse,
  SearchSort,
} from "../types/api";
import { useApp } from "./app-provider";
import { Icon } from "./icons";
import { MovieCard } from "./movie-card";

const EXAMPLES = [
  {
    label: "English",
    query: "A tense one-night thriller about a parent protecting a child",
  },
  { label: "தமிழ்", query: "கிராம வாழ்க்கை பற்றிய மனதை தொடும் படம்" },
  { label: "Tanglish", query: "courtroom-la injustice fight panra padam" },
];

const EMPTY_FILTERS: SearchFilters = {};

function activeFilterLabels(
  filters: SearchFilters,
): Array<{ key: string; label: string }> {
  const labels: Array<{ key: string; label: string }> = [];
  filters.genres?.forEach((genre) =>
    labels.push({ key: `genre:${genre}`, label: genre }),
  );
  filters.themes?.forEach((theme) =>
    labels.push({ key: `theme:${theme}`, label: theme }),
  );
  if (filters.year_from)
    labels.push({ key: "year_from", label: `From ${filters.year_from}` });
  if (filters.year_to)
    labels.push({ key: "year_to", label: `Through ${filters.year_to}` });
  if (filters.runtime_max)
    labels.push({
      key: "runtime_max",
      label: `Under ${filters.runtime_max} min`,
    });
  if (filters.actor)
    labels.push({ key: "actor", label: `Cast: ${filters.actor}` });
  if (filters.director)
    labels.push({ key: "director", label: `Director: ${filters.director}` });
  if (filters.popularity_max !== undefined)
    labels.push({ key: "popularity_max", label: "Lower-profile films" });
  if (filters.exclude_watched)
    labels.push({ key: "exclude_watched", label: "Hide watched" });
  return labels;
}

function removeFilter(filters: SearchFilters, key: string): SearchFilters {
  const next = { ...filters };
  if (key.startsWith("genre:"))
    next.genres = next.genres?.filter((value) => value !== key.slice(6));
  else if (key.startsWith("theme:"))
    next.themes = next.themes?.filter((value) => value !== key.slice(6));
  else delete next[key as keyof SearchFilters];
  if (!next.genres?.length) delete next.genres;
  if (!next.themes?.length) delete next.themes;
  return next;
}

function FilterDrawer({
  open,
  filters,
  onChange,
  onClose,
}: {
  open: boolean;
  filters: SearchFilters;
  onChange: (filters: SearchFilters) => void;
  onClose: () => void;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    if (open && !dialog.open) dialog.showModal();
    if (!open && dialog.open) dialog.close();
  }, [open]);

  const toggleList = (field: "genres" | "themes", value: string) => {
    const selected = filters[field] ?? [];
    onChange({
      ...filters,
      [field]: selected.includes(value)
        ? selected.filter((item) => item !== value)
        : [...selected, value],
    });
  };

  return (
    <dialog
      ref={ref}
      className="drawer-dialog"
      aria-labelledby="filter-heading"
      onClose={onClose}
      onCancel={onClose}
      onClick={(event) =>
        event.target === event.currentTarget && event.currentTarget.close()
      }
    >
      <section className="drawer-panel">
        <header className="dialog-header">
          <div>
            <span className="eyebrow">Refine without losing the story</span>
            <h2 id="filter-heading">Search filters</h2>
          </div>
          <button
            className="icon-button"
            type="button"
            onClick={() => ref.current?.close()}
            aria-label="Close filters"
          >
            <Icon name="x" width={21} height={21} />
          </button>
        </header>

        <fieldset className="filter-fieldset">
          <legend>Genres</legend>
          <div className="check-grid">
            {GENRE_OPTIONS.map((genre) => (
              <label key={genre}>
                <input
                  type="checkbox"
                  checked={filters.genres?.includes(genre) ?? false}
                  onChange={() => toggleList("genres", genre)}
                />
                <span>{genre}</span>
              </label>
            ))}
          </div>
        </fieldset>

        <fieldset className="filter-fieldset">
          <legend>Themes</legend>
          <div className="check-grid">
            {THEME_OPTIONS.map((theme) => (
              <label key={theme}>
                <input
                  type="checkbox"
                  checked={filters.themes?.includes(theme) ?? false}
                  onChange={() => toggleList("themes", theme)}
                />
                <span>{theme}</span>
              </label>
            ))}
          </div>
        </fieldset>

        <div className="field-grid">
          <label>
            Released after
            <input
              type="number"
              min="1931"
              max="2030"
              value={filters.year_from ?? ""}
              onChange={(event) =>
                onChange({
                  ...filters,
                  year_from: event.target.value
                    ? Number(event.target.value)
                    : undefined,
                })
              }
            />
          </label>
          <label>
            Released before
            <input
              type="number"
              min="1931"
              max="2030"
              value={filters.year_to ?? ""}
              onChange={(event) =>
                onChange({
                  ...filters,
                  year_to: event.target.value
                    ? Number(event.target.value)
                    : undefined,
                })
              }
            />
          </label>
          <label>
            Maximum runtime
            <input
              type="number"
              min="45"
              max="360"
              step="5"
              value={filters.runtime_max ?? ""}
              onChange={(event) =>
                onChange({
                  ...filters,
                  runtime_max: event.target.value
                    ? Number(event.target.value)
                    : undefined,
                })
              }
            />
          </label>
          <label>
            Actor
            <input
              value={filters.actor ?? ""}
              onChange={(event) =>
                onChange({ ...filters, actor: event.target.value || undefined })
              }
              placeholder="e.g. Karthi"
            />
          </label>
          <label className="field-wide">
            Director
            <input
              value={filters.director ?? ""}
              onChange={(event) =>
                onChange({
                  ...filters,
                  director: event.target.value || undefined,
                })
              }
              placeholder="e.g. Mani Ratnam"
            />
          </label>
        </div>

        <div className="toggle-list">
          <label className="switch-row">
            <span>
              <strong>Prioritize hidden gems</strong>
              <small>Limit mainstream-prominence score</small>
            </span>
              <input
                type="checkbox"
                aria-label="Prioritize hidden gems"
                checked={filters.popularity_max !== undefined}
              onChange={(event) =>
                onChange({
                  ...filters,
                  popularity_max: event.target.checked ? 0.45 : undefined,
                })
              }
            />
          </label>
          <label className="switch-row">
            <span>
              <strong>Hide already viewed</strong>
              <small>Uses your private activity history</small>
            </span>
              <input
                type="checkbox"
                aria-label="Hide already viewed"
                checked={filters.exclude_watched ?? false}
              onChange={(event) =>
                onChange({
                  ...filters,
                  exclude_watched: event.target.checked || undefined,
                })
              }
            />
          </label>
        </div>

        <footer className="drawer-footer">
          <button
            className="button button-secondary"
            type="button"
            onClick={() => onChange(EMPTY_FILTERS)}
          >
            Clear all
          </button>
          <button
            className="button button-primary"
            type="button"
            onClick={() => ref.current?.close()}
          >
            Show matches
          </button>
        </footer>
      </section>
    </dialog>
  );
}

export function DiscoveryPage() {
  const { token, dismissed, addSearchHistory } = useApp();
  const [query, setQuery] = useState("");
  const [filters, setFilters] = useState<SearchFilters>(EMPTY_FILTERS);
  const [sort, setSort] = useState<SearchSort>("relevance");
  const [hiddenGem, setHiddenGem] = useState(0.55);
  const [page, setPage] = useState(1);
  const [response, setResponse] = useState<SearchResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [filtersOpen, setFiltersOpen] = useState(false);
  const activeRequest = useRef<AbortController | null>(null);
  const lastRequest = useRef<SearchRequest | null>(null);

  useEffect(() => () => activeRequest.current?.abort(), []);

  const runSearch = useCallback(
    async (request: SearchRequest) => {
      activeRequest.current?.abort();
      const controller = new AbortController();
      activeRequest.current = controller;
      lastRequest.current = request;
      setLoading(true);
      setError(null);
      try {
        let next: SearchResponse;
        try {
          next = await apiClient.search(request, controller.signal, token);
        } catch (apiError) {
          if (isAbortError(apiError)) throw apiError;
          if (!isNetworkError(apiError)) throw apiError;
          await waitForDemo(controller.signal, 360);
          next = demoSearch(request);
        }
        setResponse(next);
        setPage(next.meta.page);
        addSearchHistory(
          next.query,
          next.detectedLanguage,
          next.meta.total,
          request.filters ?? {},
        );
      } catch (searchError) {
        if (isAbortError(searchError)) return;
        setResponse(null);
        setError(
          searchError instanceof ApiClientError
            ? searchError.message
            : "Search is temporarily unavailable. Please retry.",
        );
      } finally {
        if (activeRequest.current === controller) {
          activeRequest.current = null;
          setLoading(false);
        }
      }
    },
    [addSearchHistory, token],
  );

  const submit = (event?: FormEvent) => {
    event?.preventDefault();
    if (!query.trim()) return;
    void runSearch({
      query: query.trim(),
      filters,
      sort,
      page: 1,
      page_size: 12,
      beta: hiddenGem,
    });
  };

  const visibleResults =
    response?.results.filter((movie) => !dismissed.includes(movie.id)) ?? [];
  const activeFilters = useMemo(() => activeFilterLabels(filters), [filters]);

  return (
    <div className="page-shell discovery-page">
      <section className="discovery-hero" aria-labelledby="discovery-title">
        <div className="hero-copy">
          <span className="eyebrow">
            <Icon name="sparkle" width={16} height={16} /> Multilingual Tamil
            film discovery
          </span>
          <h1 id="discovery-title">
            Describe the story.
            <br />
            <em>Find the film.</em>
          </h1>
          <p>
            Search by plot, feeling, theme, or half-remembered detail—in
            English, தமிழ், or Tanglish. Every result explains why it fits.
          </p>
        </div>

        <form
          className="search-stage"
          onSubmit={submit}
          aria-label="Movie discovery search"
        >
          <label htmlFor="discovery-query">What are you in the mood for?</label>
          <div className="search-input-row">
            <Icon name="search" width={23} height={23} />
            <textarea
              id="discovery-query"
              rows={2}
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              onKeyDown={(event) => {
                if (
                  event.key === "Enter" &&
                  !event.shiftKey &&
                  !event.nativeEvent.isComposing
                ) {
                  event.preventDefault();
                  submit();
                }
              }}
              placeholder="A restrained village drama about family and changing traditions…"
              maxLength={500}
              required
            />
            <button
              className="button button-primary search-submit"
              disabled={loading || !query.trim()}
              type="submit"
            >
              {loading ? (
                <span className="spinner" aria-hidden="true" />
              ) : (
                <Icon name="arrow" width={19} height={19} />
              )}
              <span>{loading ? "Searching" : "Discover"}</span>
            </button>
          </div>
          <div className="example-row" aria-label="Search examples">
            <span>Try:</span>
            {EXAMPLES.map((example) => (
              <button
                type="button"
                key={example.label}
                onClick={() => setQuery(example.query)}
              >
                <strong>{example.label}</strong> {example.query}
              </button>
            ))}
          </div>
          <div className="search-controls">
            <button
              className="button button-secondary"
              type="button"
              onClick={() => setFiltersOpen(true)}
            >
              <Icon name="sliders" width={17} height={17} /> Filters{" "}
              {activeFilters.length > 0 && (
                <span className="count-badge">{activeFilters.length}</span>
              )}
            </button>
            <label className="inline-range">
              <span>
                Hidden gems <output>{Math.round(hiddenGem * 100)}%</output>
              </span>
              <input
                aria-label="Hidden gem preference"
                type="range"
                min="0"
                max="1"
                step="0.05"
                value={hiddenGem}
                onChange={(event) => setHiddenGem(Number(event.target.value))}
              />
            </label>
            <label className="sort-control">
              <span>Sort</span>
              <select
                value={sort}
                onChange={(event) => setSort(event.target.value as SearchSort)}
              >
                <option value="relevance">Best match</option>
                <option value="hidden_gems">Hidden gems</option>
                <option value="release_year_desc">Newest</option>
                <option value="release_year_asc">Oldest</option>
                <option value="popularity">Most known</option>
              </select>
            </label>
          </div>
          {activeFilters.length > 0 && (
            <div className="active-filter-row" aria-label="Active filters">
              {activeFilters.map((filter) => (
                <button
                  type="button"
                  key={filter.key}
                  onClick={() =>
                    setFilters((current) => removeFilter(current, filter.key))
                  }
                >
                  {filter.label}
                  <Icon name="x" width={13} height={13} />
                </button>
              ))}
              <button
                type="button"
                className="clear-chip"
                onClick={() => setFilters(EMPTY_FILTERS)}
              >
                Clear all
              </button>
            </div>
          )}
        </form>
      </section>

      <div
        className="search-status visually-hidden"
        role="status"
        aria-live="polite"
        aria-atomic="true"
      >
        {loading
          ? "Searching the catalog"
          : error
            ? `Search failed: ${error}`
            : response
              ? `${visibleResults.length} results shown for ${response.query}`
              : "Ready to search"}
      </div>

      {loading && (
        <section
          className="results-section"
          aria-label="Loading search results"
        >
          <div className="results-heading">
            <div className="skeleton skeleton-line wide" />
            <div className="skeleton skeleton-line short" />
          </div>
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
        </section>
      )}

      {!loading && error && (
        <section className="state-panel error-panel" role="alert">
          <Icon name="retry" width={34} height={34} />
          <h2>We couldn’t search the catalog</h2>
          <p>{error}</p>
          <button
            className="button button-primary"
            type="button"
            onClick={() =>
              lastRequest.current && void runSearch(lastRequest.current)
            }
          >
            <Icon name="retry" width={17} height={17} /> Try again
          </button>
        </section>
      )}

      {!loading && response && visibleResults.length === 0 && (
        <section className="state-panel">
          <Icon name="search" width={36} height={36} />
          <h2>No close matches yet</h2>
          <p>
            Try removing a filter, using a broader story description, or
            searching for a genre and mood together.
          </p>
          <div className="state-actions">
            <button
              className="button button-secondary"
              type="button"
              onClick={() => setFilters(EMPTY_FILTERS)}
            >
              Clear filters
            </button>
            <button
              className="button button-primary"
              type="button"
              onClick={() =>
                setQuery("A moving Tamil drama with family, hope, and humor")
              }
            >
              Use an example
            </button>
          </div>
        </section>
      )}

      {!loading && response && visibleResults.length > 0 && (
        <section className="results-section" aria-labelledby="results-title">
          <div className="results-heading">
            <div>
              <span className="eyebrow">
                {response.detectedLanguage} query ·{" "}
                {response.source === "demo"
                  ? "on-device preview"
                  : response.meta.rankingVersion}
              </span>
              <h2 id="results-title">Matches for “{response.query}”</h2>
            </div>
            <p>
              {response.meta.total} matches ·{" "}
              {Math.round(response.meta.latencyMs)} ms
            </p>
          </div>
          {response.source === "demo" && (
            <div className="inline-notice" role="status">
              <Icon name="info" width={18} height={18} />
              <span>
                The live service is offline, so these results come from a small
                on-device catalog. Your search was not sent anywhere.
              </span>
            </div>
          )}
          <div className="movie-grid">
            {visibleResults.map((movie, index) => (
              <MovieCard key={movie.id} movie={movie} index={index} />
            ))}
          </div>
          {response.meta.totalPages > 1 && (
            <nav className="pagination" aria-label="Search result pages">
              <button
                className="button button-secondary"
                disabled={page <= 1}
                onClick={() =>
                  void runSearch({
                    ...(lastRequest.current ?? { query }),
                    page: page - 1,
                  })
                }
              >
                Previous
              </button>
              <span>
                Page {page} of {response.meta.totalPages}
              </span>
              <button
                className="button button-secondary"
                disabled={page >= response.meta.totalPages}
                onClick={() =>
                  void runSearch({
                    ...(lastRequest.current ?? { query }),
                    page: page + 1,
                  })
                }
              >
                Next
              </button>
            </nav>
          )}
        </section>
      )}

      {!loading && !response && !error && (
        <section className="intro-shelves">
          <article>
            <span className="shelf-number">01</span>
            <h2>Say it naturally</h2>
            <p>
              Plot fragments, feelings, themes, and Tamil or Tanglish phrases
              all work.
            </p>
          </article>
          <article>
            <span className="shelf-number">02</span>
            <h2>See the evidence</h2>
            <p>
              Matched metadata and ranking signals explain every recommendation.
            </p>
          </article>
          <article>
            <span className="shelf-number">03</span>
            <h2>Shape your trove</h2>
            <p>
              Save, rate, dismiss, and collect films to improve your personal
              feed.
            </p>
          </article>
        </section>
      )}

      <FilterDrawer
        open={filtersOpen}
        filters={filters}
        onChange={setFilters}
        onClose={() => setFiltersOpen(false)}
      />
    </div>
  );
}
