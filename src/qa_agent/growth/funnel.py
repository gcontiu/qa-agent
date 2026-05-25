"""BetaFunnel — main orchestrator.

Usage in host app (e.g. src/qa_agent/api.py):

    from qa_agent.growth import BetaFunnel, FunnelConfig
    from qa_agent.growth.providers.email import from_env as email_from_env
    from qa_agent.growth.providers.notify import from_env as notify_from_env
    from qa_agent.growth.providers.antiabuse import from_env as antiabuse_from_env
    from qa_agent.integrations.growth_hooks import QAAgentHooks

    funnel = BetaFunnel(
        config=FunnelConfig(),
        hooks=QAAgentHooks(),
        email=email_from_env(),
        notify=notify_from_env(),
        antiabuse=antiabuse_from_env(),
        admin_guard=require_admin,   # FastAPI dependency
    )

    app.include_router(funnel.router)
    app.on_event("startup")(funnel.start_workers)
    app.on_event("shutdown")(funnel.stop_workers)
"""
from __future__ import annotations

from fastapi import APIRouter

from .api.admin import make_router as make_admin_router
from .api.waitlist import make_router as make_waitlist_router
from .config import FunnelConfig
from .hooks import FunnelHooks
from .providers.antiabuse import AntiAbuseGuard, NoopGuard
from .providers.email import EmailProvider, ConsoleProvider
from .providers.notify import NotificationProvider, ConsoleNotifyProvider
from .workers.scan_worker import ScanWorker
from . import db as growth_db


class BetaFunnel:
    def __init__(
        self,
        config: FunnelConfig | None = None,
        hooks: FunnelHooks | None = None,
        email: EmailProvider | None = None,
        notify: NotificationProvider | None = None,
        antiabuse: AntiAbuseGuard | None = None,
        admin_guard=None,
        db=None,
    ) -> None:
        self._config = config or FunnelConfig()
        self._hooks = hooks
        self._email = email or ConsoleProvider()
        self._notify = notify or ConsoleNotifyProvider()
        self._antiabuse = antiabuse or NoopGuard()
        self._admin_guard = admin_guard or _noop_dep
        self._db = db

        if db is not None:
            growth_db.set_pool(db)

        self._scan_worker = ScanWorker(
            config=self._config,
            hooks=self._hooks,
            email=self._email,
            notify=self._notify,
        ) if self._hooks else None

        # Build the combined router
        self.router = APIRouter()
        self.router.include_router(
            make_waitlist_router(
                config=self._config,
                hooks=self._hooks,
                antiabuse=self._antiabuse,
                notify=self._notify,
            )
        )
        if self._hooks:
            self.router.include_router(
                make_admin_router(
                    hooks=self._hooks,
                    admin_guard=self._admin_guard,
                )
            )

    async def start_workers(self) -> None:
        if self._scan_worker:
            self._scan_worker.start()

    async def stop_workers(self) -> None:
        if self._scan_worker:
            await self._scan_worker.stop()


async def _noop_dep():
    """Default admin guard — allows all. Replace with tier check in production."""
    pass
