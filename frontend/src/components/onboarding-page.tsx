"use client";

import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";
import { DEFAULT_PREFERENCES, useApp } from "./app-provider";
import { DEMO_MOVIES, GENRE_OPTIONS, THEME_OPTIONS } from "../lib/demo-data";
import type { UserPreferences } from "../types/api";
import { Icon } from "./icons";
import { MoviePoster } from "./movie-poster";

export function OnboardingPage() {
  const { profile, saveProfile } = useApp();
  const router = useRouter();
  const [step, setStep] = useState(1);
  const [preferences, setPreferences] = useState<UserPreferences>(
    profile?.preferences ?? DEFAULT_PREFERENCES,
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const progress = (step / 3) * 100;

  const toggle = (
    field: "favoriteGenres" | "favoriteThemes" | "onboardingMovieIds",
    value: string,
  ) =>
    setPreferences((current) => ({
      ...current,
      [field]: current[field].includes(value)
        ? current[field].filter((item) => item !== value)
        : [...current[field], value],
    }));
  const valid = useMemo(
    () =>
      step === 1
        ? preferences.favoriteGenres.length > 0
        : step === 2
          ? preferences.favoriteThemes.length > 0
          : preferences.onboardingMovieIds.length >= 2,
    [preferences, step],
  );

  const finish = async () => {
    setBusy(true);
    setError(null);
    try {
      await saveProfile({ onboardingComplete: true, preferences });
      router.push("/for-you");
    } catch (saveError) {
      setError(
        saveError instanceof Error
          ? saveError.message
          : "Unable to save preferences.",
      );
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="page-shell onboarding-page">
      <header className="onboarding-header">
        <div>
          <span className="eyebrow">Taste setup · step {step} of 3</span>
          <h1>Make your recommendations feel personal.</h1>
          <p>
            Choose only what matters. You can change or reset every signal
            later.
          </p>
        </div>
        <div
          className="progress-ring"
          style={
            { "--progress": `${progress * 3.6}deg` } as React.CSSProperties
          }
        >
          <span>{step}/3</span>
        </div>
      </header>
      <div
        className="progress-track"
        aria-label={`Step ${step} of 3`}
        role="progressbar"
        aria-valuemin={1}
        aria-valuemax={3}
        aria-valuenow={step}
      >
        <span style={{ width: `${progress}%` }} />
      </div>

      {step === 1 && (
        <section className="onboarding-panel" aria-labelledby="genres-title">
          <span className="eyebrow">Start broad</span>
          <h2 id="genres-title">Which genres pull you in?</h2>
          <p>
            Select one or more. This boosts matching films; it never hides
            everything else.
          </p>
          <div className="choice-cloud">
            {GENRE_OPTIONS.map((genre) => (
              <button
                type="button"
                className={
                  preferences.favoriteGenres.includes(genre)
                    ? "is-selected"
                    : ""
                }
                aria-pressed={preferences.favoriteGenres.includes(genre)}
                key={genre}
                onClick={() => toggle("favoriteGenres", genre)}
              >
                {preferences.favoriteGenres.includes(genre) && (
                  <Icon name="check" width={15} height={15} />
                )}
                {genre}
              </button>
            ))}
          </div>
        </section>
      )}
      {step === 2 && (
        <section className="onboarding-panel" aria-labelledby="themes-title">
          <span className="eyebrow">Go deeper</span>
          <h2 id="themes-title">What kinds of stories stay with you?</h2>
          <p>
            Themes make natural-language recommendations more specific and
            explainable.
          </p>
          <div className="choice-cloud">
            {THEME_OPTIONS.map((theme) => (
              <button
                type="button"
                className={
                  preferences.favoriteThemes.includes(theme)
                    ? "is-selected"
                    : ""
                }
                aria-pressed={preferences.favoriteThemes.includes(theme)}
                key={theme}
                onClick={() => toggle("favoriteThemes", theme)}
              >
                {preferences.favoriteThemes.includes(theme) && (
                  <Icon name="check" width={15} height={15} />
                )}
                {theme}
              </button>
            ))}
          </div>
          <div className="preference-sliders">
            <label>
              <span>
                Preferred release range{" "}
                <output>
                  {preferences.eraFrom}–{preferences.eraTo}
                </output>
              </span>
              <div className="dual-fields">
                <input
                  aria-label="Earliest preferred year"
                  type="number"
                  min="1931"
                  max={preferences.eraTo}
                  value={preferences.eraFrom}
                  onChange={(event) =>
                    setPreferences((current) => ({
                      ...current,
                      eraFrom: Number(event.target.value),
                    }))
                  }
                />
                <input
                  aria-label="Latest preferred year"
                  type="number"
                  min={preferences.eraFrom}
                  max="2030"
                  value={preferences.eraTo}
                  onChange={(event) =>
                    setPreferences((current) => ({
                      ...current,
                      eraTo: Number(event.target.value),
                    }))
                  }
                />
              </div>
            </label>
            <label>
              <span>
                Hidden-gem appetite{" "}
                <output>
                  {Math.round(preferences.hiddenGemPreference * 100)}%
                </output>
              </span>
              <input
                type="range"
                min="0"
                max="1"
                step="0.05"
                value={preferences.hiddenGemPreference}
                onChange={(event) =>
                  setPreferences((current) => ({
                    ...current,
                    hiddenGemPreference: Number(event.target.value),
                  }))
                }
              />
            </label>
          </div>
        </section>
      )}
      {step === 3 && (
        <section className="onboarding-panel" aria-labelledby="films-title">
          <span className="eyebrow">Add a few anchors</span>
          <h2 id="films-title">Pick at least two films you enjoy</h2>
          <p>
            These explicit choices create the first content-based taste profile.
            They are not shown publicly.
          </p>
          <div className="onboarding-movies">
            {DEMO_MOVIES.slice(0, 8).map((movie) => {
              const selected = preferences.onboardingMovieIds.includes(
                movie.id,
              );
              return (
                <button
                  type="button"
                  key={movie.id}
                  className={selected ? "is-selected" : ""}
                  aria-pressed={selected}
                  onClick={() => toggle("onboardingMovieIds", movie.id)}
                >
                  <MoviePoster movie={movie} />
                  <span>
                    <strong>{movie.title}</strong>
                    <small>{movie.genres.slice(0, 2).join(" · ")}</small>
                  </span>
                  <span className="selection-check">
                    <Icon
                      name={selected ? "check" : "plus"}
                      width={16}
                      height={16}
                    />
                  </span>
                </button>
              );
            })}
          </div>
          <label className="consent-box">
            <input
              type="checkbox"
              checked={preferences.analyticsConsent}
              onChange={(event) =>
                setPreferences((current) => ({
                  ...current,
                  analyticsConsent: event.target.checked,
                }))
              }
            />
            <span>
              <strong>Share anonymous product analytics (optional)</strong>
              <small>
                Helps measure reliability and feature use. Search text,
                credentials, and private collections are excluded.
              </small>
            </span>
          </label>
        </section>
      )}
      {error && (
        <div className="form-error" role="alert">
          {error}
        </div>
      )}
      <footer className="onboarding-footer">
        <button
          className="button button-secondary"
          type="button"
          disabled={step === 1 || busy}
          onClick={() => setStep((current) => current - 1)}
        >
          Back
        </button>
        <span>
          {step === 3
            ? `${preferences.onboardingMovieIds.length} films selected`
            : valid
              ? "Ready to continue"
              : "Choose at least one"}
        </span>
        {step < 3 ? (
          <button
            className="button button-primary"
            type="button"
            disabled={!valid}
            onClick={() => setStep((current) => current + 1)}
          >
            Continue <Icon name="arrow" width={17} height={17} />
          </button>
        ) : (
          <button
            className="button button-primary"
            type="button"
            disabled={!valid || busy}
            onClick={() => void finish()}
          >
            {busy ? "Saving" : "Build my shelf"}{" "}
            <Icon name="sparkle" width={17} height={17} />
          </button>
        )}
      </footer>
    </div>
  );
}
