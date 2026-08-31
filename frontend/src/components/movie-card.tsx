import Link from "next/link";
import type { MovieResult } from "../types/api";
import { Icon } from "./icons";
import { MovieActions } from "./movie-actions";
import { MoviePoster } from "./movie-poster";

export function MovieCard({
  movie,
  index = 0,
  interactive = true,
  compact = false,
}: {
  movie: MovieResult;
  index?: number;
  interactive?: boolean;
  compact?: boolean;
}) {
  const match = Math.round(movie.scores.final * 100);
  return (
    <article
      className={`movie-card${compact ? " movie-card-compact" : ""}`}
      style={{ "--card-index": index } as React.CSSProperties}
    >
      <Link
        className="poster-link"
        href={`/movies/${encodeURIComponent(movie.id)}`}
        aria-label={`View details for ${movie.title}`}
      >
        <MoviePoster movie={movie} priority={index < 2} />
        {movie.prominenceScore < 0.35 && (
          <span className="poster-badge">Hidden gem</span>
        )}
      </Link>
      <div className="movie-card-body">
        <div className="movie-card-heading">
          <div>
            <p className="movie-kicker">
              {movie.releaseYear ?? "Tamil"}
              {movie.runtimeMinutes ? ` · ${movie.runtimeMinutes} min` : ""}
            </p>
            <h3>
              <Link href={`/movies/${encodeURIComponent(movie.id)}`}>
                {movie.title}
              </Link>
            </h3>
            {movie.originalTitle && movie.originalTitle !== movie.title && (
              <p className="original-title" lang="ta">
                {movie.originalTitle}
              </p>
            )}
          </div>
          <div
            className="match-ring"
            style={{ "--score": `${match * 3.6}deg` } as React.CSSProperties}
            title={`${match}% match`}
          >
            <span>{match}</span>
            <small>%</small>
          </div>
        </div>

        <div className="chip-row" aria-label="Genres and themes">
          {[...movie.genres, ...movie.themes]
            .slice(0, compact ? 2 : 4)
            .map((tag) => (
              <span className="chip" key={tag}>
                {tag}
              </span>
            ))}
        </div>

        {!compact && <p className="movie-overview">{movie.overview}</p>}

        <div className="match-reason">
          <Icon name="sparkle" width={18} height={18} />
          <div>
            <strong>Why it fits</strong>
            <p>{movie.explanation.summary}</p>
            {movie.explanation.evidence.length > 0 && (
              <details>
                <summary>See matching evidence</summary>
                <ul>
                  {movie.explanation.evidence.map((evidence) => (
                    <li key={evidence}>{evidence}</li>
                  ))}
                </ul>
              </details>
            )}
          </div>
        </div>

        {interactive && <MovieActions movie={movie} compact={compact} />}
      </div>
    </article>
  );
}
