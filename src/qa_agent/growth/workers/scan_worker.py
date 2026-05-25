"""Scan worker — polls growth.waitlist for pending scans and runs them."""
from __future__ import annotations

import asyncio
import logging
from datetime import date

from ..config import FunnelConfig
from ..db import counters as db_counters
from ..db import drip as db_drip
from ..db import waitlist as db_waitlist
from ..emails import render as email_render
from ..hooks import FunnelHooks
from ..providers.email import EmailProvider
from ..providers.notify import NotificationProvider

logger = logging.getLogger(__name__)
_POLL_INTERVAL = 10  # seconds


class ScanWorker:
    def __init__(
        self,
        config: FunnelConfig,
        hooks: FunnelHooks,
        email: EmailProvider,
        notify: NotificationProvider,
    ) -> None:
        self._config = config
        self._hooks = hooks
        self._email = email
        self._notify = notify
        self._task: asyncio.Task | None = None

    def start(self) -> None:
        self._task = asyncio.create_task(self._loop(), name="growth-scan-worker")

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
                logger.exception("scan worker tick failed")
            await asyncio.sleep(_POLL_INTERVAL)

    async def _tick(self) -> None:
        today_count = await db_counters.get("mini_scans")
        if today_count >= self._config.daily_scan_cap:
            return

        row = await db_waitlist.claim_next_pending_scan()
        if not row:
            return

        wid = str(row["id"])
        email = row["email"]
        url = row["url"]

        logger.info("mini-scan starting email=%s url=%s", email, url)

        # Send "running" email + schedule drip
        try:
            entry = db_waitlist._row_to_entry(row)
            subject, html = email_render.render_mini_scan_running(entry)
            await self._email.send(email, subject, html)
            await db_drip.schedule(
                wid,
                "mini_scan_running",
                self._config.drip_schedule["mini_scan_running"],
            )
        except Exception:
            logger.exception("failed to send mini_scan_running email email=%s", email)

        # Notify founder
        try:
            today = await db_counters.get("mini_scans") + 1
            await self._notify.notify(
                self._config.founder_notify_channel,
                f"New signup: {email}",
                {
                    "url": url or "—",
                    "scans_today": f"{today}/{self._config.daily_scan_cap}",
                },
            )
        except Exception:
            logger.exception("failed to send founder notification email=%s", email)

        # Run the scan
        try:
            import asyncio as _asyncio
            result = await _asyncio.wait_for(
                self._hooks.run_mini_scan(email=email, url=url),
                timeout=self._config.mini_scan_wall_time_seconds,
            )
            await db_waitlist.mark_scan_done(wid, result)
            await db_counters.increment("mini_scans")
            logger.info("mini-scan done email=%s issues=%d cost=$%.4f", email, len(result.issues), result.cost_usd)

            # Send results email
            try:
                entry = db_waitlist._row_to_entry(await db_waitlist.get_by_id(wid) or {})
                subject, html = email_render.render_mini_scan_results(
                    entry, result, row.get("segment")
                )
                await self._email.send(email, subject, html)
                await db_waitlist.mark_scan_email_sent(wid)
                # Schedule next drip (invite at T+24h)
                await db_drip.schedule(
                    wid,
                    "invite",
                    self._config.drip_schedule["invite"],
                )
            except Exception:
                logger.exception("failed to send mini_scan_results email email=%s", email)

        except asyncio.TimeoutError:
            logger.warning("mini-scan timed out email=%s", email)
            await db_waitlist.mark_scan_failed(wid, "timeout")
        except Exception as exc:
            logger.exception("mini-scan error email=%s", email)
            await db_waitlist.mark_scan_failed(wid, str(exc))
