"""Admin endpoints — gated by admin_guard dependency provided by host."""
from __future__ import annotations

import logging
import os
from typing import Any, Callable

logger = logging.getLogger(__name__)

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query

from ..config import FunnelConfig
from ..db import counters as db_counters
from ..db import drip as db_drip
from ..db import waitlist as db_waitlist
from ..emails.render import render_invite
from ..hooks import FunnelHooks
from ..providers.email import EmailProvider


def make_router(
    hooks: FunnelHooks,
    admin_guard: Callable,
    email: EmailProvider | None = None,
    config: FunnelConfig | None = None,
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

    @router.post("/waitlist/{id}/send-invite")
    async def send_invite(id: str) -> dict:
        row = await db_waitlist.get_by_id(id)
        if not row:
            raise HTTPException(404, "Not found")
        entry = db_waitlist._row_to_entry(row)
        if entry.invite_status not in ("none", "requested"):
            raise HTTPException(409, f"Already {entry.invite_status}")

        supabase_url = os.getenv("SUPABASE_URL", "").rstrip("/")
        service_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
        if not service_key:
            raise HTTPException(503, "SUPABASE_SERVICE_ROLE_KEY not configured")

        app_url = os.getenv("APP_URL", "https://steadra.dev").rstrip("/")
        redirect_to = f"{app_url}/set-password"
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                f"{supabase_url}/auth/v1/admin/generate_link",
                headers={
                    "apikey": service_key,
                    "Authorization": f"Bearer {service_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "type": "magiclink",
                    "email": entry.email,
                    "options": {"redirect_to": redirect_to},
                },
            )

        if resp.status_code not in (200, 201):
            raise HTTPException(502, f"Supabase link generation failed: {resp.text[:200]}")

        data = resp.json()
        # Supabase returns action_link at top level or inside properties
        magic_link = data.get("action_link") or (data.get("properties") or {}).get("action_link")
        if not magic_link:
            raise HTTPException(502, f"Supabase returned no action_link. Response: {str(data)[:300]}")

        # Diagnostic: log requested vs. returned redirect_to (no token leak — redirect_to
        # is a separate query param). If returned == requested, Supabase accepted it and any
        # failure is at click-time (allow-list), pointing at the redirect-URL allow-list.
        from urllib.parse import urlparse, parse_qs
        returned_redirect = parse_qs(urlparse(magic_link).query).get("redirect_to", ["<none>"])[0]
        logger.info(
            "INVITE LINK email=%s requested_redirect=%s returned_redirect=%s",
            entry.email, redirect_to, returned_redirect,
        )

        if email:
            subject, html = render_invite(entry, magic_link)
            await email.send(to=entry.email, subject=subject, html=html)

        await db_waitlist.mark_invite_sent(id)
        return {"status": "sent", "email": entry.email}

    @router.post("/waitlist/{id}/seed-account")
    async def seed_account(id: str) -> dict:
        row = await db_waitlist.get_by_id(id)
        if not row:
            raise HTTPException(404, "Not found")
        entry = db_waitlist._row_to_entry(row)
        if not entry.invite_user_id:
            raise HTTPException(409, "User has not accepted the invite yet")
        if not entry.scan_result:
            raise HTTPException(409, "No scan result to seed from")
        await hooks.seed_user_account(entry.invite_user_id, entry)
        return {"status": "seeded", "user_id": entry.invite_user_id}

    # -----------------------------------------------------------------------
    # Funnel stats
    # -----------------------------------------------------------------------

    @router.get("/funnel")
    async def funnel_stats() -> dict:
        from ..db import get_pool
        pool = get_pool()
        if not pool:
            return {"stages": []}
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT
                    COUNT(*)::int                                                AS submitted,
                    COUNT(*) FILTER (WHERE scan_status = 'done')::int           AS scan_done,
                    COUNT(*) FILTER (WHERE invite_status IN ('sent','accepted'))::int AS invite_sent,
                    COUNT(*) FILTER (WHERE invite_status = 'accepted')::int     AS beta_active
                FROM growth.waitlist
                """
            )
        stages = [
            {"label": "Submitted",    "value": row["submitted"]},
            {"label": "Scan done",    "value": row["scan_done"]},
            {"label": "Invite sent",  "value": row["invite_sent"]},
            {"label": "Beta active",  "value": row["beta_active"]},
        ]
        return {"stages": stages}

    # -----------------------------------------------------------------------
    # Cost series (daily, for projection chart)
    # -----------------------------------------------------------------------

    @router.get("/cost-series")
    async def cost_series() -> dict:
        from ..db import get_pool
        pool = get_pool()
        if not pool:
            return {"series": [], "projection": None}
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT
                    scan_done_at::date AS day,
                    SUM(scan_cost_usd)::float AS cost_usd,
                    COUNT(*)::int AS scans
                FROM growth.waitlist
                WHERE scan_status = 'done' AND scan_cost_usd IS NOT NULL
                GROUP BY 1
                ORDER BY 1 ASC
                """
            )
        series = [
            {"day": str(r["day"]), "cost_usd": round(r["cost_usd"], 4), "scans": r["scans"]}
            for r in rows
        ]
        projection = _eom_projection(series)
        return {"series": series, "projection": projection}

    # -----------------------------------------------------------------------
    # NPS summary (admin view)
    # -----------------------------------------------------------------------

    @router.get("/nps")
    async def nps_summary() -> dict:
        from ..db import get_pool
        pool = get_pool()
        if not pool:
            return {"responses": [], "avg_score": None}
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT user_id, score, context_id, comment, submitted_at
                FROM growth.nps_responses
                ORDER BY submitted_at DESC
                LIMIT 100
                """
            )
            avg = await conn.fetchval(
                "SELECT ROUND(AVG(score)::numeric, 2)::float FROM growth.nps_responses"
            )
        return {
            "avg_score": avg,
            "responses": [
                {
                    "user_id": str(r["user_id"]),
                    "score": r["score"],
                    "context_id": r["context_id"],
                    "comment": r["comment"],
                    "submitted_at": r["submitted_at"],
                }
                for r in rows
            ],
        }

    # -----------------------------------------------------------------------
    # Active beta enrollments
    # -----------------------------------------------------------------------

    @router.get("/beta")
    async def beta_enrollments() -> dict:
        from ..db import get_pool
        pool = get_pool()
        if not pool:
            return {"items": []}
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT
                    be.user_id,
                    be.waitlist_id::text,
                    be.enrolled_at,
                    be.expires_at,
                    be.status,
                    be.converted_to_tier,
                    w.email,
                    w.url,
                    w.segment
                FROM growth.beta_enrollments be
                JOIN growth.waitlist w ON w.id = be.waitlist_id
                ORDER BY be.enrolled_at DESC
                """
            )
        return {"items": [_slim_beta(r) for r in rows]}

    # -----------------------------------------------------------------------
    # Drip queue inspector
    # -----------------------------------------------------------------------

    @router.get("/drip")
    async def drip_queue(status: str | None = Query(None)) -> dict:
        jobs = await db_drip.list_queue(status=status)
        return {"items": [_slim_drip(j) for j in jobs]}

    return router


def _eom_projection(series: list[dict]) -> dict | None:
    from datetime import date, timedelta
    if not series:
        return None
    today = date.today()
    month_start = today.replace(day=1)
    days_in_month = (month_start.replace(month=today.month % 12 + 1, day=1) - timedelta(days=1)).day
    days_elapsed = max(today.day, 1)
    days_remaining = days_in_month - today.day

    month_spend = sum(
        r["cost_usd"] for r in series
        if r["day"] >= str(month_start)
    )
    daily_avg = month_spend / days_elapsed
    eom_forecast = month_spend + daily_avg * days_remaining

    return {
        "month_spend": round(month_spend, 4),
        "daily_avg": round(daily_avg, 4),
        "eom_forecast": round(eom_forecast, 4),
        "days_elapsed": days_elapsed,
        "days_remaining": days_remaining,
    }


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


def _slim_beta(row: dict) -> dict:
    from datetime import datetime, timezone
    expires_at = row.get("expires_at")
    if expires_at and hasattr(expires_at, "astimezone"):
        days_left = (expires_at.astimezone(timezone.utc) - datetime.now(timezone.utc)).days
    else:
        days_left = None
    return {
        "user_id": str(row.get("user_id", "")),
        "waitlist_id": row.get("waitlist_id"),
        "email": row.get("email"),
        "url": row.get("url"),
        "segment": row.get("segment"),
        "enrolled_at": row.get("enrolled_at"),
        "expires_at": expires_at,
        "days_left": days_left,
        "status": row.get("status"),
        "converted_to_tier": row.get("converted_to_tier"),
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
