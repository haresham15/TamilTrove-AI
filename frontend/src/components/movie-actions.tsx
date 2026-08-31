"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useApp } from "./app-provider";
import { Icon } from "./icons";
import type { Movie } from "../types/api";

function CollectionDialog({
  movie,
  open,
  onClose,
}: {
  movie: Movie;
  open: boolean;
  onClose: () => void;
}) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const { collections, addToCollection, createCollection } = useApp();
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;
    if (open && !dialog.open) dialog.showModal();
    if (!open && dialog.open) dialog.close();
  }, [open]);

  const createAndAdd = async () => {
    if (!name.trim()) return;
    setBusy(true);
    try {
      const collection = await createCollection(name, "", "private");
      await addToCollection(collection.id, movie);
      setName("");
      onClose();
    } finally {
      setBusy(false);
    }
  };

  return (
    <dialog
      ref={dialogRef}
      className="dialog"
      aria-labelledby="collection-dialog-title"
      onClose={onClose}
      onCancel={onClose}
      onClick={(event) => {
        if (event.target === event.currentTarget) event.currentTarget.close();
      }}
    >
      <div className="dialog-panel">
        <div className="dialog-header">
          <div>
            <span className="eyebrow">Organize your trove</span>
            <h2 id="collection-dialog-title">Add {movie.title}</h2>
          </div>
          <button
            className="icon-button"
            type="button"
            onClick={() => dialogRef.current?.close()}
            aria-label="Close dialog"
          >
            <Icon name="x" width={20} height={20} />
          </button>
        </div>

        {collections.length > 0 ? (
          <div className="collection-choice-list">
            {collections.map((collection) => {
              const added = collection.items.some(
                (item) => item.movieId === movie.id,
              );
              return (
                <button
                  type="button"
                  key={collection.id}
                  disabled={added || busy}
                  onClick={async () => {
                    setBusy(true);
                    try {
                      await addToCollection(collection.id, movie);
                      dialogRef.current?.close();
                    } finally {
                      setBusy(false);
                    }
                  }}
                >
                  <span className="collection-choice-icon">
                    <Icon name="collection" width={18} height={18} />
                  </span>
                  <span>
                    <strong>{collection.name}</strong>
                    <small>
                      {collection.items.length} films · {collection.visibility}
                    </small>
                  </span>
                  {added ? (
                    <span className="added-label">
                      <Icon name="check" width={14} height={14} /> Added
                    </span>
                  ) : (
                    <Icon name="plus" width={18} height={18} />
                  )}
                </button>
              );
            })}
          </div>
        ) : (
          <div className="dialog-empty">
            <Icon name="collection" width={30} height={30} />
            <p>
              Create your first collection, then keep adding films from anywhere
              in TamilTrove.
            </p>
          </div>
        )}

        <div className="quick-create">
          <label htmlFor={`new-collection-${movie.id}`}>
            New private collection
          </label>
          <div className="input-action-row">
            <input
              id={`new-collection-${movie.id}`}
              value={name}
              onChange={(event) => setName(event.target.value)}
              placeholder="e.g. Friday night"
              maxLength={80}
            />
            <button
              className="button button-primary"
              type="button"
              disabled={!name.trim() || busy}
              onClick={createAndAdd}
            >
              Create & add
            </button>
          </div>
        </div>
      </div>
    </dialog>
  );
}

export function MovieActions({
  movie,
  allowDismiss = true,
  compact = false,
}: {
  movie: Movie;
  allowDismiss?: boolean;
  compact?: boolean;
}) {
  const {
    watchlist,
    liked,
    ratings,
    toggleWatchlist,
    toggleLike,
    rateMovie,
    dismissMovie,
  } = useApp();
  const [collectionOpen, setCollectionOpen] = useState(false);
  const saved = watchlist.includes(movie.id);
  const isLiked = liked.includes(movie.id);
  const rating = ratings[movie.id] ?? 0;

  return (
    <div className={`movie-actions${compact ? " compact" : ""}`}>
      <button
        type="button"
        className={`action-button${saved ? " is-active" : ""}`}
        aria-pressed={saved}
        onClick={() => toggleWatchlist(movie)}
        title={saved ? "Remove from watchlist" : "Save to watchlist"}
      >
        <Icon name={saved ? "check" : "bookmark"} width={17} height={17} />
        {!compact && <span>{saved ? "Saved" : "Watchlist"}</span>}
      </button>
      <button
        type="button"
        className={`action-button${isLiked ? " is-active is-liked" : ""}`}
        aria-pressed={isLiked}
        onClick={() => toggleLike(movie)}
        title={isLiked ? "Remove like" : "Like this movie"}
      >
        <Icon
          name="heart"
          width={17}
          height={17}
          fill={isLiked ? "currentColor" : "none"}
        />
        {!compact && <span>{isLiked ? "Liked" : "Like"}</span>}
      </button>
      <label
        className={`rating-control${rating ? " is-active" : ""}`}
        title="Rate this movie"
      >
        <Icon
          name="star"
          width={17}
          height={17}
          fill={rating ? "currentColor" : "none"}
        />
        <span className="visually-hidden">Rate {movie.title}</span>
        <select
          value={rating}
          onChange={(event) => rateMovie(movie, Number(event.target.value))}
        >
          <option value="0">Rate</option>
          <option value="1">1 / 5</option>
          <option value="2">2 / 5</option>
          <option value="3">3 / 5</option>
          <option value="4">4 / 5</option>
          <option value="5">5 / 5</option>
        </select>
      </label>
      <button
        type="button"
        className="action-button"
        onClick={() => setCollectionOpen(true)}
        title="Add to a collection"
        aria-label="Add to a collection"
      >
        <Icon name="plus" width={17} height={17} />
        {!compact && <span>Collect</span>}
      </button>
      {allowDismiss && (
        <button
          type="button"
          className="action-button action-muted"
          onClick={() => dismissMovie(movie)}
          title="Show me fewer like this"
        >
          <Icon name="x" width={17} height={17} />
          {!compact && <span>Not for me</span>}
        </button>
      )}
      {compact && (
        <Link
          className="action-button"
          href={`/movies/${encodeURIComponent(movie.id)}`}
          title={`View ${movie.title}`}
        >
          <Icon name="arrow" width={17} height={17} />
        </Link>
      )}
      <CollectionDialog
        movie={movie}
        open={collectionOpen}
        onClose={() => setCollectionOpen(false)}
      />
    </div>
  );
}
