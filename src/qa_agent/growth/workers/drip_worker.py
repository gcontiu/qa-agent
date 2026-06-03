"""Drip worker — processes scheduled drip_jobs every 30s."""
from __future__ import annotations

import asyncio
import logging

from ..config import FunnelConfig
from ..db import drip as db_drip
from ..db import waitlist as db_waitlist
from ..emails import render as email_render
from ..hooks import FunnelHooks
from ..providers.email import EmailProvider
from ..providers.notify import NotificationProvider

logger = logging.getLogger(__name__)
_POLL_INTERVAL = 30


class DripWorker:
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
        self._task = asyncio.create_task(self._loop(), name="growth-drip-worker")

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
                logger.exception("drip worker tick failed")
            await asyncio.sleep(_POLL_INTERVAL)

    async def _tick(self) -> None:
        jobs = await db_drip.claim_due()
        for job in jobs:
            await self._process(job)

    async def _process(self, job: dict) -> None:
        template = job.get("template", "")
        wid = str(job.get("waitlist_id", ""))
        job_id = str(job.get("id", ""))

        row = await db_waitlist.get_by_id(wid)
        if not row:
            logger.warning("drip job %s: waitlist row %s not found", job_id, wid)
            return

        entry = db_waitlist._row_to_entry(row)

        try:
            if template == "reinforce":
                subject, html = email_render.render_reinforce(entry)
                await self._email.send(entry.email, subject, html)

            elif template == "beta_check_in":
                subject, html = email_render.render_beta_check_in(entry)
                await self._email.send(entry.email, subject, html)

            elif template == "cohort_report":
                total_runs, issues_found, cost_usd = await self._cohort_stats(entry)
                subject, html = email_render.render_cohort_report(
                    entry, total_runs=total_runs,
                    issues_found=issues_found, cost_usd=cost_usd,
                )
                await self._email.send(entry.email, subject, html)

            elif template == "invite":
                # Notify founder to manually send invite (or auto-send if key configured)
                await self._notify.notify(
                    self._config.founder_notify_channel,
                    f"Invite ready: {entry.email}",
                    {"url": entry.url or "—", "action": "send invite from admin panel"},
                )

            elif template in ("mini_scan_running", "mini_scan_results"):
                # Already sent directly by scan_worker — mark done, skip re-send
                pass

            else:
                logger.warning("drip job %s: unknown template %r", job_id, template)

            logger.info("drip sent template=%s email=%s", template, entry.email)

        except Exception:
            logger.exception("drip failed template=%s email=%s", template, entry.email)
            await db_drip.mark_failed(job_id, "send error")

    async def _cohort_stats(self, entry) -> tuple[int, int, float]:
        if not entry.invite_user_id:
            return 0, 0, 0.0
        try:
            summary = await self._hooks.get_user_cost_summary(entry.invite_user_id)
            host = await self._hooks.get_host_summary(entry.invite_user_id)
            total_runs = (host or {}).get("total_runs", 0) or 0
            cost_usd = (summary.total_usd if summary else 0) or 0.0
            issues_found = (entry.scan_result.issues.__len__() if entry.scan_result else 0)
            return int(total_runs), issues_found, float(cost_usd)
        except Exception:
            return 0, 0, 0.0
