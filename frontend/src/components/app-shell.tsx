"use client";

import Image from "next/image";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useApp } from "./app-provider";
import { Icon } from "./icons";

const primaryLinks = [
  { href: "/", label: "Discover" },
  { href: "/for-you", label: "For You" },
  { href: "/collections", label: "Collections" },
  { href: "/profile", label: "My Trove" },
];

function NavLinks({ mobile = false }: { mobile?: boolean }) {
  const pathname = usePathname();
  const { profile } = useApp();
  const links = profile?.isAdmin
    ? [...primaryLinks, { href: "/admin/data-quality", label: "Data quality" }]
    : primaryLinks;

  return (
    <nav
      className={mobile ? "mobile-nav-links" : "site-nav"}
      aria-label={mobile ? "Mobile navigation" : "Primary navigation"}
    >
      {links.map((link) => {
        const current =
          link.href === "/" ? pathname === "/" : pathname.startsWith(link.href);
        return (
          <Link
            key={link.href}
            href={link.href}
            aria-current={current ? "page" : undefined}
          >
            {link.label}
          </Link>
        );
      })}
    </nav>
  );
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const { profile, notice, sessionMode } = useApp();

  return (
    <>
      <a className="skip-link" href="#main-content">
        Skip to main content
      </a>
      <header className="site-header">
        <div className="header-inner">
          <Link className="brand" href="/" aria-label="TamilTrove home">
            <span className="brand-mark">
              <Image src="/logo.png" alt="" width={38} height={38} priority />
            </span>
            <span className="brand-copy">
              <strong>TamilTrove</strong>
              <small>Stories, not algorithms</small>
            </span>
          </Link>

          <NavLinks />

          <div className="header-actions">
            {profile ? (
              <Link
                className="profile-pill"
                href="/profile"
                aria-label={`Open ${profile.displayName}'s profile`}
              >
                <span className="avatar" aria-hidden="true">
                  {profile.displayName.slice(0, 1).toUpperCase()}
                </span>
                <span>{profile.displayName.split(" ")[0]}</span>
              </Link>
            ) : (
              <Link className="button button-small button-primary" href="/auth">
                Sign in
              </Link>
            )}
            <details className="mobile-menu">
              <summary aria-label="Open navigation menu">
                <Icon name="menu" width={22} height={22} />
              </summary>
              <div className="mobile-menu-panel">
                <NavLinks mobile />
                {!profile && (
                  <Link className="button button-primary" href="/auth">
                    Sign in
                  </Link>
                )}
              </div>
            </details>
          </div>
        </div>
      </header>

      {sessionMode === "demo" && (
        <div className="demo-banner" role="status">
          <Icon name="info" width={16} height={16} />
          <span>On-device demo mode · your activity stays in this browser</span>
        </div>
      )}

      <main id="main-content" tabIndex={-1}>
        {children}
      </main>

      <footer className="site-footer">
        <div>
          <Link className="brand footer-brand" href="/">
            <span className="brand-mark mini">
              <Image src="/logo.png" alt="" width={28} height={28} />
            </span>
            <strong>TamilTrove</strong>
          </Link>
          <p>
            Grounded discovery for Tamil cinema—in English, தமிழ், and Tanglish.
          </p>
        </div>
        <div className="footer-links" aria-label="Footer navigation">
          <Link href="/profile#privacy">Privacy</Link>
          <Link href="/collections/voices-of-change">Featured collection</Link>
          <span>V2 preview</span>
        </div>
      </footer>

      <div
        className={`toast${notice ? " is-visible" : ""}${notice ? ` toast-${notice.tone}` : ""}`}
        role={notice?.tone === "error" ? "alert" : "status"}
        aria-live={notice?.tone === "error" ? "assertive" : "polite"}
        aria-atomic="true"
      >
        {notice && (
          <>
            <Icon
              name={notice.tone === "success" ? "check" : "info"}
              width={18}
              height={18}
            />
            <span>{notice.message}</span>
          </>
        )}
      </div>
    </>
  );
}
