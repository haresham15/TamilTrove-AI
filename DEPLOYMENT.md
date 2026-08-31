# TamilTrove V2 deployment guide

This guide covers the checked-in production delivery path. TamilTrove is provider-neutral: GitHub Actions publishes immutable OCI images, while a narrow authenticated deployment adapter performs platform-specific migration and traffic switching.

For a local integration environment, use [infrastructure/README.md](infrastructure/README.md). Do not expose the Compose topology directly to the internet.

## Production prerequisites

- A PostgreSQL 15+ database with pgvector 0.6+ and `pg_trgm` available.
- A TLS-terminated frontend and API origin.
- A secret manager for the database URL, signing key, deployment token, and provider credentials.
- A container runtime or managed container platform that can pull from GHCR.
- Encrypted database backups, point-in-time recovery where available, and a tested isolated restore procedure.
- Restricted access to `/metrics`, Prometheus, Grafana, PostgreSQL, Redis, and OpenTelemetry receivers.
- GitHub `staging` and `production` environments; production should require reviewers and prevent self-approval.

The backend and frontend containers run as non-root users. Treat the image digest, migration ID, dataset version, embedding model version, and ranking version as separate release coordinates.

## Runtime configuration

Never copy development values from `.env.example` into production unchanged.

| Variable | Required | Production guidance |
| --- | --- | --- |
| `TAMILTROVE_ENV` | yes | `staging` or `production` |
| `TAMILTROVE_SECRET_KEY` | yes | At least 32 random bytes from a secret manager; rotate deliberately |
| `DATABASE_URL` or `TAMILTROVE_DATABASE_URL` | yes | TLS-enabled PostgreSQL DSN using a least-privilege application role |
| `ALLOWED_ORIGINS` | yes | Exact comma-separated browser origins; never `*` with credentials |
| `NEXT_PUBLIC_API_URL` | yes at frontend build | Public HTTPS API origin, without a trailing `/api/v1` |
| `TAMILTROVE_ADMIN_EMAILS` | if admin UI is used | Explicit comma-separated administrator identities |
| `TRUSTED_POSTER_HOSTS` | recommended | Exact HTTPS image host allowlist |
| `TAMILTROVE_MODEL_NAME` / `TAMILTROVE_MODEL_VERSION` | yes | Benchmark-approved model and version matching active embeddings |
| `TAMILTROVE_ENABLE_TRANSFORMER` | yes | Enable only when the image/host has the model and capacity |
| `TAMILTROVE_RANKING_VERSION` | yes | Immutable identifier for the deployed weight/feature configuration |
| `RANKING_*` | yes | Approved weights and limits captured by the ranking version |
| `RATE_LIMIT_*` / `MAX_REQUEST_BYTES` | recommended | Application limits supplemented by edge controls |
| `TAMILTROVE_DEBUG_SCORES` | yes | `false` in production |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | recommended | Authenticated internal HTTPS collector endpoint |

`NEXT_PUBLIC_API_URL` is compiled into browser assets. Configure the repository variable before a release build and verify it is appropriate for every environment receiving that frontend digest. If staging and production use different public API origins, publish distinct frontend release candidates from the same commit and never relabel one digest as the other.

## Database initialization and migration

Install extensions through a privileged database-administration step when the application migration role cannot create them:

```sql
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
```

Apply the migration from a controlled one-off job, not from multiple replicas concurrently:

```bash
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f backend/migrations/001_v2_schema.sql
```

The migration uses an advisory lock and transaction. Create a verified backup or restore point first. The down migration deletes V2 data and is not part of normal application rollback; its explicit procedure is documented in [backend/migrations/README.md](backend/migrations/README.md).

## GitHub configuration

The workflows use commit tags for discovery and registry digests for deployment.

Repository settings:

1. Allow GitHub Actions to read packages and let the release workflow write packages.
2. Define repository variable `NEXT_PUBLIC_API_URL` with the public API origin used for release builds.
3. Define `TAMILTROVE_DATASET_VERSION`, `TAMILTROVE_MODEL_NAME`, `TAMILTROVE_MODEL_VERSION`, and `TAMILTROVE_RANKING_VERSION` repository variables with the benchmark-approved compatibility tuple packaged by the release.
4. Optionally set `STAGING_DEPLOY_ENABLED=true` to deploy successful main-branch release candidates automatically.
5. Create protected `staging` and `production` environments.
6. In each environment, define secrets `DEPLOY_WEBHOOK_URL` and `DEPLOY_TOKEN`.
7. In each environment, define variable `API_BASE_URL`; optionally define `WEB_BASE_URL` for frontend smoke checks.
8. Require reviewers for production and restrict production deployment to protected branches/tags.

The webhook URL must be HTTPS. The deployment token is read from the environment and is never passed on a command line. See [the deployment adapter contract](docs/deployment-adapter.md) for the request and trust model.

## Release flow

`.github/workflows/release.yml` runs after the main-branch `V2 quality gates` workflow succeeds. Explicit dispatch is a recovery path only for a commit already on `main` with a successful main-branch quality-gates run. It:

1. Resolves and validates the exact Git commit.
2. Revalidates the relevance dataset and regression gate.
3. Builds backend and frontend images from that commit.
4. Pushes commit-addressed images to GHCR.
5. Resolves registry digests and uploads a release manifest.
6. If enabled, asks the staging adapter to run the compatible migration and deploy those digests.
7. Runs readiness/search smoke checks and the live relevance gate against staging.

Do not promote a release whose staging job was skipped unless an equivalent staging run and its evidence are recorded elsewhere.

## Manual staging or production deployment

Run the `Deploy immutable release` workflow and provide:

- `environment`: `staging` or `production`;
- `release_sha`: the full 40-character commit from the release manifest;
- `backend_image` and `frontend_image`: the exact `@sha256:` references from that manifest;
- `dataset_version`, `embedding_model`, `embedding_model_version`, and `ranking_version` copied from that manifest;
- whether migration `001_v2_schema` should be requested;
- confirmation text `deploy staging` or `deploy production`.

The workflow rejects tags and cross-repository references, pulls the supplied digests, verifies both OCI revision labels against `release_sha`, invokes the environment-scoped adapter, then runs smoke and live relevance checks. A production reviewer should confirm that the manifest digests exactly match the staging evidence before approval.

## Post-deployment verification

At minimum, verify:

```bash
python infrastructure/scripts/smoke.py \
  --api-url https://api.example.com \
  --web-url https://app.example.com

python evaluation/scripts/evaluate.py \
  --api-url https://api.example.com \
  --output evaluation/reports/api-production.json
python evaluation/scripts/release_gate.py evaluation/reports/api-production.json
```

Then review readiness, request/error rate, p95/p99 search latency, zero-result rate, database latency, authentication, cross-account ownership, feedback, and collection sharing. Run the checked-in k6 profile from a network representative of users. Record the image digests and active dataset/model/ranking versions in the change record.

## Rollback

Application and ranking/data rollback do not imply schema downgrade.

1. Identify the last known-good backend and frontend `@sha256:` references from a successful release manifest.
2. Confirm the old application is compatible with the current additive schema.
3. Select a retained dataset and embedding/model pair when data caused the incident.
4. Run `Rollback immutable release`, supplying both digests, the target dataset/embedding/ranking compatibility tuple, a concise incident reason, and confirmation text `rollback <environment>`.
5. The adapter switches to the supplied immutable coordinates; the workflow reruns smoke and live relevance gates.
6. Keep the incident open if verification fails. Remove unhealthy instances from traffic and restore from a verified backup only when pointer rollback cannot recover correctness.

The workflow rejects mutable image tags, cross-repository image references, and images whose revision labels do not match the selected commit. It does not run the destructive down migration. See [operations.md](docs/operations.md) for incident playbooks and recovery rules.

## Backup and restore evidence

Before first production traffic and on a recurring schedule:

1. Create an encrypted backup or snapshot.
2. Restore it to a new isolated database with no production application access.
3. Apply read-only verification for schema version, row counts, stable movie IDs, user/collection ownership, active dataset/ranking/model pointers, and embedding count/dimension/content-hash alignment.
4. Start the release image against the restored database and run readiness, smoke, and selected authorization tests.
5. Destroy the isolated restore through the platform's approved process and record date, operator, artifact, recovery duration, and result.

A backup that has never passed an isolated restore test is not accepted rollback evidence.

## Host-specific notes

Vercel, Render, and similar platforms can still host the application, but the V1 arrangement of a stateless backend plus bundled JSON files is not the V2 production architecture. Any chosen host must provide the PostgreSQL/pgvector, one-off migration, immutable artifact, secret, health-check, and rollback controls above. Free tiers commonly have cold starts or resource limits; measure them rather than claiming the 750 ms warm-search objective.
