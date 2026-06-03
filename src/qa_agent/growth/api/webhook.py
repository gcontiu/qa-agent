"""Webhook endpoints called by Supabase Auth events.

Set up in Supabase Dashboard → Auth → Webhooks:
  - Event: INSERT on auth.users
  - URL:   {APP_URL}/growth/webhook/user-activated
  - Secret: matches GROWTH_WEBHOOK_SECRET env var

Or call manually: POST /growth/webhook/user-activated
  Body: {"user_id": "...", "email": "..."}
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import os

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel

from ..db import waitlist as db_waitlist
from ..hooks import FunnelHooks

logger = logging.getLogger(__name__)


class UserActivatedPayload(BaseModel):
    user_id: str
    email: str


def make_router(hooks: FunnelHooks) -> APIRouter:
    router = APIRouter(prefix="/growth/webhook")

    @router.post("/user-activated")
    async def user_activated(
        payload: UserActivatedPayload,
        request: Request,
        x_webhook_secret: str | None = Header(None),
    ) -> dict:
        _verify_secret(x_webhook_secret)

        row = await db_waitlist.get_by_email(payload.email)
        if not row:
            return {"status": "no_match"}

        entry = db_waitlist._row_to_entry(row)

        # Already accepted — idempotent
        if entry.invite_status == "accepted":
            return {"status": "already_accepted"}

        await db_waitlist.mark_invite_accepted(str(row["id"]), payload.user_id)
        await db_waitlist.insert_beta_enrollment(
            payload.user_id, str(row["id"]), expires_days=30
        )

        try:
            await hooks.seed_user_account(payload.user_id, entry)
        except Exception:
            logger.exception("seed_user_account failed for user=%s", payload.user_id)

        return {"status": "accepted", "waitlist_id": str(row["id"])}

    return router


def _verify_secret(provided: str | None) -> None:
    expected = os.getenv("GROWTH_WEBHOOK_SECRET", "")
    if not expected:
        return  # secret not configured — open in dev
    if not provided:
        raise HTTPException(401, "Missing X-Webhook-Secret header")
    if not hmac.compare_digest(provided.encode(), expected.encode()):
        raise HTTPException(403, "Invalid webhook secret")
