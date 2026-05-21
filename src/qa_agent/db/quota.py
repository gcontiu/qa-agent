"""Quota helpers: tier lookup, monthly counters, event logging."""
from __future__ import annotations

from datetime import datetime, timezone

from qa_agent.db import get_pool


async def get_tier(user_id: str) -> str:
    """Return the user's tier string, defaulting to 'free' if DB unavailable."""
    pool = get_pool()
    if not pool:
        return "free"
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT tier FROM users WHERE id = $1::uuid", user_id
        )
    return row["tier"] if row else "free"


async def count_runs_this_month(user_id: str) -> int:
    pool = get_pool()
    if not pool:
        return 0
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT COUNT(*) AS n FROM jobs
            WHERE user_id = $1::uuid
              AND date_trunc('month', started_at) = date_trunc('month', now())
            """,
            user_id,
        )
    return int(row["n"]) if row else 0


async def count_scans_this_month(user_id: str) -> int:
    """Count analyst runs this calendar month, excluding failed ones.

    Failed scans (Anthropic errors, bad URLs, etc.) don't count against quota —
    consistent with BD-004's rule that environmental failures are free.
    """
    pool = get_pool()
    if not pool:
        return 0
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT COUNT(*) AS n FROM jobs
            WHERE user_id = $1::uuid
              AND spec_dir LIKE 'analyze:%'
              AND status != 'failed'
              AND date_trunc('month', started_at) = date_trunc('month', now())
            """,
            user_id,
        )
    return int(row["n"]) if row else 0


async def log_quota_event(user_id: str, event_type: str) -> None:
    pool = get_pool()
    if not pool:
        return
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO quota_events (user_id, event_type) VALUES ($1::uuid, $2)",
            user_id, event_type,
        )


async def already_notified_this_month(user_id: str, event_type: str) -> bool:
    """True if we already sent a block-notification email for this user+type this month."""
    pool = get_pool()
    if not pool:
        return False
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT 1 FROM quota_events
            WHERE user_id = $1::uuid
              AND event_type = $2
              AND date_trunc('month', created_at) = date_trunc('month', now())
            LIMIT 1
            """,
            user_id, event_type,
        )
    return row is not None
