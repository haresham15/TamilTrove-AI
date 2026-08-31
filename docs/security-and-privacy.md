# Security and privacy

## Data classification

- Public catalog data: movie metadata, public collections, aggregate operational metrics.
- User-owned data: email/login identity, preferences, ratings, watchlist, dismissals, private/unlisted collections, and search history.
- Secrets: password hashes, signing keys, database credentials, provider credentials, session/bearer tokens.

Secrets stay server-side and out of Git, browser bundles, metrics, traces, exception bodies, and logs. `.env.example` contains development placeholders only.

## Authentication and authorization

Passwords are processed with a reviewed adaptive password-hashing implementation and are never recoverable. Production signing keys must be high entropy and rotated through the deployment secret store. Tokens are short lived. Browser authentication uses a Secure, HttpOnly, SameSite cookie where deployed on compatible origins; bearer support exists for non-browser API clients. Cookie-authenticated mutations validate the request origin/CSRF posture.

Authentication is not authorization. Every user-owned query includes the authenticated owner ID. Collection update/delete/item operations reject non-owners. Share tokens are opaque, revocable, and reveal only collection/movie presentation data. Changing a collection back to private invalidates public access.

## API controls

- Pydantic contracts constrain lengths, values, pagination, filters, and external URLs.
- CORS is an allowlist, never reflected from arbitrary origins with credentials.
- Request size and route-aware rate limits constrain expensive search/auth traffic.
- Poster/source URLs require HTTPS and trusted-host validation; redirects and image rendering remain untrusted input.
- Errors use a stable envelope with a request ID and sanitized detail.
- Database access uses parameterized repository operations and transactions.
- Admin ingestion/data-quality endpoints require an authenticated configured administrator.

Production should add a trusted edge proxy for TLS, body limits, IP-abuse controls, and security headers. Do not expose PostgreSQL, Redis, Prometheus, Grafana, or the OpenTelemetry receiver publicly.

## Privacy behavior

Recommendation processing uses only interactions associated with the consenting authenticated account. Logs use request IDs or an anonymous session identifier, never raw email, profile text, credentials, full query history, or token values. Public pages cannot include private “because you liked…” evidence.

Users can inspect/update preferences, clear search history, remove individual interactions, reset recommendation signals, export their profile, and delete their account. Account deletion transactionally removes or anonymizes owned interactions and private resources according to the documented retention policy. Backups expire on their normal encrypted retention schedule; they are not restored merely to recover a deleted account.

Before a public launch, publish the exact analytics purposes, lawful/consent basis, retention periods, subprocessors, deletion delay, contact route, and whether query text is retained. The repository implements controls but is not itself a legal privacy notice.

## Review checklist

For each release: scan Python/Node dependencies and images; verify secrets are absent from Git and built assets; test cross-account ownership boundaries; verify cookie/CORS/CSRF settings in the deployed origin topology; exercise export/deletion; inspect logs/traces for identifiers; and confirm encrypted backup restore plus key rotation procedures.
