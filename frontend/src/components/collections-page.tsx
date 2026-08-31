"use client";

import Link from "next/link";
import { FormEvent, useRef, useState } from "react";
import type { CollectionVisibility } from "../types/api";
import { useApp } from "./app-provider";
import { Icon } from "./icons";
import { MoviePoster } from "./movie-poster";

export function CollectionsPage() {
  const { profile, collections, createCollection } = useApp();
  const dialog = useRef<HTMLDialogElement>(null);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [visibility, setVisibility] = useState<CollectionVisibility>("private");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await createCollection(name, description, visibility);
      setName("");
      setDescription("");
      setVisibility("private");
      dialog.current?.close();
    } catch (createError) {
      setError(
        createError instanceof Error
          ? createError.message
          : "Unable to create collection.",
      );
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="page-shell">
      <header className="page-hero split-hero">
        <div>
          <span className="eyebrow">
            <Icon name="collection" width={16} height={16} /> Curate and share
          </span>
          <h1>
            Stories belong <em>together.</em>
          </h1>
          <p>
            Make private watchlists, unlisted recommendations for friends, or
            public collections—without exposing personal activity.
          </p>
        </div>
        <button
          className="button button-primary"
          onClick={() => dialog.current?.showModal()}
        >
          <Icon name="plus" width={18} height={18} />
          New collection
        </button>
      </header>
      {!profile && (
        <div className="inline-notice">
          <Icon name="info" width={18} height={18} />
          <span>
            Collections are currently saved on this device.{" "}
            <Link href="/auth">Sign in</Link> to sync them across devices.
          </span>
        </div>
      )}
      {collections.length ? (
        <section aria-labelledby="collections-title">
          <div className="results-heading">
            <div>
              <span className="eyebrow">
                {collections.length} collection
                {collections.length === 1 ? "" : "s"}
              </span>
              <h2 id="collections-title">Your collections</h2>
            </div>
          </div>
          <div className="collection-grid">
            {collections.map((collection) => (
              <Link
                className="collection-card"
                href={`/collections/${encodeURIComponent(collection.id)}`}
                key={collection.id}
              >
                <div className="collection-mosaic">
                  {collection.items
                    .slice(0, 4)
                    .map(
                      (item) =>
                        item.movie && (
                          <MoviePoster key={item.movieId} movie={item.movie} />
                        ),
                    )}
                  {collection.items.length === 0 && (
                    <div className="empty-mosaic">
                      <Icon name="collection" width={32} height={32} />
                      <span>Add your first film</span>
                    </div>
                  )}
                </div>
                <div className="collection-card-copy">
                  <span
                    className={`visibility visibility-${collection.visibility}`}
                  >
                    {collection.visibility}
                  </span>
                  <h2>{collection.name}</h2>
                  <p>
                    {collection.description ||
                      "A new corner of your Tamil cinema trove."}
                  </p>
                  <small>
                    {collection.items.length} film
                    {collection.items.length === 1 ? "" : "s"} · Updated{" "}
                    {collection.updatedAt
                      ? new Date(collection.updatedAt).toLocaleDateString()
                      : "recently"}
                  </small>
                </div>
              </Link>
            ))}
          </div>
        </section>
      ) : (
        <section className="state-panel">
          <Icon name="collection" width={39} height={39} />
          <h2>Start your first collection</h2>
          <p>
            Group films for a mood, a filmmaker, a friend, or a future weekend.
          </p>
          <button
            className="button button-primary"
            onClick={() => dialog.current?.showModal()}
          >
            <Icon name="plus" width={17} height={17} />
            Create collection
          </button>
        </section>
      )}
      <section className="featured-collection">
        <div>
          <span className="eyebrow">Public editorial collection</span>
          <h2>Voices of change</h2>
          <p>
            Films that turn resistance, dignity, and difficult questions into
            unforgettable cinema.
          </p>
          <Link href="/collections/voices-of-change">
            Explore collection <Icon name="arrow" width={16} height={16} />
          </Link>
        </div>
      </section>

      <dialog
        ref={dialog}
        className="dialog"
        aria-labelledby="create-collection-title"
      >
        <form className="dialog-panel stack-form" onSubmit={submit}>
          <div className="dialog-header">
            <div>
              <span className="eyebrow">A new corner of your trove</span>
              <h2 id="create-collection-title">Create collection</h2>
            </div>
            <button
              type="button"
              className="icon-button"
              aria-label="Close dialog"
              onClick={() => dialog.current?.close()}
            >
              <Icon name="x" width={20} height={20} />
            </button>
          </div>
          <label>
            Name
            <input
              autoFocus
              value={name}
              onChange={(event) => setName(event.target.value)}
              required
              maxLength={80}
              placeholder="e.g. Rainy evening films"
            />
          </label>
          <label>
            Description
            <textarea
              rows={3}
              value={description}
              onChange={(event) => setDescription(event.target.value)}
              maxLength={500}
              placeholder="What connects these films?"
            />
          </label>
          <fieldset>
            <legend>Visibility</legend>
            <div className="visibility-options">
              {(
                ["private", "unlisted", "public"] as CollectionVisibility[]
              ).map((value) => (
                <label key={value}>
                  <input
                    type="radio"
                    name="visibility"
                    value={value}
                    checked={visibility === value}
                    onChange={() => setVisibility(value)}
                  />
                  <span>
                    <strong>{value}</strong>
                    <small>
                      {value === "private"
                        ? "Only you"
                        : value === "unlisted"
                          ? "Anyone with the link"
                          : "Visible to everyone"}
                    </small>
                  </span>
                </label>
              ))}
            </div>
          </fieldset>
          {error && (
            <div className="form-error" role="alert">
              {error}
            </div>
          )}
          <div className="dialog-actions">
            <button
              type="button"
              className="button button-secondary"
              onClick={() => dialog.current?.close()}
            >
              Cancel
            </button>
            <button
              className="button button-primary"
              disabled={!name.trim() || busy}
            >
              {busy ? "Creating" : "Create collection"}
            </button>
          </div>
        </form>
      </dialog>
    </div>
  );
}
