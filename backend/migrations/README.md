# Backend database migrations

`001_v2_schema.sql` creates the empty TamilTrove V2 PostgreSQL schema. It requires PostgreSQL 15+ and pgvector 0.6+ (HNSW support). The migration enables `vector` and `pg_trgm`; the migration role therefore needs permission to create extensions, or an administrator must install them first.

Apply from the repository root with an empty or backed-up target database:

```sh
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f backend/migrations/001_v2_schema.sql
```

PowerShell equivalent:

```powershell
psql $env:DATABASE_URL -v ON_ERROR_STOP=1 -f backend/migrations/001_v2_schema.sql
```

Rollback is intentionally destructive to all V2 table data. Export or snapshot the database first:

```sh
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f backend/migrations/001_v2_schema.down.sql
```

The rollback removes only objects owned by migration 001, uses no `CASCADE`, and leaves shared extensions installed. Both scripts use a transaction, stop on SQL errors when invoked as above, and take the same advisory lock to prevent concurrent apply/rollback.

## Compatibility and adoption

- This migration does not modify or import the legacy `movies_processed.json` and `embeddings.npy` files, and it does not change the V1 `/api/search` contract. Import is a separate versioned ingestion step.
- Seed an ingestion source, dataset version, embedding-model version, and ranking config before promoting catalog rows. Activate a dataset/model/ranking config and their embeddings atomically only after validation succeeds.
- Embeddings are fixed at 384 dimensions to match the current model artifacts and permit a usable HNSW index. A model with another dimension needs an additive migration plus a backfill and atomic index/config switch; do not mix vector spaces in active rows.
- The schema permits one active dataset, one active embedding model, one default ranking config, and one active embedding per movie or user. Application code must update these flags in a single transaction.
- `user_id` and `owner_id` columns are intentionally present on user-owned data, including collection and recommendation children. RLS is not enabled here because the database-role and request-context convention is deployment-specific. Until policies are added, use a server-only database role and enforce authorization in every service/repository method.
- Search query text can be retained only when `analytics_consent` is true. Tokens, raw IP addresses, and raw user agents have no storage columns; only hashes are accepted for session security and anonymous correlation.
- The migration creates constraints and indexes, not database roles, grants, backups, scheduled jobs, partitions, or retention policies. Configure those per environment before production traffic.
