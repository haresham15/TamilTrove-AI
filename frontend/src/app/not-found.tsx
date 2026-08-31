import Link from "next/link";
import { Icon } from "../components/icons";
export default function NotFound() {
  return (
    <div className="page-shell narrow-page">
      <section className="state-panel">
        <Icon name="film" width={40} height={40} />
        <span className="eyebrow">404 · missing reel</span>
        <h1>That page isn’t in the trove</h1>
        <p>The link may have changed, or the collection may be private.</p>
        <Link className="button button-primary" href="/">
          Return to discovery
        </Link>
      </section>
    </div>
  );
}
