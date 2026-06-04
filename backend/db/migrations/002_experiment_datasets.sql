CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS experiment_datasets (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    app_user text NOT NULL DEFAULT 'nfyy',
    display_name text NOT NULL,
    file_name text NOT NULL,
    file_size bigint NOT NULL DEFAULT 0,
    top_k integer NOT NULL DEFAULT 100,
    result_count integer NOT NULL DEFAULT 0,
    group_descriptions jsonb NOT NULL DEFAULT '{}'::jsonb,
    warnings jsonb NOT NULL DEFAULT '[]'::jsonb,
    results jsonb NOT NULL DEFAULT '[]'::jsonb,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_experiment_datasets_app_user_updated
    ON experiment_datasets (app_user, updated_at DESC);
