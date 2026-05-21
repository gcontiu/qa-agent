-- Tier enforcement + quota event log
--
-- Adds a `tier` column to public.users so the API can read each user's plan
-- without a separate lookup. Adds a `quota_events` table to log when a user
-- is blocked by their quota — used to deduplicate notification emails.

-- ---------------------------------------------------------------------------
-- 1. Tier column on public.users
-- ---------------------------------------------------------------------------

ALTER TABLE users ADD COLUMN IF NOT EXISTS tier TEXT NOT NULL DEFAULT 'free'
    CHECK (tier IN ('free', 'beta', 'starter', 'pro'));

-- ---------------------------------------------------------------------------
-- 2. quota_events — one row per block event, used to throttle email alerts
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS quota_events (
    id          BIGSERIAL PRIMARY KEY,
    user_id     UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    event_type  TEXT NOT NULL CHECK (event_type IN ('run_blocked', 'scan_blocked')),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS quota_events_user_month
    ON quota_events (user_id, event_type, created_at);

-- RLS: users can read their own events; writes go through service role only
ALTER TABLE quota_events ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "users_read_own_quota_events" ON quota_events;
CREATE POLICY "users_read_own_quota_events" ON quota_events
    FOR SELECT USING (user_id = auth.uid());
