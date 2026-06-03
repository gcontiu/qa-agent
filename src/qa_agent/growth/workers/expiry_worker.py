"""Expiry worker — daily sweep on beta_enrollments.expires_at."""
from __future__ import annotations

import asyncio
import logging

from ..db import get_pool
from ..hooks import FunnelHooks

logger = logging.getLogger(__name__)
_POLL_INTERVAL = 60 * 60 * 6  # every 6 hours


class ExpiryWorker:
    def __init__(self, hooks: FunnelHooks) -> None:
        self._hooks = hooks
        self._task: asyncio.Task | None = None

    def start(self) -> None:
        self._task = asyncio.create_task(self._loop(), name="growth-expiry-worker")

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _loop(self) -> None:
        while True:
            try:
                await self._tick()
            except Exception:
                logger.exception("expiry worker tick failed")
            await asyncio.sleep(_POLL_INTERVAL)

    async def _tick(self) -> None:
        pool = get_pool()
        if not pool:
            return

        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                UPDATE growth.beta_enrollments
                SET status = 'expired'
                WHERE status = 'active' AND expires_at < now()
                RETURNING user_id
                """
            )

        if not rows:
            return

        logger.info("expiry worker: %d enrollment(s) expired", len(rows))
        for row in rows:
            user_id = row["user_id"]
            try:
                await self._hooks.revoke_tier(user_id)
                logger.info("revoked beta tier for user=%s", user_id)
            except Exception:
                logger.exception("failed to revoke tier for user=%s", user_id)
