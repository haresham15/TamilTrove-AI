export default function MovieLoading() {
  return (
    <div className="page-shell">
      <div className="detail-skeleton">
        <div className="skeleton skeleton-detail-poster" />
        <div className="skeleton-stack">
          <div className="skeleton skeleton-line short" />
          <div className="skeleton skeleton-line wide" />
          <div className="skeleton skeleton-copy large" />
        </div>
      </div>
      <span className="visually-hidden">Loading movie details</span>
    </div>
  );
}
