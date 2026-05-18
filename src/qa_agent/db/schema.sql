-- qa-agent Postgres schema
-- Run once on Supabase: SQL Editor → paste → Run
-- Safe to re-run: all statements use IF NOT EXISTS / ON CONFLICT DO NOTHING.

-- Extension for UUID generation (already enabled on Supabase)
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ---------------------------------------------------------------------------
-- users (public mirror of auth.users — D1=Option B)
-- IDs come from auth.users via the on_auth_user_created trigger (no default).
-- Business-table FKs point here, not at auth.users directly, so migrating
-- away from Supabase Auth only requires swapping the trigger + JWT middleware.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS users (
    id          UUID        PRIMARY KEY,          -- set by trigger from auth.users.id
    email       TEXT        UNIQUE NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Sync trigger: new auth.users row → public.users row
-- SECURITY DEFINER required: supabase_auth_admin owns auth.users but lacks
-- INSERT on public.users; running as function owner grants the privilege.
CREATE OR REPLACE FUNCTION public.handle_new_auth_user()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER SET search_path = public
AS $$
BEGIN
    INSERT INTO public.users (id, email, created_at)
    VALUES (NEW.id, NEW.email, NEW.created_at)
    ON CONFLICT (id) DO NOTHING;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;
CREATE TRIGGER on_auth_user_created
    AFTER INSERT ON auth.users
    FOR EACH ROW EXECUTE FUNCTION public.handle_new_auth_user();

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
-- issues
-- Technical problems discovered during analyst crawl.
-- Upserted by (product_id, fingerprint) — same issue across multiple runs
-- increments occurrences rather than creating a new row.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS issues (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    product_id      UUID        REFERENCES products(id) ON DELETE CASCADE,
    fingerprint     TEXT        NOT NULL,
    type            TEXT        NOT NULL,
    severity        TEXT        NOT NULL  CHECK (severity IN ('high','medium','low')),
    url             TEXT        NOT NULL,
    message         TEXT        NOT NULL,
    details         JSONB       NOT NULL DEFAULT '{}',
    status          TEXT        NOT NULL DEFAULT 'open'
                                CHECK (status IN ('open','acknowledged','wont_fix','resolved')),
    first_seen_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    occurrences     INTEGER     NOT NULL DEFAULT 1,
    UNIQUE (product_id, fingerprint)
);

CREATE INDEX IF NOT EXISTS issues_product_status_idx
    ON issues (product_id, status, severity);

ALTER TABLE issues ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "users_own_issues" ON issues;
CREATE POLICY "users_own_issues" ON issues
    FOR ALL USING (
        product_id IN (
            SELECT id FROM products WHERE user_id = auth.uid()
        )
    );

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

-- ---------------------------------------------------------------------------
-- Row Level Security (D3=both layers)
-- auth.uid() is the only Supabase-specific surface; replace with
-- current_setting('app.user_id')::uuid when migrating away from Supabase Auth.
-- ---------------------------------------------------------------------------

ALTER TABLE products ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "users_own_products" ON products;
CREATE POLICY "users_own_products" ON products
    FOR ALL USING (user_id = auth.uid());

ALTER TABLE specs ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "users_own_specs" ON specs;
CREATE POLICY "users_own_specs" ON specs
    FOR ALL USING (
        product_id IN (
            SELECT id FROM products WHERE user_id = auth.uid()
        )
    );

ALTER TABLE jobs ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "users_own_jobs" ON jobs;
CREATE POLICY "users_own_jobs" ON jobs
    FOR ALL USING (user_id = auth.uid());
