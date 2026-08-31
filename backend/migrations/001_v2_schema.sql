-- TamilTrove V2 canonical PostgreSQL/pgvector schema.
-- Target: PostgreSQL 15+ and pgvector 0.6+.
-- This migration is intentionally data-free; import legacy JSON/NumPy data in a
-- separate, versioned ingestion run after applying it.

BEGIN;

SET LOCAL lock_timeout = '10s';
SET LOCAL statement_timeout = '5min';
SET LOCAL search_path = public, pg_catalog;

SELECT pg_advisory_xact_lock(hashtext('tamiltrove:001_v2_schema'));

DO $$
BEGIN
    IF current_setting('server_version_num')::integer < 150000 THEN
        RAISE EXCEPTION 'TamilTrove V2 requires PostgreSQL 15 or newer';
    END IF;
END;
$$;

CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

DO $$
DECLARE
    installed_version text;
    major_version integer;
    minor_version integer;
BEGIN
    SELECT extversion
    INTO installed_version
    FROM pg_extension
    WHERE extname = 'vector';

    major_version := split_part(installed_version, '.', 1)::integer;
    minor_version := split_part(installed_version, '.', 2)::integer;

    IF major_version = 0 AND minor_version < 6 THEN
        RAISE EXCEPTION 'TamilTrove V2 requires pgvector 0.6 or newer; found %', installed_version;
    END IF;
END;
$$;

CREATE FUNCTION public.tamiltrove_set_updated_at()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.updated_at = clock_timestamp();
    RETURN NEW;
END;
$$;

CREATE FUNCTION public.tamiltrove_is_finite(input_value double precision)
RETURNS boolean
LANGUAGE sql
IMMUTABLE
PARALLEL SAFE
RETURNS NULL ON NULL INPUT
AS $$
    SELECT input_value > '-Infinity'::double precision
       AND input_value < 'Infinity'::double precision;
$$;

-- Authentication and account data -----------------------------------------

CREATE TABLE public.users (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    auth_provider text NOT NULL DEFAULT 'local',
    auth_provider_subject text,
    email text,
    password_hash text,
    display_name text NOT NULL,
    locale text NOT NULL DEFAULT 'en-US',
    preferences_json jsonb NOT NULL DEFAULT '{"favorite_genres":[],"favorite_themes":[],"preferred_eras":[],"hidden_gem_preference":0.5,"languages":["Tamil"],"dubbing_tolerance":false,"onboarding_movie_ids":[]}'::jsonb,
    privacy_json jsonb NOT NULL DEFAULT '{"store_search_history":true,"use_interactions_for_recommendations":true,"analytics_consent":false}'::jsonb,
    is_admin boolean NOT NULL DEFAULT false,
    is_disabled boolean NOT NULL DEFAULT false,
    token_version integer NOT NULL DEFAULT 1,
    last_login_at timestamptz,
    deleted_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT users_auth_provider_ck CHECK (
        auth_provider ~ '^[a-z][a-z0-9_-]{1,31}$'
    ),
    CONSTRAINT users_provider_subject_ck CHECK (
        auth_provider_subject IS NULL
        OR (char_length(btrim(auth_provider_subject)) BETWEEN 1 AND 255)
    ),
    CONSTRAINT users_email_ck CHECK (
        email IS NULL
        OR (
            email = lower(btrim(email))
            AND char_length(email) BETWEEN 3 AND 320
            AND position('@' IN email) > 1
        )
    ),
    CONSTRAINT users_display_name_ck CHECK (
        char_length(btrim(display_name)) BETWEEN 1 AND 100
    ),
    CONSTRAINT users_locale_ck CHECK (
        locale ~ '^[A-Za-z]{2,8}([_-][A-Za-z0-9]{2,8})*$'
    ),
    CONSTRAINT users_profile_json_ck CHECK (
        jsonb_typeof(preferences_json) = 'object'
        AND jsonb_typeof(privacy_json) = 'object'
    ),
    CONSTRAINT users_password_hash_ck CHECK (
        password_hash IS NULL OR char_length(password_hash) BETWEEN 20 AND 1024
    ),
    CONSTRAINT users_token_version_ck CHECK (token_version > 0),
    CONSTRAINT users_auth_identity_ck CHECK (
        (auth_provider = 'local' AND email IS NOT NULL AND password_hash IS NOT NULL)
        OR
        (auth_provider <> 'local' AND auth_provider_subject IS NOT NULL)
    )
);

CREATE UNIQUE INDEX users_active_email_uidx
    ON public.users (lower(email))
    WHERE email IS NOT NULL AND deleted_at IS NULL;

CREATE UNIQUE INDEX users_active_provider_subject_uidx
    ON public.users (auth_provider, auth_provider_subject)
    WHERE auth_provider_subject IS NOT NULL AND deleted_at IS NULL;

CREATE INDEX users_created_at_idx ON public.users (created_at DESC);

CREATE TABLE public.revoked_access_tokens (
    jti text PRIMARY KEY,
    user_id uuid NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    expires_at bigint NOT NULL,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT revoked_access_tokens_jti_ck CHECK (
        char_length(jti) BETWEEN 8 AND 255
    )
);

CREATE INDEX revoked_access_tokens_expiry_idx
    ON public.revoked_access_tokens (expires_at);

COMMENT ON COLUMN public.users.password_hash IS
    'Argon2id or equivalent encoded hash only; never expose through API schemas or logs.';

CREATE TABLE public.auth_sessions (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id uuid NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    refresh_token_hash bytea NOT NULL,
    csrf_token_hash bytea,
    user_agent_hash bytea,
    ip_address_hash bytea,
    expires_at timestamptz NOT NULL,
    last_used_at timestamptz,
    revoked_at timestamptz,
    revoke_reason text,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT auth_sessions_refresh_hash_ck CHECK (
        octet_length(refresh_token_hash) >= 32
    ),
    CONSTRAINT auth_sessions_csrf_hash_ck CHECK (
        csrf_token_hash IS NULL OR octet_length(csrf_token_hash) >= 32
    ),
    CONSTRAINT auth_sessions_user_agent_hash_ck CHECK (
        user_agent_hash IS NULL OR octet_length(user_agent_hash) >= 32
    ),
    CONSTRAINT auth_sessions_ip_hash_ck CHECK (
        ip_address_hash IS NULL OR octet_length(ip_address_hash) >= 32
    ),
    CONSTRAINT auth_sessions_expiry_ck CHECK (expires_at > created_at),
    CONSTRAINT auth_sessions_revoke_reason_ck CHECK (
        revoke_reason IS NULL OR char_length(revoke_reason) <= 255
    )
);

CREATE UNIQUE INDEX auth_sessions_refresh_token_uidx
    ON public.auth_sessions (refresh_token_hash);

CREATE INDEX auth_sessions_active_user_idx
    ON public.auth_sessions (user_id, expires_at DESC)
    WHERE revoked_at IS NULL;

-- Dataset, ingestion, and model registries --------------------------------

CREATE TABLE public.ingestion_sources (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    source_key text NOT NULL UNIQUE,
    display_name text NOT NULL,
    base_url text,
    terms_url text,
    rate_limit_per_minute integer,
    is_enabled boolean NOT NULL DEFAULT true,
    configuration jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT ingestion_sources_key_ck CHECK (
        source_key ~ '^[a-z][a-z0-9_-]{1,63}$'
    ),
    CONSTRAINT ingestion_sources_name_ck CHECK (
        char_length(btrim(display_name)) BETWEEN 1 AND 120
    ),
    CONSTRAINT ingestion_sources_base_url_ck CHECK (
        base_url IS NULL OR base_url ~ '^https://'
    ),
    CONSTRAINT ingestion_sources_terms_url_ck CHECK (
        terms_url IS NULL OR terms_url ~ '^https://'
    ),
    CONSTRAINT ingestion_sources_rate_limit_ck CHECK (
        rate_limit_per_minute IS NULL OR rate_limit_per_minute > 0
    ),
    CONSTRAINT ingestion_sources_configuration_ck CHECK (
        jsonb_typeof(configuration) = 'object'
    )
);

CREATE TABLE public.dataset_versions (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    version text NOT NULL UNIQUE,
    status text NOT NULL DEFAULT 'staged',
    parent_version_id uuid REFERENCES public.dataset_versions(id) ON DELETE RESTRICT,
    created_by_user_id uuid REFERENCES public.users(id) ON DELETE SET NULL,
    source_manifest jsonb NOT NULL DEFAULT '{}'::jsonb,
    content_hash text NOT NULL UNIQUE,
    report_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    snapshot_uri text,
    snapshot_sha256 bytea,
    record_count integer NOT NULL DEFAULT 0,
    validated_at timestamptz,
    activated_at timestamptz,
    retired_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT dataset_versions_version_ck CHECK (
        char_length(btrim(version)) BETWEEN 1 AND 100
    ),
    CONSTRAINT dataset_versions_status_ck CHECK (
        status IN ('staged', 'validated', 'active', 'retired', 'failed')
    ),
    CONSTRAINT dataset_versions_content_hash_ck CHECK (
        content_hash ~ '^[0-9A-Fa-f]{64}$'
    ),
    CONSTRAINT dataset_versions_manifest_ck CHECK (
        jsonb_typeof(source_manifest) = 'object'
        AND jsonb_typeof(report_json) = 'object'
    ),
    CONSTRAINT dataset_versions_snapshot_uri_ck CHECK (
        snapshot_uri IS NULL OR snapshot_uri ~ '^(https|s3|gs|az)://'
    ),
    CONSTRAINT dataset_versions_snapshot_hash_ck CHECK (
        snapshot_sha256 IS NULL OR octet_length(snapshot_sha256) = 32
    ),
    CONSTRAINT dataset_versions_record_count_ck CHECK (record_count >= 0),
    CONSTRAINT dataset_versions_active_timestamp_ck CHECK (
        status <> 'active' OR activated_at IS NOT NULL
    ),
    CONSTRAINT dataset_versions_parent_ck CHECK (parent_version_id IS DISTINCT FROM id)
);

CREATE UNIQUE INDEX dataset_versions_one_active_uidx
    ON public.dataset_versions ((1))
    WHERE status = 'active';

CREATE INDEX dataset_versions_created_at_idx
    ON public.dataset_versions (created_at DESC);

CREATE TABLE public.ingestion_runs (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    source_id uuid REFERENCES public.ingestion_sources(id) ON DELETE RESTRICT,
    target_dataset_version_id uuid NOT NULL
        REFERENCES public.dataset_versions(id) ON DELETE RESTRICT,
    previous_dataset_version_id uuid
        REFERENCES public.dataset_versions(id) ON DELETE RESTRICT,
    initiated_by_user_id uuid REFERENCES public.users(id) ON DELETE SET NULL,
    status text NOT NULL DEFAULT 'queued',
    dry_run boolean NOT NULL DEFAULT true,
    transformation_version text NOT NULL,
    source_cursor text,
    attempt_count integer NOT NULL DEFAULT 0,
    staged_count integer NOT NULL DEFAULT 0,
    promoted_count integer NOT NULL DEFAULT 0,
    quarantined_count integer NOT NULL DEFAULT 0,
    skipped_count integer NOT NULL DEFAULT 0,
    error_count integer NOT NULL DEFAULT 0,
    report_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    error_summary jsonb NOT NULL DEFAULT '{}'::jsonb,
    started_at timestamptz,
    completed_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT ingestion_runs_status_ck CHECK (
        status IN ('queued', 'running', 'validated', 'promoted', 'failed', 'cancelled')
    ),
    CONSTRAINT ingestion_runs_transform_version_ck CHECK (
        char_length(btrim(transformation_version)) BETWEEN 1 AND 100
    ),
    CONSTRAINT ingestion_runs_counts_ck CHECK (
        attempt_count >= 0
        AND staged_count >= 0
        AND promoted_count >= 0
        AND quarantined_count >= 0
        AND skipped_count >= 0
        AND error_count >= 0
    ),
    CONSTRAINT ingestion_runs_report_ck CHECK (
        jsonb_typeof(report_json) = 'object'
        AND jsonb_typeof(error_summary) = 'object'
    ),
    CONSTRAINT ingestion_runs_completion_ck CHECK (
        completed_at IS NULL OR started_at IS NULL OR completed_at >= started_at
    ),
    CONSTRAINT ingestion_runs_version_ck CHECK (
        previous_dataset_version_id IS NULL
        OR previous_dataset_version_id <> target_dataset_version_id
    )
);

CREATE INDEX ingestion_runs_status_created_idx
    ON public.ingestion_runs (status, created_at DESC);

CREATE INDEX ingestion_runs_target_dataset_idx
    ON public.ingestion_runs (target_dataset_version_id);

CREATE TABLE public.embedding_model_versions (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    provider text NOT NULL,
    model_name text NOT NULL,
    model_version text NOT NULL,
    dimension integer NOT NULL DEFAULT 384,
    distance_metric text NOT NULL DEFAULT 'cosine',
    normalized boolean NOT NULL DEFAULT true,
    input_template text NOT NULL,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    is_active boolean NOT NULL DEFAULT false,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT embedding_models_provider_ck CHECK (
        char_length(btrim(provider)) BETWEEN 1 AND 100
    ),
    CONSTRAINT embedding_models_name_ck CHECK (
        char_length(btrim(model_name)) BETWEEN 1 AND 255
        AND char_length(btrim(model_version)) BETWEEN 1 AND 100
    ),
    CONSTRAINT embedding_models_dimension_ck CHECK (dimension = 384),
    CONSTRAINT embedding_models_metric_ck CHECK (distance_metric = 'cosine'),
    CONSTRAINT embedding_models_template_ck CHECK (
        char_length(btrim(input_template)) BETWEEN 1 AND 2000
    ),
    CONSTRAINT embedding_models_metadata_ck CHECK (
        jsonb_typeof(metadata) = 'object'
    ),
    UNIQUE (provider, model_name, model_version)
);

CREATE UNIQUE INDEX embedding_models_one_active_uidx
    ON public.embedding_model_versions ((1))
    WHERE is_active;

-- Canonical catalog --------------------------------------------------------

CREATE TABLE public.movies (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    dataset_version_id uuid NOT NULL
        REFERENCES public.dataset_versions(id) ON DELETE RESTRICT,
    canonical_title text NOT NULL,
    original_title text,
    normalized_title text NOT NULL,
    release_year smallint,
    runtime_minutes smallint,
    certificate text,
    overview text NOT NULL,
    language text NOT NULL DEFAULT 'ta',
    poster_url text,
    source_url text,
    source_updated_at timestamptz,
    data_quality_status text NOT NULL DEFAULT 'pending',
    data_quality_confidence numeric(5,4) NOT NULL DEFAULT 0,
    prominence_score numeric(5,4) NOT NULL DEFAULT 0.5,
    searchable_text text NOT NULL DEFAULT '',
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    archived_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    search_document tsvector GENERATED ALWAYS AS (
        setweight(to_tsvector('simple'::regconfig, coalesce(canonical_title, '')), 'A')
        || setweight(to_tsvector('simple'::regconfig, coalesce(original_title, '')), 'A')
        || setweight(to_tsvector('simple'::regconfig, coalesce(searchable_text, '')), 'B')
        || setweight(to_tsvector('simple'::regconfig, coalesce(overview, '')), 'C')
    ) STORED,
    CONSTRAINT movies_canonical_title_ck CHECK (
        char_length(btrim(canonical_title)) BETWEEN 1 AND 500
    ),
    CONSTRAINT movies_original_title_ck CHECK (
        original_title IS NULL OR char_length(btrim(original_title)) BETWEEN 1 AND 500
    ),
    CONSTRAINT movies_normalized_title_ck CHECK (
        char_length(btrim(normalized_title)) BETWEEN 1 AND 500
    ),
    CONSTRAINT movies_release_year_ck CHECK (
        release_year IS NULL OR release_year BETWEEN 1888 AND 2200
    ),
    CONSTRAINT movies_runtime_ck CHECK (
        runtime_minutes IS NULL OR runtime_minutes BETWEEN 1 AND 1440
    ),
    CONSTRAINT movies_certificate_ck CHECK (
        certificate IS NULL OR char_length(btrim(certificate)) BETWEEN 1 AND 40
    ),
    CONSTRAINT movies_overview_ck CHECK (char_length(btrim(overview)) > 0),
    CONSTRAINT movies_language_ck CHECK (
        language ~ '^[A-Za-z]{2,8}([_-][A-Za-z0-9]{2,8})*$'
    ),
    CONSTRAINT movies_poster_url_ck CHECK (
        poster_url IS NULL OR poster_url ~ '^https://'
    ),
    CONSTRAINT movies_source_url_ck CHECK (
        source_url IS NULL OR source_url ~ '^https://'
    ),
    CONSTRAINT movies_quality_status_ck CHECK (
        data_quality_status IN ('pending', 'validated', 'quarantined', 'rejected')
    ),
    CONSTRAINT movies_quality_confidence_ck CHECK (
        data_quality_confidence BETWEEN 0 AND 1
    ),
    CONSTRAINT movies_prominence_ck CHECK (prominence_score BETWEEN 0 AND 1),
    CONSTRAINT movies_metadata_ck CHECK (jsonb_typeof(metadata) = 'object')
);

CREATE UNIQUE INDEX movies_identity_uidx
    ON public.movies (normalized_title, release_year, language)
    WHERE release_year IS NOT NULL AND archived_at IS NULL;

CREATE INDEX movies_search_document_gin_idx
    ON public.movies USING gin (search_document);

CREATE INDEX movies_title_trgm_idx
    ON public.movies USING gin (normalized_title gin_trgm_ops);

CREATE INDEX movies_discovery_idx
    ON public.movies (data_quality_status, language, release_year DESC, prominence_score DESC)
    WHERE archived_at IS NULL;

CREATE INDEX movies_dataset_version_idx ON public.movies (dataset_version_id);

CREATE TABLE public.movie_external_ids (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    movie_id uuid NOT NULL REFERENCES public.movies(id) ON DELETE CASCADE,
    source_system text NOT NULL,
    external_identifier text NOT NULL,
    source_url text,
    retrieved_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT movie_external_ids_source_ck CHECK (
        source_system ~ '^[a-z][a-z0-9_-]{1,63}$'
    ),
    CONSTRAINT movie_external_ids_identifier_ck CHECK (
        char_length(btrim(external_identifier)) BETWEEN 1 AND 255
    ),
    CONSTRAINT movie_external_ids_url_ck CHECK (
        source_url IS NULL OR source_url ~ '^https://'
    ),
    UNIQUE (source_system, external_identifier),
    UNIQUE (movie_id, source_system, external_identifier)
);

CREATE INDEX movie_external_ids_movie_idx
    ON public.movie_external_ids (movie_id);

CREATE TABLE public.movie_aliases (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    movie_id uuid NOT NULL REFERENCES public.movies(id) ON DELETE CASCADE,
    alias text NOT NULL,
    normalized_alias text NOT NULL,
    locale text NOT NULL DEFAULT 'ta',
    alias_type text NOT NULL DEFAULT 'alternate',
    is_searchable boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT movie_aliases_alias_ck CHECK (
        char_length(btrim(alias)) BETWEEN 1 AND 500
        AND char_length(btrim(normalized_alias)) BETWEEN 1 AND 500
    ),
    CONSTRAINT movie_aliases_locale_ck CHECK (
        locale ~ '^[A-Za-z]{2,8}([_-][A-Za-z0-9]{2,8})*$'
    ),
    CONSTRAINT movie_aliases_type_ck CHECK (
        alias_type IN ('original', 'transliteration', 'alternate', 'search', 'known_misspelling')
    ),
    UNIQUE (movie_id, normalized_alias, locale)
);

CREATE INDEX movie_aliases_lookup_trgm_idx
    ON public.movie_aliases USING gin (normalized_alias gin_trgm_ops)
    WHERE is_searchable;

CREATE TABLE public.movie_field_provenance (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    movie_id uuid NOT NULL REFERENCES public.movies(id) ON DELETE CASCADE,
    ingestion_run_id uuid REFERENCES public.ingestion_runs(id) ON DELETE SET NULL,
    field_name text NOT NULL,
    source_system text NOT NULL,
    source_identifier text,
    source_url text,
    retrieved_at timestamptz NOT NULL,
    transformation_version text NOT NULL,
    confidence numeric(5,4),
    value_sha256 bytea,
    source_value jsonb,
    is_selected boolean NOT NULL DEFAULT false,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT movie_provenance_field_ck CHECK (
        field_name ~ '^[a-z][a-z0-9_]{0,63}$'
    ),
    CONSTRAINT movie_provenance_source_ck CHECK (
        source_system ~ '^[a-z][a-z0-9_-]{1,63}$'
    ),
    CONSTRAINT movie_provenance_url_ck CHECK (
        source_url IS NULL OR source_url ~ '^https://'
    ),
    CONSTRAINT movie_provenance_transform_ck CHECK (
        char_length(btrim(transformation_version)) BETWEEN 1 AND 100
    ),
    CONSTRAINT movie_provenance_confidence_ck CHECK (
        confidence IS NULL OR confidence BETWEEN 0 AND 1
    ),
    CONSTRAINT movie_provenance_value_hash_ck CHECK (
        value_sha256 IS NULL OR octet_length(value_sha256) = 32
    )
);

CREATE UNIQUE INDEX movie_provenance_selected_field_uidx
    ON public.movie_field_provenance (movie_id, field_name)
    WHERE is_selected;

CREATE INDEX movie_provenance_source_idx
    ON public.movie_field_provenance (source_system, source_identifier);

CREATE TABLE public.people (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name text NOT NULL,
    normalized_name text NOT NULL,
    biography text,
    source_url text,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT people_name_ck CHECK (
        char_length(btrim(name)) BETWEEN 1 AND 300
        AND char_length(btrim(normalized_name)) BETWEEN 1 AND 300
    ),
    CONSTRAINT people_source_url_ck CHECK (
        source_url IS NULL OR source_url ~ '^https://'
    ),
    CONSTRAINT people_metadata_ck CHECK (jsonb_typeof(metadata) = 'object')
);

CREATE INDEX people_normalized_name_idx ON public.people (normalized_name);
CREATE INDEX people_name_trgm_idx
    ON public.people USING gin (normalized_name gin_trgm_ops);

CREATE TABLE public.person_external_ids (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    person_id uuid NOT NULL REFERENCES public.people(id) ON DELETE CASCADE,
    source_system text NOT NULL,
    external_identifier text NOT NULL,
    source_url text,
    retrieved_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT person_external_ids_source_ck CHECK (
        source_system ~ '^[a-z][a-z0-9_-]{1,63}$'
    ),
    CONSTRAINT person_external_ids_identifier_ck CHECK (
        char_length(btrim(external_identifier)) BETWEEN 1 AND 255
    ),
    CONSTRAINT person_external_ids_url_ck CHECK (
        source_url IS NULL OR source_url ~ '^https://'
    ),
    UNIQUE (source_system, external_identifier),
    UNIQUE (person_id, source_system, external_identifier)
);

CREATE TABLE public.person_aliases (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    person_id uuid NOT NULL REFERENCES public.people(id) ON DELETE CASCADE,
    alias text NOT NULL,
    normalized_alias text NOT NULL,
    locale text NOT NULL DEFAULT 'ta',
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT person_aliases_name_ck CHECK (
        char_length(btrim(alias)) BETWEEN 1 AND 300
        AND char_length(btrim(normalized_alias)) BETWEEN 1 AND 300
    ),
    CONSTRAINT person_aliases_locale_ck CHECK (
        locale ~ '^[A-Za-z]{2,8}([_-][A-Za-z0-9]{2,8})*$'
    ),
    UNIQUE (person_id, normalized_alias, locale)
);

CREATE INDEX person_aliases_lookup_trgm_idx
    ON public.person_aliases USING gin (normalized_alias gin_trgm_ops);

CREATE TABLE public.person_field_provenance (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    person_id uuid NOT NULL REFERENCES public.people(id) ON DELETE CASCADE,
    ingestion_run_id uuid REFERENCES public.ingestion_runs(id) ON DELETE SET NULL,
    field_name text NOT NULL,
    source_system text NOT NULL,
    source_identifier text,
    source_url text,
    retrieved_at timestamptz NOT NULL,
    transformation_version text NOT NULL,
    confidence numeric(5,4),
    value_sha256 bytea,
    source_value jsonb,
    is_selected boolean NOT NULL DEFAULT false,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT person_provenance_field_ck CHECK (
        field_name ~ '^[a-z][a-z0-9_]{0,63}$'
    ),
    CONSTRAINT person_provenance_source_ck CHECK (
        source_system ~ '^[a-z][a-z0-9_-]{1,63}$'
    ),
    CONSTRAINT person_provenance_url_ck CHECK (
        source_url IS NULL OR source_url ~ '^https://'
    ),
    CONSTRAINT person_provenance_transform_ck CHECK (
        char_length(btrim(transformation_version)) BETWEEN 1 AND 100
    ),
    CONSTRAINT person_provenance_confidence_ck CHECK (
        confidence IS NULL OR confidence BETWEEN 0 AND 1
    ),
    CONSTRAINT person_provenance_value_hash_ck CHECK (
        value_sha256 IS NULL OR octet_length(value_sha256) = 32
    )
);

CREATE UNIQUE INDEX person_provenance_selected_field_uidx
    ON public.person_field_provenance (person_id, field_name)
    WHERE is_selected;

CREATE INDEX person_provenance_source_idx
    ON public.person_field_provenance (source_system, source_identifier);

CREATE TABLE public.movie_credits (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    movie_id uuid NOT NULL REFERENCES public.movies(id) ON DELETE CASCADE,
    person_id uuid NOT NULL REFERENCES public.people(id) ON DELETE RESTRICT,
    role_type text NOT NULL,
    character_name text,
    billing_order integer,
    provenance_id uuid REFERENCES public.movie_field_provenance(id) ON DELETE SET NULL,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT movie_credits_role_ck CHECK (
        role_type IN (
            'actor', 'director', 'writer', 'producer', 'music',
            'cinematography', 'editor', 'other'
        )
    ),
    CONSTRAINT movie_credits_character_ck CHECK (
        character_name IS NULL OR char_length(btrim(character_name)) BETWEEN 1 AND 300
    ),
    CONSTRAINT movie_credits_billing_ck CHECK (
        billing_order IS NULL OR billing_order >= 0
    )
);

CREATE UNIQUE INDEX movie_credits_identity_uidx
    ON public.movie_credits (
        movie_id,
        person_id,
        role_type,
        (coalesce(character_name, ''))
    );

CREATE INDEX movie_credits_person_role_idx
    ON public.movie_credits (person_id, role_type, movie_id);

CREATE INDEX movie_credits_movie_role_idx
    ON public.movie_credits (movie_id, role_type, billing_order);

CREATE TABLE public.genres (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    slug text NOT NULL UNIQUE,
    display_name text NOT NULL,
    description text NOT NULL DEFAULT '',
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT genres_slug_ck CHECK (slug ~ '^[a-z0-9]+(?:-[a-z0-9]+)*$'),
    CONSTRAINT genres_name_ck CHECK (
        char_length(btrim(display_name)) BETWEEN 1 AND 100
    )
);

CREATE TABLE public.themes (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    slug text NOT NULL UNIQUE,
    display_name text NOT NULL,
    description text,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT themes_slug_ck CHECK (slug ~ '^[a-z0-9]+(?:-[a-z0-9]+)*$'),
    CONSTRAINT themes_name_ck CHECK (
        char_length(btrim(display_name)) BETWEEN 1 AND 120
    )
);

CREATE TABLE public.movie_genres (
    movie_id uuid NOT NULL REFERENCES public.movies(id) ON DELETE CASCADE,
    genre_id uuid NOT NULL REFERENCES public.genres(id) ON DELETE RESTRICT,
    confidence numeric(5,4) NOT NULL DEFAULT 1,
    provenance_id uuid REFERENCES public.movie_field_provenance(id) ON DELETE SET NULL,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (movie_id, genre_id),
    CONSTRAINT movie_genres_confidence_ck CHECK (confidence BETWEEN 0 AND 1)
);

CREATE INDEX movie_genres_genre_movie_idx
    ON public.movie_genres (genre_id, movie_id);

CREATE TABLE public.movie_themes (
    movie_id uuid NOT NULL REFERENCES public.movies(id) ON DELETE CASCADE,
    theme_id uuid NOT NULL REFERENCES public.themes(id) ON DELETE RESTRICT,
    confidence numeric(5,4) NOT NULL,
    is_generated boolean NOT NULL DEFAULT false,
    provenance_id uuid REFERENCES public.movie_field_provenance(id) ON DELETE SET NULL,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (movie_id, theme_id),
    CONSTRAINT movie_themes_confidence_ck CHECK (confidence BETWEEN 0 AND 1)
);

CREATE INDEX movie_themes_theme_movie_idx
    ON public.movie_themes (theme_id, movie_id);

CREATE TABLE public.movie_embeddings (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    movie_id uuid NOT NULL REFERENCES public.movies(id) ON DELETE CASCADE,
    model_version_id uuid NOT NULL
        REFERENCES public.embedding_model_versions(id) ON DELETE RESTRICT,
    dataset_version_id uuid NOT NULL
        REFERENCES public.dataset_versions(id) ON DELETE RESTRICT,
    content_sha256 bytea NOT NULL,
    embedding vector(384) NOT NULL,
    is_active boolean NOT NULL DEFAULT false,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT movie_embeddings_content_hash_ck CHECK (
        octet_length(content_sha256) = 32
    ),
    CONSTRAINT movie_embeddings_vector_ck CHECK (
        vector_dims(embedding) = 384 AND vector_norm(embedding) > 0
    ),
    UNIQUE (movie_id, model_version_id, content_sha256)
);

CREATE UNIQUE INDEX movie_embeddings_one_active_per_movie_uidx
    ON public.movie_embeddings (movie_id)
    WHERE is_active;

CREATE INDEX movie_embeddings_active_model_idx
    ON public.movie_embeddings (model_version_id, movie_id)
    WHERE is_active;

CREATE INDEX movie_embeddings_active_hnsw_idx
    ON public.movie_embeddings
    USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64)
    WHERE is_active;

COMMENT ON COLUMN public.movie_embeddings.embedding IS
    '384-dimensional active retrieval vector; changing dimensions requires an additive migration and atomic reindex.';

-- Ingestion staging, quarantine, and quality reporting ---------------------

CREATE TABLE public.staged_movie_records (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    ingestion_run_id uuid NOT NULL REFERENCES public.ingestion_runs(id) ON DELETE CASCADE,
    source_record_id text NOT NULL,
    raw_payload jsonb NOT NULL,
    normalized_payload jsonb,
    matched_movie_id uuid REFERENCES public.movies(id) ON DELETE SET NULL,
    identity_status text NOT NULL DEFAULT 'unmatched',
    identity_confidence numeric(5,4),
    validation_status text NOT NULL DEFAULT 'pending',
    validation_errors jsonb NOT NULL DEFAULT '[]'::jsonb,
    content_sha256 bytea,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT staged_movies_source_record_ck CHECK (
        char_length(btrim(source_record_id)) BETWEEN 1 AND 500
    ),
    CONSTRAINT staged_movies_payload_ck CHECK (
        jsonb_typeof(raw_payload) = 'object'
        AND (normalized_payload IS NULL OR jsonb_typeof(normalized_payload) = 'object')
    ),
    CONSTRAINT staged_movies_identity_status_ck CHECK (
        identity_status IN ('unmatched', 'matched', 'ambiguous', 'new', 'rejected')
    ),
    CONSTRAINT staged_movies_identity_confidence_ck CHECK (
        identity_confidence IS NULL OR identity_confidence BETWEEN 0 AND 1
    ),
    CONSTRAINT staged_movies_validation_status_ck CHECK (
        validation_status IN ('pending', 'valid', 'invalid', 'quarantined')
    ),
    CONSTRAINT staged_movies_validation_errors_ck CHECK (
        jsonb_typeof(validation_errors) = 'array'
    ),
    CONSTRAINT staged_movies_content_hash_ck CHECK (
        content_sha256 IS NULL OR octet_length(content_sha256) = 32
    ),
    UNIQUE (ingestion_run_id, source_record_id)
);

CREATE INDEX staged_movies_run_validation_idx
    ON public.staged_movie_records (ingestion_run_id, validation_status, identity_status);

CREATE INDEX staged_movies_matched_movie_idx
    ON public.staged_movie_records (matched_movie_id)
    WHERE matched_movie_id IS NOT NULL;

CREATE TABLE public.quarantine_records (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    staged_record_id uuid NOT NULL
        REFERENCES public.staged_movie_records(id) ON DELETE CASCADE,
    reason_code text NOT NULL,
    reason_detail text NOT NULL,
    evidence jsonb NOT NULL DEFAULT '{}'::jsonb,
    status text NOT NULL DEFAULT 'open',
    resolution_action text,
    reviewed_by_user_id uuid REFERENCES public.users(id) ON DELETE SET NULL,
    reviewed_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT quarantine_reason_code_ck CHECK (
        reason_code ~ '^[a-z][a-z0-9_]{1,63}$'
    ),
    CONSTRAINT quarantine_reason_detail_ck CHECK (
        char_length(btrim(reason_detail)) BETWEEN 1 AND 4000
    ),
    CONSTRAINT quarantine_evidence_ck CHECK (jsonb_typeof(evidence) = 'object'),
    CONSTRAINT quarantine_status_ck CHECK (
        status IN ('open', 'approved', 'rejected', 'resolved')
    ),
    CONSTRAINT quarantine_resolution_ck CHECK (
        resolution_action IS NULL OR char_length(resolution_action) <= 2000
    )
);

CREATE INDEX quarantine_open_records_idx
    ON public.quarantine_records (created_at DESC)
    WHERE status = 'open';

CREATE TABLE public.data_quality_reports (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    ingestion_run_id uuid NOT NULL REFERENCES public.ingestion_runs(id) ON DELETE CASCADE,
    dataset_version_id uuid NOT NULL REFERENCES public.dataset_versions(id) ON DELETE RESTRICT,
    report_version text NOT NULL,
    passed boolean NOT NULL,
    metrics jsonb NOT NULL,
    report_uri text,
    report_sha256 bytea,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT quality_reports_version_ck CHECK (
        char_length(btrim(report_version)) BETWEEN 1 AND 100
    ),
    CONSTRAINT quality_reports_metrics_ck CHECK (jsonb_typeof(metrics) = 'object'),
    CONSTRAINT quality_reports_uri_ck CHECK (
        report_uri IS NULL OR report_uri ~ '^(https|s3|gs|az)://'
    ),
    CONSTRAINT quality_reports_hash_ck CHECK (
        report_sha256 IS NULL OR octet_length(report_sha256) = 32
    ),
    UNIQUE (ingestion_run_id, report_version)
);

CREATE TABLE public.movie_quality_issues (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    movie_id uuid REFERENCES public.movies(id) ON DELETE CASCADE,
    ingestion_run_id uuid REFERENCES public.ingestion_runs(id) ON DELETE SET NULL,
    issue_code text NOT NULL,
    field_name text,
    severity text NOT NULL,
    detail text NOT NULL,
    evidence jsonb NOT NULL DEFAULT '{}'::jsonb,
    status text NOT NULL DEFAULT 'open',
    resolved_by_user_id uuid REFERENCES public.users(id) ON DELETE SET NULL,
    resolved_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT quality_issues_subject_ck CHECK (
        movie_id IS NOT NULL OR ingestion_run_id IS NOT NULL
    ),
    CONSTRAINT quality_issues_code_ck CHECK (
        issue_code ~ '^[a-z][a-z0-9_]{1,63}$'
    ),
    CONSTRAINT quality_issues_field_ck CHECK (
        field_name IS NULL OR field_name ~ '^[a-z][a-z0-9_]{0,63}$'
    ),
    CONSTRAINT quality_issues_severity_ck CHECK (
        severity IN ('info', 'warning', 'error', 'critical')
    ),
    CONSTRAINT quality_issues_detail_ck CHECK (
        char_length(btrim(detail)) BETWEEN 1 AND 4000
    ),
    CONSTRAINT quality_issues_evidence_ck CHECK (jsonb_typeof(evidence) = 'object'),
    CONSTRAINT quality_issues_status_ck CHECK (
        status IN ('open', 'accepted', 'fixed', 'false_positive')
    )
);

CREATE INDEX movie_quality_open_idx
    ON public.movie_quality_issues (severity, created_at DESC)
    WHERE status = 'open';

CREATE INDEX movie_quality_movie_idx
    ON public.movie_quality_issues (movie_id, status)
    WHERE movie_id IS NOT NULL;

-- Ranking configuration and retrieval telemetry ---------------------------

CREATE TABLE public.ranking_configs (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    version text NOT NULL UNIQUE,
    dataset_version_id uuid NOT NULL
        REFERENCES public.dataset_versions(id) ON DELETE RESTRICT,
    embedding_model_version_id uuid NOT NULL
        REFERENCES public.embedding_model_versions(id) ON DELETE RESTRICT,
    algorithm text NOT NULL DEFAULT 'rrf',
    weights jsonb NOT NULL,
    config_sha256 bytea NOT NULL,
    code_commit text,
    is_default boolean NOT NULL DEFAULT false,
    created_by_user_id uuid REFERENCES public.users(id) ON DELETE SET NULL,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT ranking_configs_version_ck CHECK (
        char_length(btrim(version)) BETWEEN 1 AND 120
    ),
    CONSTRAINT ranking_configs_algorithm_ck CHECK (
        algorithm IN ('weighted', 'rrf', 'learning_to_rank')
    ),
    CONSTRAINT ranking_configs_weights_ck CHECK (jsonb_typeof(weights) = 'object'),
    CONSTRAINT ranking_configs_hash_ck CHECK (octet_length(config_sha256) = 32),
    CONSTRAINT ranking_configs_commit_ck CHECK (
        code_commit IS NULL OR code_commit ~ '^[0-9A-Fa-f]{7,64}$'
    )
);

CREATE UNIQUE INDEX ranking_configs_one_default_uidx
    ON public.ranking_configs ((1))
    WHERE is_default;

CREATE TABLE public.search_events (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    request_id uuid NOT NULL UNIQUE,
    user_id uuid REFERENCES public.users(id) ON DELETE CASCADE,
    anonymous_session_hash bytea,
    query_text text,
    normalized_query text,
    detected_language text,
    search_mode text NOT NULL DEFAULT 'query',
    filters jsonb NOT NULL DEFAULT '{}'::jsonb,
    sort_mode text NOT NULL DEFAULT 'relevance',
    ranking_config_id uuid NOT NULL REFERENCES public.ranking_configs(id) ON DELETE RESTRICT,
    status text NOT NULL DEFAULT 'success',
    error_code text,
    result_count integer NOT NULL DEFAULT 0,
    latency_ms integer NOT NULL,
    analytics_consent boolean NOT NULL DEFAULT false,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT search_events_identity_ck CHECK (
        user_id IS NULL OR anonymous_session_hash IS NULL
    ),
    CONSTRAINT search_events_session_hash_ck CHECK (
        anonymous_session_hash IS NULL OR octet_length(anonymous_session_hash) >= 32
    ),
    CONSTRAINT search_events_query_ck CHECK (
        query_text IS NULL OR char_length(query_text) <= 500
    ),
    CONSTRAINT search_events_normalized_query_ck CHECK (
        normalized_query IS NULL OR char_length(normalized_query) <= 1000
    ),
    CONSTRAINT search_events_language_ck CHECK (
        detected_language IS NULL
        OR detected_language ~ '^[A-Za-z]{2,8}([_-][A-Za-z0-9]{2,8})*$'
    ),
    CONSTRAINT search_events_mode_ck CHECK (
        search_mode IN ('query', 'empty_discovery')
    ),
    CONSTRAINT search_events_filters_ck CHECK (jsonb_typeof(filters) = 'object'),
    CONSTRAINT search_events_sort_ck CHECK (
        sort_mode IN ('relevance', 'release_year', 'popularity', 'hidden_gem')
    ),
    CONSTRAINT search_events_status_ck CHECK (
        status IN ('success', 'validation_error', 'error')
    ),
    CONSTRAINT search_events_counts_ck CHECK (result_count >= 0 AND latency_ms >= 0),
    CONSTRAINT search_events_consent_ck CHECK (
        analytics_consent OR (query_text IS NULL AND normalized_query IS NULL)
    )
);

CREATE INDEX search_events_user_history_idx
    ON public.search_events (user_id, created_at DESC)
    WHERE user_id IS NOT NULL;

CREATE INDEX search_events_ranking_latency_idx
    ON public.search_events (ranking_config_id, created_at DESC, latency_ms);

CREATE INDEX search_events_created_at_idx
    ON public.search_events (created_at DESC);

CREATE TABLE public.search_event_results (
    search_event_id uuid NOT NULL REFERENCES public.search_events(id) ON DELETE CASCADE,
    position integer NOT NULL,
    movie_id uuid NOT NULL REFERENCES public.movies(id) ON DELETE RESTRICT,
    semantic_score double precision,
    lexical_score double precision,
    fused_score double precision,
    personalization_score double precision,
    quality_score double precision,
    diversity_penalty double precision,
    final_score double precision NOT NULL,
    component_scores jsonb NOT NULL DEFAULT '{}'::jsonb,
    explanation_evidence jsonb NOT NULL DEFAULT '[]'::jsonb,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (search_event_id, position),
    CONSTRAINT search_results_position_ck CHECK (position > 0),
    CONSTRAINT search_results_component_scores_ck CHECK (
        jsonb_typeof(component_scores) = 'object'
    ),
    CONSTRAINT search_results_evidence_ck CHECK (
        jsonb_typeof(explanation_evidence) = 'array'
    ),
    CONSTRAINT search_results_finite_scores_ck CHECK (
        (semantic_score IS NULL OR public.tamiltrove_is_finite(semantic_score))
        AND (lexical_score IS NULL OR public.tamiltrove_is_finite(lexical_score))
        AND (fused_score IS NULL OR public.tamiltrove_is_finite(fused_score))
        AND (
            personalization_score IS NULL
            OR public.tamiltrove_is_finite(personalization_score)
        )
        AND (quality_score IS NULL OR public.tamiltrove_is_finite(quality_score))
        AND (
            diversity_penalty IS NULL
            OR public.tamiltrove_is_finite(diversity_penalty)
        )
        AND public.tamiltrove_is_finite(final_score)
    ),
    UNIQUE (search_event_id, movie_id)
);

CREATE INDEX search_results_movie_idx
    ON public.search_event_results (movie_id, created_at DESC);

-- User-visible history is separate from operational search telemetry. It is
-- written only when the user's privacy_json.store_search_history setting is on
-- and is deleted with the account or through the profile history controls.
CREATE TABLE public.search_history (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id uuid NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    query_text text NOT NULL,
    normalized_query text NOT NULL,
    detected_language text NOT NULL,
    filters_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    result_ids_json jsonb NOT NULL DEFAULT '[]'::jsonb,
    ranking_version text NOT NULL,
    latency_ms double precision NOT NULL,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT search_history_query_ck CHECK (char_length(query_text) <= 500),
    CONSTRAINT search_history_normalized_query_ck CHECK (
        char_length(normalized_query) <= 1000
    ),
    CONSTRAINT search_history_language_ck CHECK (
        char_length(btrim(detected_language)) BETWEEN 2 AND 32
    ),
    CONSTRAINT search_history_filters_ck CHECK (jsonb_typeof(filters_json) = 'object'),
    CONSTRAINT search_history_results_ck CHECK (jsonb_typeof(result_ids_json) = 'array'),
    CONSTRAINT search_history_ranking_version_ck CHECK (
        char_length(btrim(ranking_version)) BETWEEN 1 AND 120
    ),
    CONSTRAINT search_history_latency_ck CHECK (
        latency_ms >= 0 AND public.tamiltrove_is_finite(latency_ms)
    )
);

CREATE INDEX search_history_user_created_idx
    ON public.search_history (user_id, created_at DESC);

CREATE TABLE public.recommendation_events (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    request_id uuid NOT NULL UNIQUE,
    user_id uuid NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    surface text NOT NULL,
    ranking_config_id uuid NOT NULL REFERENCES public.ranking_configs(id) ON DELETE RESTRICT,
    source_movie_id uuid REFERENCES public.movies(id) ON DELETE SET NULL,
    context jsonb NOT NULL DEFAULT '{}'::jsonb,
    result_count integer NOT NULL DEFAULT 0,
    latency_ms integer NOT NULL,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT recommendation_events_surface_ck CHECK (
        surface IN (
            'for_you', 'because_you_liked', 'similar', 'theme',
            'hidden_gems', 'recently_added', 'cold_start'
        )
    ),
    CONSTRAINT recommendation_events_context_ck CHECK (jsonb_typeof(context) = 'object'),
    CONSTRAINT recommendation_events_counts_ck CHECK (
        result_count >= 0 AND latency_ms >= 0
    ),
    UNIQUE (id, user_id)
);

CREATE INDEX recommendation_events_user_history_idx
    ON public.recommendation_events (user_id, created_at DESC);

CREATE TABLE public.recommendation_event_results (
    recommendation_event_id uuid NOT NULL,
    user_id uuid NOT NULL,
    position integer NOT NULL,
    movie_id uuid NOT NULL REFERENCES public.movies(id) ON DELETE RESTRICT,
    final_score double precision NOT NULL,
    component_scores jsonb NOT NULL DEFAULT '{}'::jsonb,
    explanation_evidence jsonb NOT NULL DEFAULT '[]'::jsonb,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (recommendation_event_id, position),
    CONSTRAINT recommendation_results_event_owner_fk
        FOREIGN KEY (recommendation_event_id, user_id)
        REFERENCES public.recommendation_events(id, user_id)
        ON DELETE CASCADE,
    CONSTRAINT recommendation_results_position_ck CHECK (position > 0),
    CONSTRAINT recommendation_results_final_score_ck CHECK (
        public.tamiltrove_is_finite(final_score)
    ),
    CONSTRAINT recommendation_results_component_scores_ck CHECK (
        jsonb_typeof(component_scores) = 'object'
    ),
    CONSTRAINT recommendation_results_evidence_ck CHECK (
        jsonb_typeof(explanation_evidence) = 'array'
    ),
    UNIQUE (recommendation_event_id, movie_id)
);

CREATE INDEX recommendation_results_user_movie_idx
    ON public.recommendation_event_results (user_id, movie_id, created_at DESC);

-- Preferences, interactions, and current user/movie state -----------------

CREATE TABLE public.user_preferences (
    user_id uuid PRIMARY KEY REFERENCES public.users(id) ON DELETE CASCADE,
    preferred_era_start smallint,
    preferred_era_end smallint,
    hidden_gem_weight numeric(5,4) NOT NULL DEFAULT 0.5,
    preferred_languages text[] NOT NULL DEFAULT ARRAY['ta']::text[],
    dubbing_tolerance boolean NOT NULL DEFAULT false,
    excluded_certificates text[] NOT NULL DEFAULT ARRAY[]::text[],
    personalization_enabled boolean NOT NULL DEFAULT true,
    settings jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT user_preferences_era_ck CHECK (
        (preferred_era_start IS NULL OR preferred_era_start BETWEEN 1888 AND 2200)
        AND (preferred_era_end IS NULL OR preferred_era_end BETWEEN 1888 AND 2200)
        AND (
            preferred_era_start IS NULL
            OR preferred_era_end IS NULL
            OR preferred_era_start <= preferred_era_end
        )
    ),
    CONSTRAINT user_preferences_hidden_gem_ck CHECK (hidden_gem_weight BETWEEN 0 AND 1),
    CONSTRAINT user_preferences_languages_ck CHECK (
        cardinality(preferred_languages) BETWEEN 1 AND 20
    ),
    CONSTRAINT user_preferences_certificates_ck CHECK (
        cardinality(excluded_certificates) <= 50
    ),
    CONSTRAINT user_preferences_settings_ck CHECK (jsonb_typeof(settings) = 'object')
);

CREATE TABLE public.user_preferred_genres (
    user_id uuid NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    genre_id uuid NOT NULL REFERENCES public.genres(id) ON DELETE CASCADE,
    weight numeric(5,4) NOT NULL DEFAULT 1,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (user_id, genre_id),
    CONSTRAINT user_preferred_genres_weight_ck CHECK (weight BETWEEN 0 AND 1)
);

CREATE TABLE public.user_preferred_themes (
    user_id uuid NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    theme_id uuid NOT NULL REFERENCES public.themes(id) ON DELETE CASCADE,
    weight numeric(5,4) NOT NULL DEFAULT 1,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (user_id, theme_id),
    CONSTRAINT user_preferred_themes_weight_ck CHECK (weight BETWEEN 0 AND 1)
);

CREATE TABLE public.user_profile_embeddings (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id uuid NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    model_version_id uuid NOT NULL
        REFERENCES public.embedding_model_versions(id) ON DELETE RESTRICT,
    profile_sha256 bytea NOT NULL,
    embedding vector(384) NOT NULL,
    signal_count integer NOT NULL,
    is_active boolean NOT NULL DEFAULT false,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT user_embeddings_profile_hash_ck CHECK (
        octet_length(profile_sha256) = 32
    ),
    CONSTRAINT user_embeddings_vector_ck CHECK (
        vector_dims(embedding) = 384 AND vector_norm(embedding) > 0
    ),
    CONSTRAINT user_embeddings_signal_count_ck CHECK (signal_count > 0),
    UNIQUE (user_id, model_version_id, profile_sha256)
);

CREATE UNIQUE INDEX user_embeddings_one_active_per_user_uidx
    ON public.user_profile_embeddings (user_id)
    WHERE is_active;

CREATE TABLE public.user_interactions (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id uuid NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    movie_id uuid NOT NULL REFERENCES public.movies(id) ON DELETE RESTRICT,
    interaction_type text NOT NULL,
    value numeric(10,4),
    search_event_id uuid REFERENCES public.search_events(id) ON DELETE SET NULL,
    recommendation_event_id uuid REFERENCES public.recommendation_events(id) ON DELETE SET NULL,
    context_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    idempotency_key text,
    occurred_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT user_interactions_type_ck CHECK (
        interaction_type IN (
            'impression', 'click', 'save', 'unsave', 'rating', 'like',
            'dislike', 'dismiss', 'undismiss', 'viewed'
        )
    ),
    CONSTRAINT user_interactions_numeric_value_ck CHECK (
        value IS NULL
        OR (
            value > '-Infinity'::numeric
            AND value < 'Infinity'::numeric
        )
    ),
    CONSTRAINT user_interactions_rating_ck CHECK (
        interaction_type <> 'rating'
        OR (value IS NOT NULL AND value BETWEEN 1 AND 5)
    ),
    CONSTRAINT user_interactions_context_source_ck CHECK (
        num_nonnulls(search_event_id, recommendation_event_id) <= 1
    ),
    CONSTRAINT user_interactions_context_ck CHECK (jsonb_typeof(context_json) = 'object'),
    CONSTRAINT user_interactions_idempotency_ck CHECK (
        idempotency_key IS NULL OR char_length(idempotency_key) BETWEEN 8 AND 255
    )
);

CREATE UNIQUE INDEX user_interactions_idempotency_uidx
    ON public.user_interactions (user_id, idempotency_key)
    WHERE idempotency_key IS NOT NULL;

CREATE INDEX user_interactions_profile_idx
    ON public.user_interactions (user_id, occurred_at DESC);

CREATE INDEX user_interactions_user_movie_idx
    ON public.user_interactions (user_id, movie_id, occurred_at DESC);

CREATE INDEX user_interactions_movie_type_idx
    ON public.user_interactions (movie_id, interaction_type, occurred_at DESC);

CREATE TABLE public.user_movie_states (
    user_id uuid NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    movie_id uuid NOT NULL REFERENCES public.movies(id) ON DELETE CASCADE,
    is_saved boolean NOT NULL DEFAULT false,
    like_state smallint NOT NULL DEFAULT 0,
    is_dismissed boolean NOT NULL DEFAULT false,
    is_viewed boolean NOT NULL DEFAULT false,
    rating numeric(2,1),
    saved_at timestamptz,
    rated_at timestamptz,
    dismissed_at timestamptz,
    viewed_at timestamptz,
    last_interaction_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (user_id, movie_id),
    CONSTRAINT user_movie_states_like_ck CHECK (like_state BETWEEN -1 AND 1),
    CONSTRAINT user_movie_states_rating_ck CHECK (
        rating IS NULL OR rating BETWEEN 1 AND 5
    )
);

CREATE INDEX user_movie_states_watchlist_idx
    ON public.user_movie_states (user_id, saved_at DESC)
    WHERE is_saved;

CREATE INDEX user_movie_states_dismissed_idx
    ON public.user_movie_states (user_id, dismissed_at DESC)
    WHERE is_dismissed;

CREATE INDEX user_movie_states_rated_idx
    ON public.user_movie_states (user_id, rated_at DESC)
    WHERE rating IS NOT NULL;

-- User-owned and shareable collections ------------------------------------

CREATE TABLE public.collections (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id uuid NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    name text NOT NULL,
    description text,
    visibility text NOT NULL DEFAULT 'private',
    share_token text,
    cover_movie_id uuid REFERENCES public.movies(id) ON DELETE SET NULL,
    deleted_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT collections_name_ck CHECK (
        char_length(btrim(name)) BETWEEN 1 AND 120
    ),
    CONSTRAINT collections_description_ck CHECK (char_length(description) <= 5000),
    CONSTRAINT collections_visibility_ck CHECK (
        visibility IN ('private', 'unlisted', 'public')
    ),
    CONSTRAINT collections_share_token_ck CHECK (
        share_token IS NULL OR share_token ~ '^[A-Za-z0-9_-]{24,255}$'
    ),
    UNIQUE (id, owner_id)
);

CREATE UNIQUE INDEX collections_share_token_uidx
    ON public.collections (share_token)
    WHERE share_token IS NOT NULL AND deleted_at IS NULL;

CREATE INDEX collections_owner_updated_idx
    ON public.collections (owner_id, updated_at DESC)
    WHERE deleted_at IS NULL;

CREATE INDEX collections_public_updated_idx
    ON public.collections (updated_at DESC)
    WHERE visibility = 'public' AND deleted_at IS NULL;

CREATE TABLE public.collection_items (
    collection_id uuid NOT NULL,
    owner_id uuid NOT NULL,
    movie_id uuid NOT NULL REFERENCES public.movies(id) ON DELETE RESTRICT,
    position integer NOT NULL,
    note text,
    added_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (collection_id, movie_id),
    CONSTRAINT collection_items_collection_owner_fk
        FOREIGN KEY (collection_id, owner_id)
        REFERENCES public.collections(id, owner_id)
        ON DELETE CASCADE,
    CONSTRAINT collection_items_position_ck CHECK (position >= 0),
    CONSTRAINT collection_items_note_ck CHECK (
        note IS NULL OR char_length(note) <= 2000
    ),
    CONSTRAINT collection_items_position_uidx
        UNIQUE (collection_id, position)
        DEFERRABLE INITIALLY IMMEDIATE
);

CREATE INDEX collection_items_owner_idx
    ON public.collection_items (owner_id, collection_id, position);

CREATE INDEX collection_items_movie_idx
    ON public.collection_items (movie_id);

COMMENT ON TABLE public.collection_items IS
    'owner_id intentionally duplicates the parent owner for simple ownership checks and future RLS policies; the composite foreign key prevents drift.';

COMMENT ON TABLE public.recommendation_event_results IS
    'user_id intentionally duplicates the parent owner for future RLS policies; the composite foreign key prevents drift.';

-- Keep updated_at reliable even when writes do not pass through the API.
CREATE TRIGGER users_set_updated_at
    BEFORE UPDATE ON public.users
    FOR EACH ROW EXECUTE FUNCTION public.tamiltrove_set_updated_at();
CREATE TRIGGER auth_sessions_set_updated_at
    BEFORE UPDATE ON public.auth_sessions
    FOR EACH ROW EXECUTE FUNCTION public.tamiltrove_set_updated_at();
CREATE TRIGGER ingestion_sources_set_updated_at
    BEFORE UPDATE ON public.ingestion_sources
    FOR EACH ROW EXECUTE FUNCTION public.tamiltrove_set_updated_at();
CREATE TRIGGER dataset_versions_set_updated_at
    BEFORE UPDATE ON public.dataset_versions
    FOR EACH ROW EXECUTE FUNCTION public.tamiltrove_set_updated_at();
CREATE TRIGGER ingestion_runs_set_updated_at
    BEFORE UPDATE ON public.ingestion_runs
    FOR EACH ROW EXECUTE FUNCTION public.tamiltrove_set_updated_at();
CREATE TRIGGER embedding_models_set_updated_at
    BEFORE UPDATE ON public.embedding_model_versions
    FOR EACH ROW EXECUTE FUNCTION public.tamiltrove_set_updated_at();
CREATE TRIGGER movies_set_updated_at
    BEFORE UPDATE ON public.movies
    FOR EACH ROW EXECUTE FUNCTION public.tamiltrove_set_updated_at();
CREATE TRIGGER people_set_updated_at
    BEFORE UPDATE ON public.people
    FOR EACH ROW EXECUTE FUNCTION public.tamiltrove_set_updated_at();
CREATE TRIGGER genres_set_updated_at
    BEFORE UPDATE ON public.genres
    FOR EACH ROW EXECUTE FUNCTION public.tamiltrove_set_updated_at();
CREATE TRIGGER themes_set_updated_at
    BEFORE UPDATE ON public.themes
    FOR EACH ROW EXECUTE FUNCTION public.tamiltrove_set_updated_at();
CREATE TRIGGER staged_movies_set_updated_at
    BEFORE UPDATE ON public.staged_movie_records
    FOR EACH ROW EXECUTE FUNCTION public.tamiltrove_set_updated_at();
CREATE TRIGGER quarantine_records_set_updated_at
    BEFORE UPDATE ON public.quarantine_records
    FOR EACH ROW EXECUTE FUNCTION public.tamiltrove_set_updated_at();
CREATE TRIGGER movie_quality_issues_set_updated_at
    BEFORE UPDATE ON public.movie_quality_issues
    FOR EACH ROW EXECUTE FUNCTION public.tamiltrove_set_updated_at();
CREATE TRIGGER ranking_configs_set_updated_at
    BEFORE UPDATE ON public.ranking_configs
    FOR EACH ROW EXECUTE FUNCTION public.tamiltrove_set_updated_at();
CREATE TRIGGER user_preferences_set_updated_at
    BEFORE UPDATE ON public.user_preferences
    FOR EACH ROW EXECUTE FUNCTION public.tamiltrove_set_updated_at();
CREATE TRIGGER user_interactions_set_updated_at
    BEFORE UPDATE ON public.user_interactions
    FOR EACH ROW EXECUTE FUNCTION public.tamiltrove_set_updated_at();
CREATE TRIGGER user_movie_states_set_updated_at
    BEFORE UPDATE ON public.user_movie_states
    FOR EACH ROW EXECUTE FUNCTION public.tamiltrove_set_updated_at();
CREATE TRIGGER collections_set_updated_at
    BEFORE UPDATE ON public.collections
    FOR EACH ROW EXECUTE FUNCTION public.tamiltrove_set_updated_at();
CREATE TRIGGER collection_items_set_updated_at
    BEFORE UPDATE ON public.collection_items
    FOR EACH ROW EXECUTE FUNCTION public.tamiltrove_set_updated_at();

COMMIT;
