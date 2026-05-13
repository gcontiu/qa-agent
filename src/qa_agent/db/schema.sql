-- qa-agent Postgres schema
-- Run once on Supabase: SQL Editor → paste → Run
-- Safe to re-run: all statements use IF NOT EXISTS / ON CONFLICT DO NOTHING.

-- Extension for UUID generation (already enabled on Supabase)
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ---------------------------------------------------------------------------
-- users
-- Stub for now — populated by Clerk/Supabase Auth in Step 6.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS users (
    id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    email       TEXT        UNIQUE NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------------
-- products
-- A user's target website. One product → many spec files + many jobs.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS products (
    id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     UUID        REFERENCES users(id) ON DELETE CASCADE,
    name        TEXT        NOT NULL,
    url         TEXT        NOT NULL,
    description TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------------
-- specs
-- Generated feature files per product. Stored in DB so they survive
-- redeploys (no longer dependent on container filesystem).
-- approved = user reviewed and approved before first run.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS specs (
    id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    product_id  UUID        REFERENCES products(id) ON DELETE CASCADE,
    filename    TEXT        NOT NULL,         -- e.g. "homepage.feature"
    content     TEXT        NOT NULL,         -- raw Gherkin or config.yaml
    approved    BOOLEAN     NOT NULL DEFAULT false,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (product_id, filename)
);

-- ---------------------------------------------------------------------------
-- jobs
-- Replaces the in-memory _runs dict + run_status.json files.
-- Survives server restarts; queryable per user.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS jobs (
    id              TEXT        PRIMARY KEY,  -- "emag-2026-05-13T15-41-00Z"
    user_id         UUID        REFERENCES users(id) ON DELETE SET NULL,
    product_id      UUID        REFERENCES products(id) ON DELETE SET NULL,
    spec_dir        TEXT        NOT NULL,
    status          TEXT        NOT NULL DEFAULT 'pending'
                                CHECK (status IN ('pending','running','done','failed','cancelled')),
    executor_model  TEXT,
    max_scenarios   INTEGER,
    capped_at       INTEGER,                  -- actual cap applied (if < max_scenarios)
    started_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at    TIMESTAMPTZ,
    summary         JSONB,                    -- {total, passed, failed, errored}
    report_path     TEXT,                     -- relative path to report.json on volume
    error           TEXT,
    cost_usd        NUMERIC(10, 6),           -- from telemetry.json after run
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS jobs_user_id_idx     ON jobs (user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS jobs_status_idx      ON jobs (status) WHERE status IN ('pending', 'running');
CREATE INDEX IF NOT EXISTS jobs_product_id_idx  ON jobs (product_id);

-- ---------------------------------------------------------------------------
-- Trigger: auto-update specs.updated_at
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS specs_updated_at ON specs;
CREATE TRIGGER specs_updated_at
    BEFORE UPDATE ON specs
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();
