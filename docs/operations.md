# Operations, deployment, and incident response

## Service objectives and signals

The initial production targets are search p95 below 750 ms under the checked-in warm-load profile, less than 1% server errors, and less than 15% zero-result searches for representative traffic. Relevance has a separate 80% Hit@5 release floor and language-slice gates. Adjust targets only with recorded measurements and product review.

Prometheus scrapes request/error counts, route duration, search duration/stages, zero results, interaction conversion, and ingestion/quarantine counters. Structured JSON logs include timestamp, severity, service, environment, request/trace ID, route template, status, duration, ranking version, and sanitized error or job/dataset context. Avoid raw query/user/token values.

`/health` diagnoses the process. `/ready` diagnoses required catalog/model/database dependencies and controls routing. OpenTelemetry spans cover request handling, normalization/embedding, lexical/vector retrieval, reranking, repository calls, and explanation generation when an exporter is configured.

## Release procedure

1. Pin and install dependencies; run formatting, lint, types, backend/frontend/evaluation tests, database migration checks, and builds.
2. Build immutable images tagged by Git commit and scan dependencies and images.
3. Back up PostgreSQL and test the backup in an isolated database on the scheduled restore cadence.
4. Apply backward-compatible migrations as a controlled one-off job.
5. Deploy the immutable artifact and compatible dataset/ranking version to staging.
6. Wait for readiness, run `infrastructure/scripts/smoke.py`, browser E2E/accessibility tests, the live relevance benchmark, and k6 thresholds.
7. Review the protected production environment approval, promote the exact staged image digests, and canary if supported.
8. Verify health, readiness, p95/error/zero-result signals, auth, search, interactions, and collection sharing. Record the deployment versions.

## Rollback

Stop promotion when any gate fails. Roll back the application to the previously retained immutable digest. Ranking weights/feature flags and the active dataset pointer can roll back independently. Do not downgrade a database schema until the older application is active, the migration is explicitly reversible, and a restore point is verified. Re-run readiness and smoke checks after rollback.

## Backups and recovery

Use encrypted managed PostgreSQL backups plus point-in-time recovery. A backup is only credible after an isolated restore test verifies row counts, stable movie IDs, users/ownership, active dataset/version metadata, and embedding alignment. Keep Redis out of the recovery critical path because it is not canonical.

Define recovery objectives for the target host. A reasonable initial portfolio deployment target is a 24-hour recovery point and four-hour recovery time; production owners must choose and test the actual values.

## Incident playbooks

### Readiness failure

Remove the instance from traffic, inspect dependency/model initialization and latest migration/dataset logs, verify database reachability and active embedding compatibility, then restart only if initialization is safe and bounded. Roll back the artifact or dataset if the failure began at deployment.

### Elevated errors

Correlate the alert window by route template, deployment, request/trace ID, and dependency latency. Protect the service with tighter rate limits or feature-flagged expensive stages. Do not log or paste tokens/user data into the incident channel. Roll back on a release-correlated regression.

### Search latency regression

Compare embedding, lexical/vector retrieval, database, reranking, and explanation span durations. Check cold starts, pool saturation, query plans/index health, candidate limits, and cache measurements. Preserve relevance gates when changing ranking stages.

### Relevance or zero-result regression

Freeze ranking/dataset promotion, run the benchmark by language/category, inspect normalization and filter parsing, compare ranking versions, and roll back the ranking configuration or dataset pointer. Record representative sanitized queries only under the approved analytics policy.

### Failed ingestion or data-quality regression

Leave the current canonical version active, stop promotion, preserve staging/quarantine evidence, and identify source drift, identity ambiguity, or validator changes. Retry only temporary failures. A bad external correction must not overwrite trustworthy canonical data.

### Credential exposure

Revoke/rotate the credential immediately, inspect access logs without propagating the secret, invalidate affected sessions, remove it from deployment/build systems and Git history using an approved incident procedure, and document scope plus required user notification.

After every material incident, write a blameless timeline, user impact, detection gap, root cause, corrective owner/date, and a regression test or alert improvement.
