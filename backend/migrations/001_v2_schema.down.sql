-- Safe structural rollback for 001_v2_schema.sql.
-- This is destructive to V2 data. Back up/export first.
-- Deliberately does not drop vector or pg_trgm because extensions may be shared.

BEGIN;

SET LOCAL lock_timeout = '10s';
SET LOCAL statement_timeout = '5min';
SET LOCAL search_path = public, pg_catalog;

SELECT pg_advisory_xact_lock(hashtext('tamiltrove:001_v2_schema'));

-- Drop exact migration-owned objects in reverse dependency order. Avoid
-- CASCADE so an unexpected external dependency makes rollback fail safely.
DROP TABLE IF EXISTS public.collection_items;
DROP TABLE IF EXISTS public.collections;

DROP TABLE IF EXISTS public.user_movie_states;
DROP TABLE IF EXISTS public.user_interactions;
DROP TABLE IF EXISTS public.user_profile_embeddings;
DROP TABLE IF EXISTS public.user_preferred_themes;
DROP TABLE IF EXISTS public.user_preferred_genres;
DROP TABLE IF EXISTS public.user_preferences;

DROP TABLE IF EXISTS public.recommendation_event_results;
DROP TABLE IF EXISTS public.recommendation_events;
DROP TABLE IF EXISTS public.search_history;
DROP TABLE IF EXISTS public.search_event_results;
DROP TABLE IF EXISTS public.search_events;
DROP TABLE IF EXISTS public.ranking_configs;

DROP TABLE IF EXISTS public.movie_quality_issues;
DROP TABLE IF EXISTS public.data_quality_reports;
DROP TABLE IF EXISTS public.quarantine_records;
DROP TABLE IF EXISTS public.staged_movie_records;

DROP TABLE IF EXISTS public.movie_embeddings;
DROP TABLE IF EXISTS public.movie_themes;
DROP TABLE IF EXISTS public.movie_genres;
DROP TABLE IF EXISTS public.themes;
DROP TABLE IF EXISTS public.genres;
DROP TABLE IF EXISTS public.movie_credits;
DROP TABLE IF EXISTS public.person_field_provenance;
DROP TABLE IF EXISTS public.person_aliases;
DROP TABLE IF EXISTS public.person_external_ids;
DROP TABLE IF EXISTS public.people;
DROP TABLE IF EXISTS public.movie_field_provenance;
DROP TABLE IF EXISTS public.movie_aliases;
DROP TABLE IF EXISTS public.movie_external_ids;
DROP TABLE IF EXISTS public.movies;

DROP TABLE IF EXISTS public.embedding_model_versions;
DROP TABLE IF EXISTS public.ingestion_runs;
DROP TABLE IF EXISTS public.dataset_versions;
DROP TABLE IF EXISTS public.ingestion_sources;

DROP TABLE IF EXISTS public.auth_sessions;
DROP TABLE IF EXISTS public.revoked_access_tokens;
DROP TABLE IF EXISTS public.users;

DROP FUNCTION IF EXISTS public.tamiltrove_is_finite(double precision);
DROP FUNCTION IF EXISTS public.tamiltrove_set_updated_at();

COMMIT;
