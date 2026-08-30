"use client";

import Image from 'next/image';
import { useEffect, useRef, useState } from 'react';
import styles from './page.module.css';

interface Movie {
  index: number;
  title: string;
  genre: string;
  director: string;
  cast: string;
  overview: string;
  prominence_score: number;
  similarity_score: number;
  final_score: number;
  poster_url?: string;
  plot_x?: number;
  plot_y?: number;
}

export default function Home() {
  const [query, setQuery] = useState('');
  const [beta, setBeta] = useState(0.8);
  const [results, setResults] = useState<Movie[]>([]);
  const [loading, setLoading] = useState(false);
  const [hasSearched, setHasSearched] = useState(false);
  const [queryPlot, setQueryPlot] = useState<{x: number, y: number} | null>(null);
  const [error, setError] = useState<string | null>(null);
  const activeRequest = useRef<AbortController | null>(null);

  // Modal State
  const [selectedMovie, setSelectedMovie] = useState<Movie | null>(null);

  useEffect(() => {
    return () => activeRequest.current?.abort();
  }, []);

  useEffect(() => {
    if (!selectedMovie) return;

    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setSelectedMovie(null);
    };
    window.addEventListener('keydown', closeOnEscape);
    return () => window.removeEventListener('keydown', closeOnEscape);
  }, [selectedMovie]);

  const handleSearch = async () => {
    if (!query.trim()) return;
    
    activeRequest.current?.abort();
    const controller = new AbortController();
    activeRequest.current = controller;
    setLoading(true);
    setHasSearched(true);
    setError(null);
    
    try {
      const apiUrl = (process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8001').replace(/\/+$/, '');
      const response = await fetch(`${apiUrl}/api/search`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          query: query,
          beta: beta,
          alpha: 1.0
        }),
        signal: controller.signal,
      });

      const data = await response.json().catch(() => null);
      if (!response.ok) {
        throw new Error(data?.detail || data?.error || `Search failed (${response.status})`);
      }
      if (data.results) {
        setResults(data.results);
      } else {
        setResults([]);
      }
      
      if (data.query_plot) {
        setQueryPlot(data.query_plot);
      } else {
        setQueryPlot(null);
      }
    } catch (error) {
      if (error instanceof DOMException && error.name === 'AbortError') return;
      console.error("Error searching movies:", error);
      setResults([]);
      setQueryPlot(null);
      setError(error instanceof Error ? error.message : 'Unable to search right now.');
    } finally {
      if (activeRequest.current === controller) {
        activeRequest.current = null;
        setLoading(false);
      }
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.nativeEvent.isComposing) {
      handleSearch();
    }
  };

  const handleSliderChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setBeta(parseFloat(e.target.value));
  };
  
  const handleSliderRelease = () => {
    if (hasSearched && query.trim()) {
      handleSearch();
    }
  };
  return (
    <main className={styles.main}>
      <header className={styles.hero}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '1rem', marginBottom: '1rem' }}>
          <Image src="/logo.png" width={64} height={64} priority alt="TamilTrove logo" style={{ borderRadius: '16px', boxShadow: '0 4px 14px rgba(0, 0, 0, 0.5)' }} />
          <div className={styles.heroBadge}>TamilTrove AI</div>
        </div>
        <h1 className={styles.title}>Unearth Kollywood Masterpieces</h1>
        <p className={styles.subtitle}>
          New to Kollywood or searching for your next favorite film? Don&apos;t let the sheer volume of releases overwhelm you.
          Simply describe the narrative &quot;vibe&quot; or plot you are craving, and our AI will instantly dig up the perfect Tamil cinematic counterpart from the modern era (2015-2025).
          Use the <strong>Hidden Gem</strong> slider to dynamically filter out mainstream blockbusters and uncover critically acclaimed, under-the-radar masterpieces.
        </p>
      </header>

      <div className={styles.searchContainer}>
        <input 
          type="text" 
          className={styles.searchInput}
          placeholder="e.g., A gritty heist movie with complex character betrayals and intense action..."
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={handleKeyDown}
        />
        
        <div className={styles.controls}>
          <div className={styles.sliderGroup}>
            <div className={styles.sliderHeader}>
              <span className={styles.sliderLabel}>💎 Hidden Gem Filter</span>
              <span className={styles.sliderValue}>{(beta * 10).toFixed(1)}</span>
            </div>
            <input 
              type="range" 
              min="0" 
              max="2" 
              step="0.1" 
              value={beta} 
              className={styles.slider}
              onChange={handleSliderChange}
              onMouseUp={handleSliderRelease}
              onTouchEnd={handleSliderRelease}
              title="Higher values favor lesser-known movies"
            />
          </div>
          
          <button 
            className={styles.searchButton}
            onClick={handleSearch}
            disabled={loading}
            title="Run the AI Semantic Search to find your perfect movie match"
          >
            {loading ? 'Analyzing...' : 'Find Matches'}
          </button>
        </div>
      </div>

      {error && <p className={styles.errorMessage} role="alert">{error}</p>}

      {results.length > 0 && (
        <div className={styles.resultsGrid}>
          {results.map((movie, idx) => {
            const genres = movie.genre ? movie.genre.split(new RegExp('[/,]')).map(g => g.trim()).filter(Boolean) : [];
            const popularity = Math.round(movie.prominence_score * 100);
            
            return (
              <div 
                key={`${movie.index}-${idx}`} 
                className={`${styles.card} ${styles.clickableCard} fade-in`} 
                style={{ animationDelay: `${idx * 0.05}s` }}
                onClick={() => setSelectedMovie(movie)}
                title={`Click to view details for ${movie.title}`}
              >
                <div className={styles.cardHeader}>
                  <h3 className={styles.movieTitle}>{movie.title}</h3>
                  <div className={styles.matchScoreContainer} title="The overall AI Match Score combining semantic similarity and your Hidden Gem preference.">
                    <span className={styles.matchScoreLabel}>Match</span>
                    <span className={styles.matchScore}>
                      {(movie.final_score * 100).toFixed(0)}%
                    </span>
                  </div>
                </div>
                
                {genres.length > 0 && (
                  <div className={styles.tags}>
                    {genres.map(g => (
                      <span key={g} className={styles.tag} title={`Genre: ${g}`}>{g}</span>
                    ))}
                  </div>
                )}
                
                <div className={styles.metadata}>
                  <span><strong>Director:</strong> {movie.director}</span>
                  <span><strong>Cast:</strong> {movie.cast.length > 60 ? movie.cast.substring(0, 60) + '...' : movie.cast}</span>
                  <div className={styles.popularityRow} title="A score based on the global prominence of the director and cast. A lower score means it is a more niche or independent film.">
                    <span><strong>Mainstream Popularity:</strong> {popularity}/100</span>
                    <div className={styles.popBarContainer}>
                      <div className={styles.popBarFill} style={{ width: `${Math.max(popularity, 2)}%` }}></div>
                    </div>
                  </div>
                </div>
                
                <p className={styles.overview}>{movie.overview}</p>
                
                {movie.prominence_score <= 0.08 && (
                  <div className={styles.gemBadge} title="This film features indie or less frequent collaborators, making it an under-the-radar gem!">
                    💎 Certified Hidden Gem
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
      
      {/* Semantic Visualization Plot */}
      {results.length > 0 && queryPlot && (
        <div className={styles.plotContainer}>
          <div className={styles.axisX}></div>
          <div className={styles.axisY}></div>
          <span className={`${styles.axisLabel} ${styles.labelLeft}`}>Semantic Dimension 1 (–)</span>
          <span className={`${styles.axisLabel} ${styles.labelRight}`}>Semantic Dimension 1 (+)</span>
          <span className={`${styles.axisLabel} ${styles.labelTop}`}>Semantic Dimension 2 (+)</span>
          <span className={`${styles.axisLabel} ${styles.labelBottom}`}>Semantic Dimension 2 (–)</span>
          
          {/* Query Dot */}
          <div 
            className={`${styles.plotDot} ${styles.queryDot}`}
            style={{ 
              left: `${((queryPlot.x + 1) / 2) * 100}%`, 
              bottom: `${((queryPlot.y + 1) / 2) * 100}%` 
            }}
            title="Your search query's position in the mathematical semantic embedding space"
          >
            <span className={styles.queryLabel}>You</span>
          </div>

          {/* Results Dots */}
          {results.map((movie) => {
            if (movie.plot_x === undefined || movie.plot_y === undefined) return null;
            return (
              <div 
                key={`plot-${movie.index}`}
                className={styles.plotDot}
                style={{ 
                  left: `${((movie.plot_x + 1) / 2) * 100}%`, 
                  bottom: `${((movie.plot_y + 1) / 2) * 100}%` 
                }}
                onClick={() => setSelectedMovie(movie)}
                title={`Click to view ${movie.title}`}
              >
                <div className={styles.plotTooltip}>{movie.title}</div>
              </div>
            );
          })}
        </div>
      )}
      
      {hasSearched && results.length === 0 && !loading && !error && (
        <p className={styles.noResults}>No matches found. Try adjusting your vibe search!</p>
      )}

      {/* Modal Overlay */}
      {selectedMovie && (
        <div className={styles.modalOverlay} onClick={() => setSelectedMovie(null)} role="presentation">
          <div className={styles.modalContent} onClick={(e) => e.stopPropagation()} role="dialog" aria-modal="true" aria-labelledby="movie-dialog-title">
            <button className={styles.closeButton} onClick={() => setSelectedMovie(null)} title="Close Movie Details">✕</button>
            
            <div className={styles.modalPoster}>
              {selectedMovie.poster_url ? (
                <Image src={selectedMovie.poster_url} alt={`${selectedMovie.title} poster`} className={styles.posterImage} width={500} height={750} unoptimized />
              ) : (
                <div className={styles.posterFallback}>
                  <span style={{ fontSize: '3rem' }}>🎬</span>
                  <p>No Official Poster Found</p>
                </div>
              )}
            </div>
            
            <div className={styles.modalBody}>
              <h2 id="movie-dialog-title" className={styles.title} style={{ fontSize: '2.5rem', marginBottom: '0.5rem' }}>{selectedMovie.title}</h2>
              
              <div className={styles.tags}>
                {selectedMovie.genre && selectedMovie.genre.split(new RegExp('[/,]')).map(g => (
                  <span key={g} className={styles.tag} title={`Genre: ${g.trim()}`}>{g.trim()}</span>
                ))}
              </div>
              
              <div className={styles.metadata} style={{ background: 'transparent', padding: 0 }}>
                <span><strong>Director:</strong> {selectedMovie.director}</span>
                <span><strong>Cast:</strong> {selectedMovie.cast}</span>
                <span><strong>Mainstream Popularity:</strong> {Math.round(selectedMovie.prominence_score * 100)} / 100</span>
              </div>
              
              <div className={styles.modalSynopsis}>
                <strong>Synopsis:</strong><br /><br />
                {selectedMovie.overview}
              </div>
            </div>
          </div>
        </div>
      )}
    </main>
  );
}
