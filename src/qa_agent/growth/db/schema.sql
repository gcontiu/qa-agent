-- growth schema — isolated from host tables
-- Cross-schema reference only via loose user_id TEXT.
-- Safe to re-run: uses IF NOT EXISTS.

CREATE SCHEMA IF NOT EXISTS growth;

CREATE TABLE IF NOT EXISTS growth.waitlist (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    email           TEXT        NOT NULL UNIQUE,
    url             TEXT,
    segment         TEXT,                   -- 'ecommerce' | 'saas' | 'agency' | NULL
    ip              TEXT,
    user_agent      TEXT,
    submitted_at    TIMESTAMPTZ NOT NULL DEFAULT now(),

    scan_status     TEXT        NOT NULL DEFAULT 'pending'
                                CHECK (scan_status IN ('pending','running','done','failed','capped')),
    scan_started_at TIMESTAMPTZ,
    scan_done_at    TIMESTAMPTZ,
    scan_result     JSONB,
    scan_cost_usd   NUMERIC(8,4),           -- NULL until scan completes
    scan_email_sent_at TIMESTAMPTZ,

    invite_status   TEXT        NOT NULL DEFAULT 'none'
                                CHECK (invite_status IN ('none','sent','accepted')),
    invite_sent_at  TIMESTAMPTZ,
    invite_user_id  TEXT
);

CREATE INDEX IF NOT EXISTS growth_waitlist_email_idx
    ON growth.waitlist (email);
CREATE INDEX IF NOT EXISTS growth_waitlist_scan_status_idx
    ON growth.waitlist (scan_status) WHERE scan_status IN ('pending', 'running');
CREATE INDEX IF NOT EXISTS growth_waitlist_submitted_at_idx
    ON growth.waitlist (submitted_at DESC);

CREATE TABLE IF NOT EXISTS growth.beta_enrollments (
    user_id           TEXT        PRIMARY KEY,
    waitlist_id       UUID        REFERENCES growth.waitlist(id),
    enrolled_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at        TIMESTAMPTZ NOT NULL,
    status            TEXT        NOT NULL DEFAULT 'active'
                                  CHECK (status IN ('active','expired','converted')),
    converted_to_tier TEXT,
    converted_at      TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS growth_beta_enrollments_status_idx
    ON growth.beta_enrollments (status, expires_at ASC)
    WHERE status = 'active';

CREATE TABLE IF NOT EXISTS growth.drip_jobs (
    id            UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    waitlist_id   UUID        REFERENCES growth.waitlist(id),
    template      TEXT        NOT NULL,
    scheduled_for TIMESTAMPTZ NOT NULL,
    sent_at       TIMESTAMPTZ,
    status        TEXT        NOT NULL DEFAULT 'pending'
                              CHECK (status IN ('pending','sent','failed','skipped')),
    error         TEXT
);

CREATE INDEX IF NOT EXISTS growth_drip_jobs_pending_idx
    ON growth.drip_jobs (scheduled_for ASC) WHERE status = 'pending';

CREATE TABLE IF NOT EXISTS growth.nps_responses (
    id           UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id      TEXT        NOT NULL,
    score        INT         NOT NULL CHECK (score BETWEEN 1 AND 5),
    context_id   TEXT,                      -- e.g. run_id; opaque to growth
    comment      TEXT,
    submitted_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS growth.daily_counters (
    counter_date  DATE        NOT NULL,
    counter_name  TEXT        NOT NULL,
    counter_value INT         NOT NULL DEFAULT 0,
    PRIMARY KEY (counter_date, counter_name)
);
