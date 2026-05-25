"""Drip job CRUD."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from . import get_pool


async def schedule(
    waitlist_id: str,
    template: str,
    delay: timedelta,
) -> None:
    pool = get_pool()
    if not pool:
        return
    scheduled_for = datetime.now(timezone.utc) + delay
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO growth.drip_jobs (waitlist_id, template, scheduled_for)
            VALUES ($1::uuid, $2, $3)
            ON CONFLICT DO NOTHING
            """,
            waitlist_id, template, scheduled_for,
        )


async def claim_due() -> list[dict]:
    """Claim all due pending jobs atomically."""
    pool = get_pool()
    if not pool:
        return []
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            UPDATE growth.drip_jobs
            SET status = 'sent', sent_at = now()
            WHERE id IN (
                SELECT id FROM growth.drip_jobs
                WHERE status = 'pending' AND scheduled_for <= now()
                ORDER BY scheduled_for ASC
                LIMIT 50
                FOR UPDATE SKIP LOCKED
            )
            RETURNING *
            """
        )
    return [dict(r) for r in rows]


async def mark_failed(id: str, error: str) -> None:
    pool = get_pool()
    if not pool:
        return
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE growth.drip_jobs SET status = 'failed', error = $2 WHERE id = $1::uuid",
            id, error,
        )


async def list_queue(status: str | None = None, limit: int = 100) -> list[dict]:
    pool = get_pool()
    if not pool:
        return []
    where = f"WHERE status = '{status}'" if status else ""
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            f"""
            SELECT dj.*, w.email, w.url
            FROM growth.drip_jobs dj
            JOIN growth.waitlist w ON w.id = dj.waitlist_id
            {where}
            ORDER BY scheduled_for ASC
            LIMIT {limit}
            """
        )
    return [dict(r) for r in rows]
