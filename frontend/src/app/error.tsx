"use client";
import { Icon } from "../components/icons";
export default function GlobalError({
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <div className="page-shell narrow-page">
      <section className="state-panel error-panel" role="alert">
        <Icon name="retry" width={38} height={38} />
        <h1>Something interrupted this page</h1>
        <p>Your saved activity is safe. Try rendering the page again.</p>
        <button className="button button-primary" onClick={reset}>
          <Icon name="retry" width={17} height={17} />
          Try again
        </button>
      </section>
    </div>
  );
}
