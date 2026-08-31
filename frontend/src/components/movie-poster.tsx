"use client";

import Image from "next/image";
import { useState } from "react";
import type { Movie } from "../types/api";
import { Icon } from "./icons";

export function MoviePoster({
  movie,
  priority = false,
  className = "",
}: {
  movie: Movie;
  priority?: boolean;
  className?: string;
}) {
  const [failed, setFailed] = useState(false);

  return (
    <div className={`movie-poster ${className}`} data-title={movie.title}>
      {movie.posterUrl && !failed ? (
        <Image
          src={movie.posterUrl}
          alt={`${movie.title} poster`}
          fill
          sizes="(max-width: 600px) 42vw, (max-width: 1000px) 25vw, 220px"
          className="poster-image"
          priority={priority}
          unoptimized
          onError={() => setFailed(true)}
        />
      ) : (
        <div
          className="poster-fallback"
          role="img"
          aria-label={`No poster available for ${movie.title}`}
        >
          <Icon name="film" width={30} height={30} />
          <strong>{movie.originalTitle || movie.title}</strong>
          <span>{movie.releaseYear ?? "Tamil cinema"}</span>
        </div>
      )}
      <span className="poster-sheen" aria-hidden="true" />
    </div>
  );
}
