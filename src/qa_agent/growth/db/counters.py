"""Daily counter helpers (scan cap tracking, etc.)."""
from __future__ import annotations

from datetime import date

from . import get_pool


async def increment(name: str, by: int = 1) -> int:
    """Increment counter for today, return new value."""
    pool = get_pool()
    if not pool:
        return 0
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO growth.daily_counters (counter_date, counter_name, counter_value)
            VALUES (current_date, $1, $2)
            ON CONFLICT (counter_date, counter_name)
            DO UPDATE SET counter_value = growth.daily_counters.counter_value + $2
            RETURNING counter_value
            """,
            name, by,
        )
    return int(row["counter_value"])


async def get(name: str, for_date: date | None = None) -> int:
    pool = get_pool()
    if not pool:
        return 0
    target = for_date or date.today()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT counter_value FROM growth.daily_counters
            WHERE counter_date = $1 AND counter_name = $2
            """,
            target, name,
        )
    return int(row["counter_value"]) if row else 0


async def get_series(name: str, days: int = 30) -> list[dict]:
    """Return daily values for the last N days (including 0 days)."""
    pool = get_pool()
    if not pool:
        return []
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT d::date AS counter_date,
                   COALESCE(c.counter_value, 0) AS counter_value
            FROM generate_series(
                current_date - ($2 - 1)::int, current_date, '1 day'
            ) d
            LEFT JOIN growth.daily_counters c
                ON c.counter_date = d::date AND c.counter_name = $1
            ORDER BY d ASC
            """,
            name, days,
        )
    return [{"date": str(r["counter_date"]), "value": int(r["counter_value"])} for r in rows]
