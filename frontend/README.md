# TamilTrove V2 frontend

TamilTrove is a responsive, accessible Next.js 16 App Router client for multilingual Tamil-film discovery. It supports English, Tamil, and Tanglish search; transparent ranking explanations; filters; personal recommendations; profiles and privacy controls; interactions; and private, unlisted, or public collections.

## Local setup

Requirements: Node.js 22 and npm 11.

```bash
cp .env.example .env.local
npm ci
npm run dev
```

Open `http://localhost:3000`. By default the UI calls `http://localhost:8000`. If that API cannot be reached, discovery and account flows switch to a clearly labeled, browser-only demo catalog so every UX state remains reviewable. Non-network API failures (authorization, validation, and server errors) are shown instead of being hidden by the demo.

`NEXT_PUBLIC_API_URL` is public and embedded during `next build`; do not put secrets in any `NEXT_PUBLIC_*` variable.

## Quality checks

```bash
npm run format:check
npm run lint
npm run typecheck
npm run test
npm run build
npm run e2e:install
npm run e2e
```

Component tests use Vitest, jsdom, and Testing Library. Async Server Components are kept thin and their interactive clients are tested independently. The production build uses Next.js standalone output.
Playwright covers multilingual search and filters, backend-failure recovery, keyboard-only navigation, responsive Chromium, and an axe WCAG A/AA scan. Set `PLAYWRIGHT_BASE_URL` to exercise an already-running staging deployment.

## Main routes

- `/` — multilingual natural-language search, filters, ranking evidence, and result actions.
- `/for-you` — personalized, hidden-gem, and recently-added shelves.
- `/movies/[id]` — canonical details, provenance, feedback, and similar films.
- `/auth` and `/onboarding` — account and explicit cold-start preferences.
- `/profile` — watchlist, ratings, history, privacy, export, reset, and deletion.
- `/collections` and `/collections/[id]` — curation, ownership controls, and safe sharing.
- `/admin/data-quality` — role-gated validation and quarantine reporting.

## Container

```bash
docker build --build-arg NEXT_PUBLIC_API_URL=http://backend:8000 -t tamiltrove-frontend .
docker run --rm -p 3000:3000 tamiltrove-frontend
```

The final image runs as an unprivileged user and includes only standalone runtime output. Put a reverse proxy in front of the container for TLS and edge request limits.
