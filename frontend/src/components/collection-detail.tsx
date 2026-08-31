"use client";

import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";
import { apiClient, isNetworkError } from "../lib/api-client";
import { DEMO_SHARED_COLLECTION } from "../lib/demo-data";
import type { MovieCollection } from "../types/api";
import { useApp } from "./app-provider";
import { Icon } from "./icons";
import { MoviePoster } from "./movie-poster";

export function CollectionDetail({ id }: { id: string }) {
  const {
    collections,
    updateCollection,
    deleteCollection,
    removeFromCollection,
    shareCollection,
    notify,
  } = useApp();
  const local = useMemo(
    () => collections.find((item) => item.id === id),
    [collections, id],
  );
  const [remote, setRemote] = useState<MovieCollection | null>(
    id === DEMO_SHARED_COLLECTION.shareToken || id === DEMO_SHARED_COLLECTION.id
      ? DEMO_SHARED_COLLECTION
      : null,
  );
  const [loading, setLoading] = useState(!local && !remote);
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState(false);
  const deleteDialog = useRef<HTMLDialogElement>(null);
  const collection = local ?? remote;
  const owned = Boolean(local);

  useEffect(() => {
    if (local || remote) return;
    const controller = new AbortController();
    apiClient
      .sharedCollection(id, controller.signal)
      .then(setRemote)
      .catch((loadError) => {
        if (!isNetworkError(loadError))
          setError(
            loadError instanceof Error
              ? loadError.message
              : "Collection not found.",
          );
        else
          setError("This shared collection could not be loaded while offline.");
      })
      .finally(() => setLoading(false));
    return () => controller.abort();
  }, [id, local, remote]);

  const copyShare = async () => {
    if (!collection) return;
    const shared = owned ? await shareCollection(collection.id) : collection;
    const url = `${window.location.origin}/collections/${shared.shareToken ?? shared.id}`;
    await navigator.clipboard.writeText(url);
    notify("Share link copied.", "success");
  };

  if (loading)
    return (
      <div className="page-shell">
        <div className="state-panel">
          <span className="spinner dark" />
          <h1>Loading collection</h1>
        </div>
      </div>
    );
  if (!collection || error)
    return (
      <div className="page-shell">
        <section className="state-panel error-panel" role="alert">
          <Icon name="collection" width={38} height={38} />
          <h1>Collection unavailable</h1>
          <p>{error ?? "This collection does not exist or is private."}</p>
          <Link href="/collections" className="button button-primary">
            Back to collections
          </Link>
        </section>
      </div>
    );

  return (
    <div className="page-shell collection-detail-page">
      <nav className="breadcrumbs" aria-label="Breadcrumb">
        <Link href="/collections">Collections</Link>
        <Icon name="chevron" width={14} height={14} />
        <span aria-current="page">{collection.name}</span>
      </nav>
      <header className="collection-detail-header">
        <div>
          <span className={`visibility visibility-${collection.visibility}`}>
            {collection.visibility}
          </span>
          {editing ? (
            <EditCollection
              collection={collection}
              onSave={async (changes) => {
                await updateCollection(collection.id, changes);
                setEditing(false);
              }}
              onCancel={() => setEditing(false)}
            />
          ) : (
            <>
              <h1>{collection.name}</h1>
              <p>{collection.description || "A TamilTrove film collection."}</p>
              <small>
                Curated by{" "}
                {collection.ownerDisplayName ??
                  (owned ? "you" : "TamilTrove member")}{" "}
                · {collection.items.length} films
              </small>
            </>
          )}
        </div>
        <div className="collection-header-actions">
          {collection.visibility !== "private" && (
            <button
              className="button button-primary"
              onClick={() => void copyShare()}
            >
              <Icon name="collection" width={17} height={17} />
              Copy share link
            </button>
          )}
          {owned && (
            <>
              <button
                className="button button-secondary"
                onClick={() => setEditing((value) => !value)}
              >
                Edit
              </button>
              <button
                className="icon-button danger-text"
                aria-label="Delete collection"
                onClick={() => deleteDialog.current?.showModal()}
              >
                <Icon name="trash" width={19} height={19} />
              </button>
            </>
          )}
        </div>
      </header>
      {collection.items.length ? (
        <ol className="collection-film-list">
          {collection.items
            .sort((a, b) => a.position - b.position)
            .map((item, index) => {
              const movie = item.movie;
              return (
                <li key={item.movieId}>
                  <span className="collection-index">
                    {String(index + 1).padStart(2, "0")}
                  </span>
                  {movie ? (
                    <>
                      <Link
                        className="collection-list-poster"
                        href={`/movies/${encodeURIComponent(movie.id)}`}
                      >
                        <MoviePoster movie={movie} />
                      </Link>
                      <div className="collection-list-copy">
                        <span className="eyebrow">
                          {movie.releaseYear ?? "Tamil cinema"} ·{" "}
                          {movie.genres.slice(0, 2).join(" / ")}
                        </span>
                        <h2>
                          <Link
                            href={`/movies/${encodeURIComponent(movie.id)}`}
                          >
                            {movie.title}
                          </Link>
                        </h2>
                        <p>{movie.overview}</p>
                      </div>
                    </>
                  ) : (
                    <div className="collection-list-copy">
                      <h2>
                        <Link
                          href={`/movies/${encodeURIComponent(item.movieId)}`}
                        >
                          Catalog film
                        </Link>
                      </h2>
                      <p>
                        Open this film to load its current catalog metadata.
                      </p>
                    </div>
                  )}
                  {owned && (
                    <button
                      className="icon-button danger-text"
                      aria-label={`Remove ${movie?.title ?? "film"} from collection`}
                      onClick={() =>
                        void removeFromCollection(collection.id, item.movieId)
                      }
                    >
                      <Icon name="x" width={18} height={18} />
                    </button>
                  )}
                </li>
              );
            })}
        </ol>
      ) : (
        <section className="state-panel">
          <Icon name="film" width={37} height={37} />
          <h2>This collection is empty</h2>
          <p>Add a film from any result card using the Collect action.</p>
          <Link href="/" className="button button-primary">
            Discover films
          </Link>
        </section>
      )}
      <dialog
        ref={deleteDialog}
        className="dialog"
        aria-labelledby="delete-collection-title"
      >
        <div className="dialog-panel">
          <h2 id="delete-collection-title">Delete “{collection.name}”?</h2>
          <p>
            The collection will be removed. The movies and your other activity
            are unaffected.
          </p>
          <div className="dialog-actions">
            <button
              className="button button-secondary"
              onClick={() => deleteDialog.current?.close()}
            >
              Cancel
            </button>
            <button
              className="button button-danger"
              onClick={() => void deleteCollection(collection.id)}
            >
              Delete collection
            </button>
          </div>
        </div>
      </dialog>
    </div>
  );
}

function EditCollection({
  collection,
  onSave,
  onCancel,
}: {
  collection: MovieCollection;
  onSave: (
    changes: Partial<
      Pick<MovieCollection, "name" | "description" | "visibility">
    >,
  ) => Promise<void>;
  onCancel: () => void;
}) {
  const [name, setName] = useState(collection.name);
  const [description, setDescription] = useState(collection.description);
  const [visibility, setVisibility] = useState(collection.visibility);
  const [busy, setBusy] = useState(false);
  return (
    <form
      className="inline-edit"
      onSubmit={async (event) => {
        event.preventDefault();
        setBusy(true);
        try {
          await onSave({ name, description, visibility });
        } finally {
          setBusy(false);
        }
      }}
    >
      <label>
        Name
        <input
          value={name}
          onChange={(event) => setName(event.target.value)}
          required
          maxLength={80}
        />
      </label>
      <label>
        Description
        <textarea
          value={description}
          onChange={(event) => setDescription(event.target.value)}
          rows={2}
          maxLength={500}
        />
      </label>
      <label>
        Visibility
        <select
          value={visibility}
          onChange={(event) =>
            setVisibility(event.target.value as MovieCollection["visibility"])
          }
        >
          <option value="private">Private</option>
          <option value="unlisted">Unlisted</option>
          <option value="public">Public</option>
        </select>
      </label>
      <div className="state-actions">
        <button
          type="button"
          className="button button-secondary"
          onClick={onCancel}
        >
          Cancel
        </button>
        <button className="button button-primary" disabled={busy}>
          {busy ? "Saving" : "Save"}
        </button>
      </div>
    </form>
  );
}
