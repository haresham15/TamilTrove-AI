# Deployment adapter contract

TamilTrove's GitHub workflows intentionally do not receive SSH access or a general-purpose cloud credential. They call a narrow environment-scoped HTTPS endpoint that validates and applies an immutable deployment intent.

The adapter is operated by the deployment owner. It can front a Kubernetes controller, managed-container API, GitOps reconciler, or a locked-down single-host service.

## Authentication and transport

- Accept HTTPS only; terminate TLS at an authenticated, monitored endpoint.
- Require `Authorization: Bearer <environment-scoped-token>` and rotate the token through GitHub environment secrets.
- Restrict the endpoint by repository/workflow identity or source network when supported.
- Use `Idempotency-Key` to return the result of an already accepted request rather than repeating it.
- Reject redirects, mutable image tags, unexpected registry/repository names, unknown migration IDs, unknown dataset/ranking versions, and an environment that does not match the token.
- Rate-limit requests and log the request ID, action, environment, release ID, immutable coordinates, actor identity, result, and duration. Never log the bearer token.

The client sends `Content-Type: application/json`, `Accept: application/json`, `User-Agent: tamiltrove-deployment-client/2`, and a unique `X-Request-ID`.

## Request body

```json
{
  "schema_version": 2,
  "action": "deploy",
  "environment": "staging",
  "release_id": "0123456789abcdef0123456789abcdef01234567",
  "backend_image": "ghcr.io/owner/repository/backend@sha256:...",
  "frontend_image": "ghcr.io/owner/repository/frontend@sha256:...",
  "migration_id": "001_v2_schema",
  "dataset_version": "v2-seed-1",
  "embedding_model": "sentence-transformers/all-MiniLM-L6-v2",
  "embedding_model_version": "1",
  "ranking_version": "v2-local-hybrid-1",
  "reason": "main branch release"
}
```

Supported actions:

- `migrate`: run exactly the allowlisted, backward-compatible migration from the supplied backend image as a one-off job. Acquire the migration lock, capture output, and fail without switching traffic.
- `deploy`: verify image signatures/digests and the dataset/embedding/ranking compatibility tuple, start the candidate, wait for readiness, then switch traffic atomically or through a bounded canary.
- `rollback`: switch application and dataset/embedding/ranking pointers to the explicitly supplied last-known-good coordinates. Do not downgrade the schema.

Empty optional strings are omitted by the client. `backend_image` and `frontend_image` are mandatory digest references for every action. The adapter should accept only the configured TamilTrove GHCR repository.

## Response

Return a 2xx status only after the intent has been accepted and completed synchronously, or after a controller has durably accepted it and the adapter has waited for its terminal result. The body must be JSON:

```json
{
  "accepted": true,
  "deployment_id": "platform-specific-non-secret-id",
  "status": "succeeded"
}
```

The checked-in client requires `accepted: true` and `status` equal to `succeeded`. Any other status, non-JSON response, redirect, timeout, or non-2xx response fails the workflow. Keep error bodies sanitized because GitHub may retain workflow logs.

## Server-side deployment transaction

For `deploy`, the adapter should perform these checks in order:

1. Authenticate and authorize the repository, action, and target environment.
2. Validate the request schema and idempotency key.
3. Resolve and verify both supplied registry digests without accepting a tag substitution.
4. Verify the migration, dataset, embedding model, and ranking versions are mutually compatible.
5. Create the candidate revision with production secrets injected only at runtime.
6. Wait for process health and dependency readiness.
7. Run a small internal smoke check before it can receive public traffic.
8. Switch traffic or canary, observe the configured error/latency window, and record the previous coordinates.
9. Return a non-secret deployment identifier.

GitHub performs external smoke and relevance checks after this transaction. A deployment remains reversible until those gates and the observation window pass.

## Local contract test

`infrastructure/scripts/deployment_webhook.py --dry-run` validates an intent and prints its redacted JSON without making a request:

```bash
python infrastructure/scripts/deployment_webhook.py \
  --dry-run \
  --action deploy \
  --environment staging \
  --release-id 0123456789abcdef0123456789abcdef01234567 \
  --backend-image ghcr.io/owner/repository/backend@sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa \
  --frontend-image ghcr.io/owner/repository/frontend@sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb \
  --dataset-version v2-seed-1 \
  --embedding-model sentence-transformers/all-MiniLM-L6-v2 \
  --embedding-model-version 1 \
  --ranking-version v2-local-hybrid-1
```

Dry-run output never contains the deployment URL or token.
