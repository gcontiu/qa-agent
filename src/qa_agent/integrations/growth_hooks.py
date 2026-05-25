"""QAAgentHooks — qa-agent's implementation of FunnelHooks.

This is the only qa-agent-specific file in the growth integration.
Everything else lives in src/qa_agent/growth/.
"""
from __future__ import annotations

import logging

from qa_agent.growth.models import CostSummary, MiniScanResult, ScanIssue, WaitlistEntry

logger = logging.getLogger(__name__)


class QAAgentHooks:
    async def run_mini_scan(self, email: str, url: str) -> MiniScanResult:
        """Run Opus analyst pass on the URL. 60s wall-time cap applied by the worker."""
        from qa_agent.analyst import run_analysis
        try:
            result = await run_analysis(
                pages=[url],
                model="claude-opus-4-7",
            )
            issues = []
            for finding in result.findings:
                sev = "critical" if finding.severity in ("high", "critical") else (
                    "warning" if finding.severity == "medium" else "info"
                )
                issues.append(ScanIssue(
                    severity=sev,
                    type=finding.type,
                    message=finding.message,
                    location=getattr(finding, "url", None),
                ))
            cost = float(getattr(result, "cost_usd", 0) or 0)
            return MiniScanResult(
                issues=issues,
                page_count=getattr(result, "pages_crawled", 1),
                duration_ms=getattr(result, "duration_ms", 0),
                cost_usd=cost,
            )
        except Exception as exc:
            logger.exception("mini-scan failed for %s", url)
            raise

    async def seed_user_account(self, user_id: str, waitlist_row: WaitlistEntry) -> None:
        from qa_agent.db import products as db_products
        if not waitlist_row.url:
            return
        try:
            existing = await db_products.get_by_user_and_url(user_id, waitlist_row.url)
            if existing:
                return
            product_id = await db_products.create(
                user_id=user_id,
                name=waitlist_row.url,
                url=waitlist_row.url,
            )
            if waitlist_row.scan_result:
                await db_products.seed_specs_from_scan(product_id, waitlist_row.scan_result)
        except Exception:
            logger.exception("seed_user_account failed for user=%s", user_id)

    async def grant_tier(self, user_id: str, tier: str = "beta") -> None:
        from qa_agent.db import get_pool
        pool = get_pool()
        if not pool:
            return
        async with pool.acquire() as conn:
            await conn.execute(
                "UPDATE users SET tier = $2 WHERE id = $1::uuid", user_id, tier
            )

    async def revoke_tier(self, user_id: str) -> None:
        await self.grant_tier(user_id, "free")

    async def get_host_summary(self, user_id: str) -> dict | None:
        from qa_agent.db import get_pool
        pool = get_pool()
        if not pool:
            return None
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT
                    COUNT(*)::int AS total_runs,
                    MAX(started_at) AS last_run_at,
                    SUM(CASE WHEN status = 'done' THEN 1 ELSE 0 END)::int AS completed_runs
                FROM jobs WHERE user_id = $1::uuid
                """,
                user_id,
            )
        if not row:
            return None
        return {
            "total_runs": row["total_runs"],
            "completed_runs": row["completed_runs"],
            "last_run_at": row["last_run_at"].isoformat() if row["last_run_at"] else None,
        }

    async def get_user_cost_summary(self, user_id: str) -> CostSummary | None:
        from qa_agent.db import get_pool
        pool = get_pool()
        if not pool:
            return None
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT
                    COALESCE(SUM(cost_usd), 0)::float AS total_usd,
                    COUNT(*)::int AS run_count,
                    MAX(completed_at) AS last_event_at
                FROM jobs WHERE user_id = $1::uuid
                """,
                user_id,
            )
        if not row:
            return None
        return CostSummary(
            total_usd=row["total_usd"],
            breakdown={"runs": row["total_usd"]},
            run_count=row["run_count"],
            last_event_at=row["last_event_at"],
        )
