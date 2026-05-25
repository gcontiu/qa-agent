"""Public POST /waitlist endpoint."""
from __future__ import annotations

import re
from typing import Callable

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from ..config import FunnelConfig
from ..db import counters as db_counters
from ..db import waitlist as db_waitlist
from ..hooks import FunnelHooks
from ..providers.antiabuse import AntiAbuseGuard
from ..providers.notify import NotificationProvider


class WaitlistSubmit(BaseModel):
    email: str
    url: str | None = None
    turnstile_token: str | None = None
    segment: str | None = None


def make_router(
    config: FunnelConfig,
    hooks: FunnelHooks,
    antiabuse: AntiAbuseGuard,
    notify: NotificationProvider,
) -> APIRouter:
    router = APIRouter()

    @router.post("/waitlist", status_code=201)
    async def join_waitlist(request: Request, entry: WaitlistSubmit) -> dict:
        email = entry.email.strip().lower()

        if not re.match(r"^[^\s@]+@[^\s@]+\.[^\s@]{2,}$", email):
            raise HTTPException(422, "Invalid email address")
        if entry.url and not re.match(r"^https?://", entry.url):
            raise HTTPException(422, "URL must start with http:// or https://")

        remote_ip = request.headers.get("x-forwarded-for", request.client.host if request.client else "0.0.0.0").split(",")[0].strip()

        # Anti-abuse checks
        if entry.turnstile_token:
            ok = await antiabuse.verify_token(entry.turnstile_token, remote_ip)
            if not ok:
                raise HTTPException(422, "Bot check failed")

        email_check = await antiabuse.check_email(email)
        if not email_check.ok:
            raise HTTPException(422, f"Email not accepted: {email_check.reason}")

        rate_check = await antiabuse.check_ip_rate(remote_ip)
        if not rate_check.ok:
            raise HTTPException(429, "Too many signups from this IP")

        # Deduplicate
        existing = await db_waitlist.get_by_email(email)
        if existing:
            return {"status": "already_queued"}

        # Segment detection
        segment = entry.segment
        if not segment and entry.url:
            segment = _detect_segment(entry.url, config)

        wid = await db_waitlist.insert(
            email=email,
            url=entry.url,
            segment=segment,
            ip=remote_ip,
            user_agent=request.headers.get("user-agent"),
        )

        # Cap check
        today_count = await db_counters.get("mini_scans")
        if today_count >= config.daily_scan_cap:
            await db_waitlist.mark_scan_capped(wid)

        return {"status": "ok", "id": wid}

    return router


def _detect_segment(url: str, config: FunnelConfig) -> str | None:
    import re
    for rule in config.segment_rules:
        if re.search(rule.pattern, url, re.IGNORECASE):
            return rule.segment
    return None
