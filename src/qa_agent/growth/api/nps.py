"""POST /nps — submit NPS score from authenticated user."""
from __future__ import annotations

from typing import Callable

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from ..db import get_pool


class NPSSubmit(BaseModel):
    score: int = Field(..., ge=1, le=5)
    context_id: str | None = None
    comment: str | None = None


def make_router(auth_guard: Callable) -> APIRouter:
    router = APIRouter()

    @router.post("/nps", status_code=201)
    async def submit_nps(
        payload: NPSSubmit,
        request: Request,
        user=Depends(auth_guard),
    ) -> dict:
        user_id = getattr(user, "user_id", None) or str(user)
        if not user_id:
            raise HTTPException(401, "Not authenticated")

        pool = get_pool()
        if not pool:
            raise HTTPException(503, "DB unavailable")

        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO growth.nps_responses (user_id, score, context_id, comment)
                VALUES ($1, $2, $3, $4)
                RETURNING id::text
                """,
                user_id, payload.score, payload.context_id, payload.comment,
            )
        return {"status": "ok", "id": row["id"]}

    return router
