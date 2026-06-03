"""Waitlist table CRUD."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from . import get_pool
from ..models import MiniScanResult, WaitlistEntry


async def insert(
    *,
    email: str,
    url: str | None,
    segment: str | None,
    ip: str | None,
    user_agent: str | None,
) -> str:
    """Insert a new waitlist row. Returns the new UUID."""
    pool = get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO growth.waitlist (email, url, segment, ip, user_agent)
            VALUES ($1, $2, $3, $4, $5)
            RETURNING id::text
            """,
            email, url, segment, ip, user_agent,
        )
    return row["id"]


async def get_by_email(email: str) -> dict | None:
    pool = get_pool()
    if not pool:
        return None
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM growth.waitlist WHERE email = $1", email
        )
    return dict(row) if row else None


async def get_by_id(id: str) -> dict | None:
    pool = get_pool()
    if not pool:
        return None
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM growth.waitlist WHERE id = $1::uuid", id
        )
    return dict(row) if row else None


async def list_all(
    *,
    scan_status: str | None = None,
    invite_status: str | None = None,
    segment: str | None = None,
    q: str | None = None,
    page: int = 1,
    page_size: int = 50,
) -> tuple[list[dict], int]:
    pool = get_pool()
    if not pool:
        return [], 0

    conditions = []
    params: list[Any] = []
    i = 1

    if scan_status:
        conditions.append(f"scan_status = ${i}")
        params.append(scan_status)
        i += 1
    if invite_status:
        conditions.append(f"invite_status = ${i}")
        params.append(invite_status)
        i += 1
    if segment:
        conditions.append(f"segment = ${i}")
        params.append(segment)
        i += 1
    if q:
        conditions.append(f"(email ILIKE ${i} OR url ILIKE ${i})")
        params.append(f"%{q}%")
        i += 1

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    offset = (page - 1) * page_size

    async with pool.acquire() as conn:
        count_row = await conn.fetchrow(
            f"SELECT COUNT(*) AS n FROM growth.waitlist {where}", *params
        )
        rows = await conn.fetch(
            f"""
            SELECT * FROM growth.waitlist {where}
            ORDER BY submitted_at DESC
            LIMIT {page_size} OFFSET {offset}
            """,
            *params,
        )

    return [dict(r) for r in rows], int(count_row["n"])


async def claim_next_pending_scan() -> dict | None:
    """Atomically claim one pending scan row. Returns None if none available."""
    pool = get_pool()
    if not pool:
        return None
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            UPDATE growth.waitlist
            SET scan_status = 'running',
                scan_started_at = now()
            WHERE id = (
                SELECT id FROM growth.waitlist
                WHERE scan_status = 'pending' AND url IS NOT NULL
                ORDER BY submitted_at ASC
                LIMIT 1
                FOR UPDATE SKIP LOCKED
            )
            RETURNING *
            """
        )
    return dict(row) if row else None


async def mark_scan_done(id: str, result: MiniScanResult) -> None:
    pool = get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE growth.waitlist
            SET scan_status = 'done',
                scan_done_at = now(),
                scan_result = $2::jsonb,
                scan_cost_usd = $3
            WHERE id = $1::uuid
            """,
            id,
            result.model_dump_json(),
            result.cost_usd,
        )


async def mark_scan_failed(id: str, error: str) -> None:
    pool = get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE growth.waitlist
            SET scan_status = 'failed',
                scan_done_at = now()
            WHERE id = $1::uuid
            """,
            id,
        )


async def mark_scan_capped(id: str) -> None:
    pool = get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE growth.waitlist SET scan_status = 'capped' WHERE id = $1::uuid",
            id,
        )


async def mark_scan_email_sent(id: str) -> None:
    pool = get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE growth.waitlist SET scan_email_sent_at = now() WHERE id = $1::uuid",
            id,
        )


async def mark_invite_sent(id: str) -> None:
    pool = get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE growth.waitlist SET invite_status='sent', invite_sent_at=now() WHERE id=$1::uuid",
            id,
        )


async def mark_invite_accepted(id: str, user_id: str) -> None:
    pool = get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """UPDATE growth.waitlist
               SET invite_status='accepted', invite_user_id=$2
               WHERE id=$1::uuid""",
            id, user_id,
        )


async def insert_beta_enrollment(user_id: str, waitlist_id: str, expires_days: int = 30) -> None:
    from datetime import timedelta
    pool = get_pool()
    if not pool:
        return
    expires_at = datetime.now(timezone.utc) + timedelta(days=expires_days)
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO growth.beta_enrollments (user_id, waitlist_id, expires_at)
            VALUES ($1, $2::uuid, $3)
            ON CONFLICT (user_id) DO NOTHING
            """,
            user_id, waitlist_id, expires_at,
        )


def _row_to_entry(row: dict) -> WaitlistEntry:
    scan_result = None
    if row.get("scan_result"):
        raw = row["scan_result"]
        if isinstance(raw, str):
            raw = json.loads(raw)
        scan_result = MiniScanResult.model_validate(raw)

    return WaitlistEntry(
        id=str(row["id"]),
        email=row["email"],
        url=row.get("url"),
        segment=row.get("segment"),
        ip=row.get("ip"),
        submitted_at=row["submitted_at"],
        scan_status=row["scan_status"],
        scan_started_at=row.get("scan_started_at"),
        scan_done_at=row.get("scan_done_at"),
        scan_result=scan_result,
        scan_cost_usd=float(row["scan_cost_usd"]) if row.get("scan_cost_usd") else None,
        scan_email_sent_at=row.get("scan_email_sent_at"),
        invite_status=row["invite_status"],
        invite_sent_at=row.get("invite_sent_at"),
        invite_user_id=row.get("invite_user_id"),
    )
