"""
CRUD operations for the `jobs` table.

All functions are no-ops (return None / empty list) if the DB pool is not
configured — callers fall back to in-memory state transparently.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from qa_agent.db import get_pool


async def create(run_id: str, spec_dir: str, **kwargs: Any) -> None:
    pool = get_pool()
    if not pool:
        return
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO jobs (id, user_id, spec_dir, status, started_at,
                              executor_model, max_scenarios)
            VALUES ($1, $2::uuid, $3, 'pending', $4, $5, $6)
            ON CONFLICT (id) DO NOTHING
            """,
            run_id,
            kwargs.get("user_id"),
            spec_dir,
            datetime.now(timezone.utc),
            kwargs.get("executor_model"),
            kwargs.get("max_scenarios"),
        )


async def update(run_id: str, **fields: Any) -> None:
    """Update arbitrary fields on a job row. Only known columns are written."""
    pool = get_pool()
    if not pool:
        return

    allowed = {
        "status", "completed_at", "summary", "report_path",
        "error", "cost_usd", "capped_at",
    }
    updates = {k: v for k, v in fields.items() if k in allowed}
    if not updates:
        return

    # Serialize JSONB fields
    if "summary" in updates and isinstance(updates["summary"], dict):
        updates["summary"] = json.dumps(updates["summary"])

    cols = list(updates.keys())
    vals = list(updates.values())
    set_clause = ", ".join(f"{c} = ${i+2}" for i, c in enumerate(cols))

    async with pool.acquire() as conn:
        await conn.execute(
            f"UPDATE jobs SET {set_clause} WHERE id = $1",
            run_id,
            *vals,
        )


async def get(run_id: str) -> dict | None:
    pool = get_pool()
    if not pool:
        return None
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM jobs WHERE id = $1", run_id)
    if row is None:
        return None
    return _row_to_dict(row)


async def list_all(user_id: str | None = None, limit: int = 100) -> list[dict]:
    pool = get_pool()
    if not pool:
        return []
    async with pool.acquire() as conn:
        if user_id:
            rows = await conn.fetch(
                "SELECT * FROM jobs WHERE user_id = $1::uuid ORDER BY created_at DESC LIMIT $2",
                user_id, limit,
            )
        else:
            rows = await conn.fetch(
                "SELECT * FROM jobs ORDER BY created_at DESC LIMIT $1", limit
            )
    return [_row_to_dict(r) for r in rows]


async def mark_interrupted() -> None:
    """Mark any pending/running jobs as failed (called on server startup)."""
    pool = get_pool()
    if not pool:
        return
    async with pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE jobs
            SET status = 'failed',
                completed_at = $1,
                error = 'Interrupted by server restart'
            WHERE status IN ('pending', 'running')
            """,
            datetime.now(timezone.utc),
        )


def _row_to_dict(row: Any) -> dict:
    d = dict(row)
    if isinstance(d.get("summary"), str):
        d["summary"] = json.loads(d["summary"])
    # Serialize datetimes to ISO strings for API compatibility
    for k in ("started_at", "completed_at", "created_at"):
        if isinstance(d.get(k), datetime):
            d[k] = d[k].isoformat()
    return d
