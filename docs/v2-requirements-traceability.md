# V2 requirements traceability

This matrix maps the acceptance criteria in [V2.md](../V2.md) to implementation and verification evidence. It distinguishes repository completion from evidence that can only be produced in a configured staging or production environment.

Status meanings:

- **Implemented**: code, configuration, documentation, and local automated coverage are present.
- **Release-gated**: implemented, but every release must produce environment-specific evidence before promotion.
- **Operational prerequisite**: the repository supplies a contract or runbook; the deployment owner must provide the managed service, credential, review, or recovery exercise.
- **Deferred**: explicitly outside V2 in the product brief.

## Success criteria and must-have scope

| V2 requirement | Repository evidence | Status and acceptance check |
| --- | --- | --- |
| English, Tamil, Tanglish, and mixed-language discovery | [`normalization.py`](../backend/app/normalization.py), [`ranking.py`](../backend/app/ranking.py), and the multilingual examples in the web experience | **Implemented.** Backend language/normalization tests and the three language benchmark slices run in CI. |
| Hybrid semantic and lexical search | [`ranking.py`](../backend/app/ranking.py), PostgreSQL hybrid candidate retrieval in [`postgres.py`](../backend/app/postgres.py), and pgvector/FTS indexes in [`001_v2_schema.sql`](../backend/migrations/001_v2_schema.sql) | **Implemented; release-gated.** Deterministic tests verify fusion/reranking. A target deployment must run the live API benchmark and warm load profile. |
| Structured filters, sorting, pagination, and discovery mode | API contracts in [`schemas.py`](../backend/app/schemas.py), ranking/filter execution in [`ranking.py`](../backend/app/ranking.py), and the discovery interface under [`frontend/src/app`](../frontend/src/app) | **Implemented.** API discovery tests cover validation and result behavior; an empty query intentionally returns diverse discovery results. |
| Stable canonical catalog in PostgreSQL and pgvector | [`001_v2_schema.sql`](../backend/migrations/001_v2_schema.sql), [`postgres.py`](../backend/app/postgres.py), and [migration guidance](../backend/migrations/README.md) | **Implemented.** PostgreSQL integration tests apply the migration and exercise the repository. Production extension installation and migration execution are controlled deployment steps. |
| Repeatable, validated, versioned ingestion | [`catalog.py`](../backend/app/catalog.py), [`ingestion.py`](../backend/app/ingestion.py), admin ingestion/data-quality API routes, and [pipeline design](data-pipeline.md) | **Implemented.** Unit/API tests cover validation, dry-run, quarantine, idempotency, and version recording. Source licensing and independent metadata review remain operator responsibilities. |
| Registration, sign-in, profiles, watchlists, ratings, likes, dismissals, and history | Versioned API routes in [`main.py`](../backend/main.py), repositories in [`storage.py`](../backend/app/storage.py) and [`postgres.py`](../backend/app/postgres.py), and authenticated web surfaces | **Implemented.** Auth, ownership, state, export, history-clear, and account-deletion boundaries are covered by backend tests. |
| Personalized recommendations and cold start | Preference signals and recommendation surfaces in [`services.py`](../backend/app/services.py), onboarding, profile, and For You pages | **Implemented.** Explicit positive/negative signals affect content-based ranking; onboarding and diverse catalog fallback handle cold start. Collaborative filtering remains deferred until interaction volume justifies it. |
| Evidence-based explanations | Deterministic explanation construction in [`ranking.py`](../backend/app/ranking.py) and explanation rendering on cards/detail/recommendation pages | **Implemented.** Explanations are built only from ranking contributions and catalog metadata; smoke checks require an explanation summary and evidence list. |
| Similar movies, collections, sharing, feedback, and recommendation history | Movie-similar and collection APIs, owner-scoped repositories, collection/profile/detail pages | **Implemented.** Private, unlisted, public, ordered-item, revocable-token, and cross-account cases are exercised by API tests. |
| Admin data-quality dashboard and ranking experiments | Admin API routes, dataset/experiment records in the PostgreSQL migration, and [`frontend/src/app/admin/data-quality`](../frontend/src/app/admin/data-quality) | **Implemented.** Access requires a configured administrator identity. |
| At least 100 reviewed relevance judgments | [`relevance-v2.0.json`](../evaluation/datasets/relevance-v2.0.json) and [`validate_dataset.py`](../evaluation/scripts/validate_dataset.py) | **Implemented.** CI validates 120 catalog-grounded judgments with 40 English, 40 Tamil, and 40 Tanglish queries. Independent audience review is required before an external quality claim. |
| Hit@5 at least 80%, with MRR/NDCG and language regression gates | [`baseline-v2.json`](../evaluation/reports/baseline-v2.json), [`evaluate.py`](../evaluation/scripts/evaluate.py), and [`release_gate.py`](../evaluation/scripts/release_gate.py) | **Implemented; release-gated.** The committed offline reproducibility baseline records 94.2% Hit@5. Release promotion requires live-API overall, per-language, regression, error, zero-result, and latency gates. |
| Search latency measured against a production target | API histograms, stage timings, [`search.js`](../infrastructure/load-tests/search.js), Prometheus alerts, and Grafana dashboard | **Release-gated.** The initial target is warm p95 below 750 ms and p99 below 1.5 s. Offline baseline timing is not presented as production capacity evidence. |
| Health, readiness, metrics, structured logs, and traces | `/health`, `/ready`, `/metrics`, [`observability.py`](../backend/app/observability.py), and [`infrastructure`](../infrastructure) | **Implemented; release-gated.** Smoke checks verify readiness and search metadata. A production collector, retention policy, and alert destinations are operational configuration. |

## API, security, privacy, and accessibility

| V2 requirement | Repository evidence | Status and acceptance check |
| --- | --- | --- |
| Versioned API, stable IDs, typed contracts, pagination, error envelope, request/ranking metadata | [`main.py`](../backend/main.py), [`schemas.py`](../backend/app/schemas.py), and the typed frontend client in [`api-client.ts`](../frontend/src/lib/api-client.ts) | **Implemented.** `/api/v1` is canonical; the old search path is a deprecated compatibility adapter. |
| Authentication, ownership, CORS, CSRF, size/rate limits, and secret handling | [`security.py`](../backend/app/security.py), request middleware, repository owner scopes, [security review](security-and-privacy.md), and [example environment](../.env.example) | **Implemented; release-gated.** Production must use high-entropy managed secrets, exact HTTPS origins, edge controls, and deployed cross-account/cookie-topology tests. |
| Export, deletion, privacy controls, and consent-safe telemetry | Profile/export/delete/history routes and [privacy behavior](security-and-privacy.md) | **Implemented.** The deployer must publish retention, analytics purpose/consent, subprocessors, deletion delay, and contact terms before public traffic. |
| Keyboard operation, semantic structure, status announcements, focus/contrast, and reduced motion | Shared shell/components and global responsive/accessibility styles under [`frontend/src`](../frontend/src) | **Implemented; release-gated.** Component tests cover critical interaction states; browser keyboard-only and accessibility scans remain part of staging evidence. |
| Restricted external URLs and trustworthy data presentation | Catalog URL validators, trusted-poster host configuration, data-quality state, and provenance schema | **Implemented.** A deployer owns host allowlists, source terms, and final content review. |

## Testing and delivery

| V2 requirement | Repository evidence | Status and acceptance check |
| --- | --- | --- |
| Backend unit and integration coverage | [`backend/tests`](../backend/tests) covers normalization, ranking, security, repositories, ingestion, APIs, ownership, operations, and PostgreSQL | **Implemented.** CI runs the suite against a pgvector PostgreSQL service with coverage output. |
| Frontend unit/component coverage and build checks | [`frontend/tests`](../frontend/tests), Vitest/Testing Library configuration, and frontend quality scripts in [`package.json`](../frontend/package.json) | **Implemented.** CI runs formatting, ESLint, Next type generation/TypeScript, component tests, and the production build. |
| Critical end-to-end and accessibility workflows | Staging smoke script, frontend integration coverage, and the deployment verification sequence | **Release-gated.** The protected deployment must record browser-level search/filter/auth/feedback/collection/keyboard results against the actual origins. |
| Deterministic relevance tests and report publication | [`evaluation`](../evaluation), CI relevance job, and uploaded reports | **Implemented.** Pull requests use a fast deterministic guardrail; staging and rollback run live-API evaluation. |
| Dependency, secret, configuration, and container scanning | [CI workflow](../.github/workflows/ci.yml), [Dependabot](../.github/dependabot.yml), and [`validate_config.py`](../infrastructure/scripts/validate_config.py) | **Implemented.** Actions are commit-pinned; high/critical dependency, secret, misconfiguration, and image findings fail CI. |
| Immutable build, staging verification, protected promotion, and rollback | [`release.yml`](../.github/workflows/release.yml), [`deploy.yml`](../.github/workflows/deploy.yml), [`rollback.yml`](../.github/workflows/rollback.yml), and [deployment adapter contract](deployment-adapter.md) | **Implemented; operational prerequisite.** Promotion accepts only release-manifest image digests. Protected environments and the provider adapter must be configured by the repository owner. |
| Backups, restore testing, incident response, and common-failure runbooks | [deployment guide](../DEPLOYMENT.md) and [operations runbook](operations.md) | **Operational prerequisite.** The target database/platform must produce dated encrypted backup and isolated-restore evidence; documentation alone is not recovery proof. |

## Explicit boundaries

- Redis is opt-in and is not on the correctness path. It should be enabled only for a measured cache or job workload.
- Object storage is not required for the checked-in catalog/evaluation size; a production operator can attach it for durable report snapshots.
- Scheduled ingestion is exposed through an idempotent admin operation and deployment-compatible job contract. The chosen scheduler is provider-specific.
- A managed multilingual transformer is optional in local development. Any model/model-version change must regenerate compatible embeddings and pass every language slice.
- Native mobile apps, streaming/copyrighted media hosting, subscriptions, a generic chatbot, social messaging, and premature collaborative filtering remain **deferred** exactly as defined by V2.

## Release evidence checklist

A release is not production-accepted until its change record contains:

1. The full Git commit, backend/frontend image digests, migration ID, dataset version, embedding model/version, and ranking version.
2. Passing CI artifacts for backend/frontend tests, relevance regression, configuration validation, builds, and security scans.
3. Staging smoke, browser critical-flow/accessibility, live multilingual evaluation, and representative k6 results.
4. Readiness, p95/p99 latency, error, zero-result, database, and resource observations from the target topology.
5. A production approval, rollback coordinates, and a recent successful isolated database restore record.
