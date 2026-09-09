-- TamilTrove V4 multimodal search and event streaming schema migration.
-- Target: PostgreSQL 15+ and pgvector 0.6+.

BEGIN;

SET LOCAL lock_timeout = '10s';
SET LOCAL statement_timeout = '5min';
SET LOCAL search_path = public, pg_catalog;

SELECT pg_advisory_xact_lock(hashtext('tamiltrove:002_v4_multimodal_streaming'));

-- 1. Extend catalog_movies with multimodal profiles and vectors
ALTER TABLE public.catalog_movies
    ADD COLUMN IF NOT EXISTS visual_palette jsonb NOT NULL DEFAULT '{}'::jsonb,
    ADD COLUMN IF NOT EXISTS audio_profile jsonb NOT NULL DEFAULT '{}'::jsonb,
    ADD COLUMN IF NOT EXISTS vision_embedding vector(384),
    ADD COLUMN IF NOT EXISTS audio_embedding vector(384);

-- 2. Create HNSW cosine indexes for cross-modal nearest-neighbor retrieval
CREATE INDEX IF NOT EXISTS catalog_movies_vision_embedding_hnsw
    ON public.catalog_movies USING hnsw (vision_embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

CREATE INDEX IF NOT EXISTS catalog_movies_audio_embedding_hnsw
    ON public.catalog_movies USING hnsw (audio_embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

-- 3. Create real-time interaction event log table for event-driven streaming & replay
CREATE TABLE IF NOT EXISTS public.interaction_event_log (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    event_id text NOT NULL UNIQUE,
    user_id uuid NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    event_type text NOT NULL,
    movie_id uuid NOT NULL REFERENCES public.catalog_movies(id) ON DELETE CASCADE,
    session_id text,
    context jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp()
);

CREATE INDEX IF NOT EXISTS interaction_event_log_user_idx
    ON public.interaction_event_log (user_id, created_at DESC);

CREATE INDEX IF NOT EXISTS interaction_event_log_type_idx
    ON public.interaction_event_log (event_type, created_at DESC);

-- 4. Create agent session memory table
CREATE TABLE IF NOT EXISTS public.agent_sessions (
    id text PRIMARY KEY,
    user_id uuid REFERENCES public.users(id) ON DELETE CASCADE,
    messages_json jsonb NOT NULL DEFAULT '[]'::jsonb,
    context_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp()
);

CREATE INDEX IF NOT EXISTS agent_sessions_user_idx
    ON public.agent_sessions (user_id, updated_at DESC);

COMMIT;
