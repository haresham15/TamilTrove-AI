"use client";

import Link from "next/link";
import { FormEvent, useRef, useState } from "react";
import { apiClient } from "../lib/api-client";
import { DEMO_MOVIES, GENRE_OPTIONS, THEME_OPTIONS } from "../lib/demo-data";
import type { Movie, UserProfile } from "../types/api";
import { useApp } from "./app-provider";
import { Icon } from "./icons";
import { MoviePoster } from "./movie-poster";

function movieFor(id: string): Movie {
  return (
    DEMO_MOVIES.find((movie) => movie.id === id) ?? {
      id,
      title: "Catalog film",
      overview: "Open the live catalog for full details.",
      language: "Tamil",
      genres: [],
      themes: [],
      cast: [],
      prominenceScore: 0.5,
    }
  );
}

export function ProfilePage() {
  const app = useApp();
  const {
    profile,
    watchlist,
    liked,
    dismissed,
    ratings,
    history,
    collections,
    saveProfile,
    restoreDismissed,
    clearSearchHistory,
    resetTasteProfile,
    deleteAccount,
    signOut,
    token,
    sessionMode,
  } = app;
  const [draft, setDraft] = useState<UserProfile | null>(profile);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const deleteDialog = useRef<HTMLDialogElement>(null);

  if (!profile || !draft)
    return (
      <div className="page-shell narrow-page">
        <section className="state-panel">
          <Icon name="user" width={38} height={38} />
          <h1>Your trove is waiting</h1>
          <p>
            Sign in to sync your watchlist and collections. You can also
            continue in the on-device demo.
          </p>
          <div className="state-actions">
            <Link className="button button-primary" href="/auth">
              Sign in
            </Link>
            <Link className="button button-secondary" href="/onboarding">
              Try taste setup
            </Link>
          </div>
        </section>
      </div>
    );

  const save = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      setDraft(
        await saveProfile({
          displayName: draft.displayName,
          locale: draft.locale,
          preferences: draft.preferences,
          privacy: draft.privacy,
        }),
      );
    } catch (saveError) {
      setError(
        saveError instanceof Error
          ? saveError.message
          : "Unable to save profile.",
      );
    } finally {
      setBusy(false);
    }
  };
  const togglePreference = (
    field: "favoriteGenres" | "favoriteThemes",
    value: string,
  ) =>
    setDraft((current) =>
      current
        ? {
            ...current,
            preferences: {
              ...current.preferences,
              [field]: current.preferences[field].includes(value)
                ? current.preferences[field].filter((item) => item !== value)
                : [...current.preferences[field], value],
            },
          }
        : current,
    );
  const exportData = async () => {
    const payload =
      sessionMode === "api"
        ? await apiClient.exportProfile(token)
        : {
            profile,
            watchlist,
            liked,
            dismissed,
            ratings,
            history,
            collections,
            exportedAt: new Date().toISOString(),
          };
    const blob = new Blob([JSON.stringify(payload, null, 2)], {
      type: "application/json",
    });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = "tamiltrove-export.json";
    anchor.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="page-shell profile-page">
      <header className="profile-header">
        <div className="avatar avatar-xl" aria-hidden="true">
          {profile.displayName.slice(0, 1).toUpperCase()}
        </div>
        <div>
          <span className="eyebrow">
            My Trove ·{" "}
            {sessionMode === "api" ? "synced account" : "on-device demo"}
          </span>
          <h1>{profile.displayName}</h1>
          <p>{profile.email}</p>
        </div>
        <button
          className="button button-secondary"
          onClick={() => void signOut()}
        >
          Sign out
        </button>
      </header>
      <nav className="section-nav" aria-label="Profile sections">
        <a href="#watchlist">
          Watchlist <span>{watchlist.length}</span>
        </a>
        <a href="#taste">Taste profile</a>
        <a href="#activity">Activity</a>
        <a href="#privacy">Privacy & data</a>
      </nav>

      <section id="watchlist" className="profile-section">
        <div className="section-heading">
          <div>
            <span className="eyebrow">Saved for later</span>
            <h2>Watchlist</h2>
          </div>
          <Link href="/">
            Discover films <Icon name="arrow" width={15} height={15} />
          </Link>
        </div>
        {watchlist.length ? (
          <div className="poster-rail">
            {watchlist.map((id) => {
              const movie = movieFor(id);
              return (
                <Link href={`/movies/${encodeURIComponent(id)}`} key={id}>
                  <MoviePoster movie={movie} />
                  <strong>{movie.title}</strong>
                  <small>{movie.releaseYear ?? "Tamil cinema"}</small>
                </Link>
              );
            })}
          </div>
        ) : (
          <div className="inline-empty">
            <Icon name="bookmark" width={27} height={27} />
            <div>
              <strong>Your watchlist is empty</strong>
              <p>Save a film from any result or detail page.</p>
            </div>
          </div>
        )}
      </section>

      <form id="taste" className="profile-section" onSubmit={save}>
        <div className="section-heading">
          <div>
            <span className="eyebrow">Explicit preferences</span>
            <h2>Taste profile</h2>
          </div>
          <button className="button button-primary" disabled={busy}>
            {busy ? "Saving" : "Save preferences"}
          </button>
        </div>
        <div className="profile-form-grid">
          <label>
            Display name
            <input
              value={draft.displayName}
              minLength={2}
              maxLength={80}
              onChange={(event) =>
                setDraft({ ...draft, displayName: event.target.value })
              }
            />
          </label>
          <label>
            Interface locale
            <select
              value={draft.locale}
              onChange={(event) =>
                setDraft({ ...draft, locale: event.target.value })
              }
            >
              <option value="en-IN">English (India)</option>
              <option value="ta-IN">தமிழ் (India)</option>
            </select>
          </label>
          <fieldset className="field-wide">
            <legend>Favorite genres</legend>
            <div className="choice-cloud small">
              {GENRE_OPTIONS.map((genre) => (
                <button
                  type="button"
                  key={genre}
                  aria-pressed={draft.preferences.favoriteGenres.includes(
                    genre,
                  )}
                  className={
                    draft.preferences.favoriteGenres.includes(genre)
                      ? "is-selected"
                      : ""
                  }
                  onClick={() => togglePreference("favoriteGenres", genre)}
                >
                  {genre}
                </button>
              ))}
            </div>
          </fieldset>
          <fieldset className="field-wide">
            <legend>Favorite themes</legend>
            <div className="choice-cloud small">
              {THEME_OPTIONS.map((theme) => (
                <button
                  type="button"
                  key={theme}
                  aria-pressed={draft.preferences.favoriteThemes.includes(
                    theme,
                  )}
                  className={
                    draft.preferences.favoriteThemes.includes(theme)
                      ? "is-selected"
                      : ""
                  }
                  onClick={() => togglePreference("favoriteThemes", theme)}
                >
                  {theme}
                </button>
              ))}
            </div>
          </fieldset>
          <label className="field-wide">
            <span>
              Hidden-gem preference{" "}
              <output>
                {Math.round(draft.preferences.hiddenGemPreference * 100)}%
              </output>
            </span>
            <input
              type="range"
              min="0"
              max="1"
              step="0.05"
              value={draft.preferences.hiddenGemPreference}
              onChange={(event) =>
                setDraft({
                  ...draft,
                  preferences: {
                    ...draft.preferences,
                    hiddenGemPreference: Number(event.target.value),
                  },
                })
              }
            />
          </label>
        </div>
        {error && (
          <div className="form-error" role="alert">
            {error}
          </div>
        )}
      </form>

      <section id="activity" className="profile-section">
        <div className="section-heading">
          <div>
            <span className="eyebrow">Private feedback</span>
            <h2>Activity & history</h2>
          </div>
        </div>
        <div className="stats-grid">
          <div>
            <strong>{liked.length}</strong>
            <span>liked</span>
          </div>
          <div>
            <strong>{Object.keys(ratings).length}</strong>
            <span>rated</span>
          </div>
          <div>
            <strong>{collections.length}</strong>
            <span>collections</span>
          </div>
          <div>
            <strong>{history.length}</strong>
            <span>searches saved</span>
          </div>
        </div>
        <div className="activity-columns">
          <div>
            <h3>Recent searches</h3>
            {history.length ? (
              <ul className="history-list">
                {history.slice(0, 8).map((item) => (
                  <li key={item.id}>
                    <Link href={`/?q=${encodeURIComponent(item.query)}`}>
                      {item.query}
                    </Link>
                    <span>
                      {item.detectedLanguage} · {item.resultCount} results
                    </span>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="muted-copy">No saved searches.</p>
            )}
            <button
              className="text-button danger-text"
              disabled={!history.length}
              onClick={() => void clearSearchHistory()}
            >
              Clear search history
            </button>
          </div>
          <div id="dismissed">
            <h3>Dismissed films</h3>
            {dismissed.length ? (
              <ul className="dismissed-list">
                {dismissed.map((id) => (
                  <li key={id}>
                    <span>{movieFor(id).title}</span>
                    <button onClick={() => restoreDismissed(id)}>
                      Restore
                    </button>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="muted-copy">No dismissed films.</p>
            )}
          </div>
        </div>
      </section>

      <section id="privacy" className="profile-section">
        <div className="section-heading">
          <div>
            <span className="eyebrow">You stay in control</span>
            <h2>Privacy & data</h2>
          </div>
        </div>
        <div className="privacy-grid">
          <div className="toggle-list">
            <label className="switch-row">
              <span>
                <strong>Save search history</strong>
                <small>Stored privately to help you revisit discoveries.</small>
              </span>
              <input
                type="checkbox"
                checked={draft.privacy.saveSearchHistory}
                onChange={(event) =>
                  setDraft({
                    ...draft,
                    privacy: {
                      ...draft.privacy,
                      saveSearchHistory: event.target.checked,
                    },
                  })
                }
              />
            </label>
            <label className="switch-row">
              <span>
                <strong>Personalized recommendations</strong>
                <small>Use likes, ratings, views, and dismissals.</small>
              </span>
              <input
                type="checkbox"
                checked={draft.privacy.personalizeRecommendations}
                onChange={(event) =>
                  setDraft({
                    ...draft,
                    privacy: {
                      ...draft.privacy,
                      personalizeRecommendations: event.target.checked,
                    },
                  })
                }
              />
            </label>
            <label className="switch-row">
              <span>
                <strong>Anonymous analytics</strong>
                <small>
                  Never includes credentials or private collection contents.
                </small>
              </span>
              <input
                type="checkbox"
                checked={draft.preferences.analyticsConsent}
                onChange={(event) =>
                  setDraft({
                    ...draft,
                    preferences: {
                      ...draft.preferences,
                      analyticsConsent: event.target.checked,
                    },
                  })
                }
              />
            </label>
            <button
              className="button button-secondary"
              onClick={(event) => {
                event.preventDefault();
                void save(event as unknown as FormEvent);
              }}
            >
              Save privacy settings
            </button>
          </div>
          <div className="data-actions">
            <button className="data-action" onClick={() => void exportData()}>
              <Icon name="download" width={21} height={21} />
              <span>
                <strong>Export my data</strong>
                <small>
                  Download a JSON copy of your profile and activity.
                </small>
              </span>
              <Icon name="chevron" width={17} height={17} />
            </button>
            <button
              className="data-action"
              onClick={() => void resetTasteProfile()}
            >
              <Icon name="retry" width={21} height={21} />
              <span>
                <strong>Reset recommendation profile</strong>
                <small>Keeps your watchlist and collections.</small>
              </span>
              <Icon name="chevron" width={17} height={17} />
            </button>
            <button
              className="data-action danger-text"
              onClick={() => deleteDialog.current?.showModal()}
            >
              <Icon name="trash" width={21} height={21} />
              <span>
                <strong>Delete account and data</strong>
                <small>This cannot be undone after confirmation.</small>
              </span>
              <Icon name="chevron" width={17} height={17} />
            </button>
          </div>
        </div>
      </section>

      <dialog
        ref={deleteDialog}
        className="dialog"
        aria-labelledby="delete-title"
      >
        <div className="dialog-panel">
          <div className="dialog-header">
            <div>
              <span className="eyebrow">Permanent action</span>
              <h2 id="delete-title">Delete your TamilTrove account?</h2>
            </div>
            <button
              className="icon-button"
              aria-label="Close dialog"
              onClick={() => deleteDialog.current?.close()}
            >
              <Icon name="x" width={20} height={20} />
            </button>
          </div>
          <p>
            This removes your profile, interactions, search history, and
            collections. Export first if you want a copy.
          </p>
          <div className="dialog-actions">
            <button
              className="button button-secondary"
              onClick={() => deleteDialog.current?.close()}
            >
              Keep my account
            </button>
            <button
              className="button button-danger"
              onClick={async () => {
                await deleteAccount();
                deleteDialog.current?.close();
              }}
            >
              Delete permanently
            </button>
          </div>
        </div>
      </dialog>
    </div>
  );
}
