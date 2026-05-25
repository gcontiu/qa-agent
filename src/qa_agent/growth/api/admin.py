"""Admin endpoints — gated by admin_guard dependency provided by host."""
from __future__ import annotations

from typing import Any, Callable

from fastapi import APIRouter, Depends, HTTPException, Query

from ..db import counters as db_counters
from ..db import drip as db_drip
from ..db import waitlist as db_waitlist
from ..hooks import FunnelHooks


def make_router(
    hooks: FunnelHooks,
    admin_guard: Callable,
) -> APIRouter:
    router = APIRouter(prefix="/admin/growth", dependencies=[Depends(admin_guard)])

    # -----------------------------------------------------------------------
    # Overview / dashboard KPIs
    # -----------------------------------------------------------------------

    @router.get("/overview")
    async def overview() -> dict:
        rows, total = await db_waitlist.list_all(page_size=20)
        scan_done = sum(1 for r in rows if r.get("scan_status") == "done")
        invite_sent = sum(1 for r in rows if r.get("invite_status") in ("sent", "accepted"))
        today_scans = await db_counters.get("mini_scans")
        recent_feed = rows[:10]
        return {
            "total_waitlist": total,
            "today_scans": today_scans,
            "recent": [_slim(r) for r in recent_feed],
        }

    # -----------------------------------------------------------------------
    # Waitlist list
    # -----------------------------------------------------------------------

    @router.get("/waitlist")
    async def list_waitlist(
        scan_status: str | None = Query(None),
        invite_status: str | None = Query(None),
        segment: str | None = Query(None),
        q: str | None = Query(None),
        page: int = Query(1, ge=1),
    ) -> dict:
        rows, total = await db_waitlist.list_all(
            scan_status=scan_status,
            invite_status=invite_status,
            segment=segment,
            q=q,
            page=page,
        )
        return {"total": total, "page": page, "items": [_slim(r) for r in rows]}

    # -----------------------------------------------------------------------
    # Per-user timeline
    # -----------------------------------------------------------------------

    @router.get("/waitlist/{id}")
    async def get_waitlist_entry(id: str) -> dict:
        row = await db_waitlist.get_by_id(id)
        if not row:
            raise HTTPException(404, "Not found")

        entry = db_waitlist._row_to_entry(row)
        drip_jobs = await db_drip.list_queue(limit=50)
        entry_drip = [j for j in drip_jobs if str(j.get("waitlist_id")) == id]

        # Optional host summary
        host_summary = None
        cost_summary = None
        if entry.invite_user_id:
            try:
                host_summary = await hooks.get_host_summary(entry.invite_user_id)
                cost_summary_obj = await hooks.get_user_cost_summary(entry.invite_user_id)
                if cost_summary_obj:
                    cost_summary = cost_summary_obj.model_dump()
            except Exception:
                pass

        return {
            "entry": entry.model_dump(),
            "drip_jobs": [_slim_drip(j) for j in entry_drip],
            "host_summary": host_summary,
            "cost_summary": cost_summary,
        }

    # -----------------------------------------------------------------------
    # Actions
    # -----------------------------------------------------------------------

    @router.post("/waitlist/{id}/force-rescan")
    async def force_rescan(id: str) -> dict:
        row = await db_waitlist.get_by_id(id)
        if not row:
            raise HTTPException(404, "Not found")
        from ..db import get_pool
        pool = get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                "UPDATE growth.waitlist SET scan_status = 'pending' WHERE id = $1::uuid",
                id,
            )
        return {"status": "queued"}

    @router.post("/waitlist/{id}/skip-next-drip")
    async def skip_next_drip(id: str) -> dict:
        pool_ref = db_drip.get_pool() if hasattr(db_drip, "get_pool") else None
        from ..db import get_pool
        pool = get_pool()
        if not pool:
            raise HTTPException(503, "DB unavailable")
        async with pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE growth.drip_jobs SET status = 'skipped'
                WHERE id = (
                    SELECT id FROM growth.drip_jobs
                    WHERE waitlist_id = $1::uuid AND status = 'pending'
                    ORDER BY scheduled_for ASC LIMIT 1
                )
                """,
                id,
            )
        return {"status": "skipped"}

    # -----------------------------------------------------------------------
    # Drip queue inspector
    # -----------------------------------------------------------------------

    @router.get("/drip")
    async def drip_queue(status: str | None = Query(None)) -> dict:
        jobs = await db_drip.list_queue(status=status)
        return {"items": [_slim_drip(j) for j in jobs]}

    return router


def _slim(row: dict) -> dict:
    return {
        "id": str(row.get("id", "")),
        "email": row.get("email"),
        "url": row.get("url"),
        "segment": row.get("segment"),
        "submitted_at": row.get("submitted_at"),
        "scan_status": row.get("scan_status"),
        "scan_cost_usd": float(row["scan_cost_usd"]) if row.get("scan_cost_usd") else None,
        "invite_status": row.get("invite_status"),
    }


def _slim_drip(row: dict) -> dict:
    return {
        "id": str(row.get("id", "")),
        "template": row.get("template"),
        "scheduled_for": row.get("scheduled_for"),
        "status": row.get("status"),
        "sent_at": row.get("sent_at"),
        "error": row.get("error"),
        "email": row.get("email"),
    }
