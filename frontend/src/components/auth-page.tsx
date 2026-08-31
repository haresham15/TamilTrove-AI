"use client";

import Link from "next/link";
import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import { useApp } from "./app-provider";
import { Icon } from "./icons";

export function AuthPage() {
  const { profile, signIn } = useApp();
  const router = useRouter();
  const [register, setRegister] = useState(false);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const next = await signIn({ email, password, displayName, register });
      router.push(next.onboardingComplete ? "/for-you" : "/onboarding");
    } catch (submitError) {
      setError(
        submitError instanceof Error
          ? submitError.message
          : "Unable to continue. Please try again.",
      );
    } finally {
      setBusy(false);
    }
  };

  if (profile)
    return (
      <div className="page-shell narrow-page">
        <section className="state-panel">
          <span className="avatar avatar-large" aria-hidden="true">
            {profile.displayName.slice(0, 1)}
          </span>
          <h1>You’re already signed in</h1>
          <p>Continue to your recommendations or manage your profile.</p>
          <div className="state-actions">
            <Link className="button button-secondary" href="/profile">
              Open profile
            </Link>
            <Link className="button button-primary" href="/for-you">
              Go to For You
            </Link>
          </div>
        </section>
      </div>
    );

  return (
    <div className="auth-layout">
      <section className="auth-story" aria-labelledby="auth-story-title">
        <div>
          <span className="eyebrow">Your cinema, remembered carefully</span>
          <h1 id="auth-story-title">
            Build a trove that <em>learns from you.</em>
          </h1>
          <p>
            Save films, make collections, and improve recommendations with
            feedback you control.
          </p>
        </div>
        <ul>
          <li>
            <Icon name="shield" width={19} height={19} />
            <span>
              <strong>Private by default.</strong> Collections begin private and
              recommendation data can be reset.
            </span>
          </li>
          <li>
            <Icon name="sparkle" width={19} height={19} />
            <span>
              <strong>Explainable.</strong> Every recommendation shows grounded
              evidence.
            </span>
          </li>
          <li>
            <Icon name="download" width={19} height={19} />
            <span>
              <strong>Portable.</strong> Export or delete your account data at
              any time.
            </span>
          </li>
        </ul>
      </section>
      <section className="auth-card" aria-labelledby="auth-title">
        <div className="auth-tabs" role="tablist" aria-label="Account action">
          <button
            role="tab"
            aria-selected={!register}
            onClick={() => {
              setRegister(false);
              setError(null);
            }}
          >
            Sign in
          </button>
          <button
            role="tab"
            aria-selected={register}
            onClick={() => {
              setRegister(true);
              setError(null);
            }}
          >
            Create account
          </button>
        </div>
        <span className="eyebrow">
          {register ? "Start your personal trove" : "Welcome back"}
        </span>
        <h2 id="auth-title">
          {register ? "Create your account" : "Sign in to TamilTrove"}
        </h2>
        <form onSubmit={submit} className="stack-form">
          {register && (
            <label>
              Display name
              <input
                autoComplete="name"
                value={displayName}
                onChange={(event) => setDisplayName(event.target.value)}
                minLength={2}
                maxLength={80}
                required
                placeholder="How should we greet you?"
              />
            </label>
          )}
          <label>
            Email address
            <input
              type="email"
              inputMode="email"
              autoComplete="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              required
              placeholder="you@example.com"
            />
          </label>
          <label>
            Password
            <input
              type="password"
              autoComplete={register ? "new-password" : "current-password"}
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              minLength={8}
              maxLength={128}
              required
            />
            <small>
              At least 8 characters. Passwords are never stored in the browser.
            </small>
          </label>
          {error && (
            <div className="form-error" role="alert">
              <Icon name="info" width={17} height={17} />
              {error}
            </div>
          )}
          <button
            className="button button-primary button-wide"
            disabled={busy}
            type="submit"
          >
            {busy ? (
              <span className="spinner" aria-hidden="true" />
            ) : (
              <Icon name="arrow" width={18} height={18} />
            )}
            {busy ? "Please wait" : register ? "Create account" : "Sign in"}
          </button>
        </form>
        <p className="auth-footnote">
          If the API is unavailable, TamilTrove switches to a clearly labeled
          on-device demo. Nothing is silently uploaded.
        </p>
      </section>
    </div>
  );
}
