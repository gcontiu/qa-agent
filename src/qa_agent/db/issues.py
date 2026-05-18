"""CRUD for the `issues` table."""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from qa_agent.db import get_pool


async def bulk_upsert(product_id: str, issues: list[dict]) -> int:
    """
    Upsert issues by (product_id, fingerprint).
    On conflict: update last_seen_at, increment occurrences, escalate severity if higher.
    Returns count of rows processed.
    """
    if not issues:
        return 0
    pool = get_pool()
    if not pool:
        return 0
    async with pool.acquire() as conn:
        for issue in issues:
            await conn.execute(
                """
                INSERT INTO issues
                    (product_id, fingerprint, type, severity, url, message, details)
                VALUES
                    ($1::uuid, $2, $3, $4, $5, $6, $7::jsonb)
                ON CONFLICT (product_id, fingerprint) DO UPDATE SET
                    last_seen_at = now(),
                    occurrences  = issues.occurrences + 1,
                    severity     = CASE
                        WHEN (
                            ARRAY_POSITION(ARRAY['low','medium','high'], EXCLUDED.severity) >
                            ARRAY_POSITION(ARRAY['low','medium','high'], issues.severity)
                        ) THEN EXCLUDED.severity
                        ELSE issues.severity
                    END,
                    message      = EXCLUDED.message,
                    details      = EXCLUDED.details
                """,
                product_id,
                issue["fingerprint"],
                issue["type"],
                issue["severity"],
                issue["url"],
                issue["message"],
                json.dumps(issue.get("details", {})),
            )
    return len(issues)


async def list_by_product(
    product_id: str,
    status: str | None = None,
    severity: str | None = None,
) -> list[dict]:
    pool = get_pool()
    if not pool:
        return []
    conditions = ["product_id = $1::uuid"]
    params: list[Any] = [product_id]
    if status:
        params.append(status)
        conditions.append(f"status = ${len(params)}")
    if severity:
        params.append(severity)
        conditions.append(f"severity = ${len(params)}")
    where = " AND ".join(conditions)
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            f"""
            SELECT * FROM issues
            WHERE {where}
            ORDER BY
                ARRAY_POSITION(ARRAY['high','medium','low'], severity),
                last_seen_at DESC
            """,
            *params,
        )
    return [_row_to_dict(r) for r in rows]


async def update_status(product_id: str, issue_id: str, status: str) -> bool:
    pool = get_pool()
    if not pool:
        return False
    async with pool.acquire() as conn:
        result = await conn.execute(
            "UPDATE issues SET status = $3 WHERE product_id = $1::uuid AND id = $2::uuid",
            product_id, issue_id, status,
        )
    return result != "UPDATE 0"


async def summary(product_id: str) -> dict:
    """Return count breakdown by severity for open issues."""
    pool = get_pool()
    if not pool:
        return {"total": 0, "high": 0, "medium": 0, "low": 0}
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT severity, COUNT(*) AS cnt
            FROM issues
            WHERE product_id = $1::uuid AND status = 'open'
            GROUP BY severity
            """,
            product_id,
        )
    counts = {r["severity"]: r["cnt"] for r in rows}
    total = sum(counts.values())
    return {
        "total": total,
        "high": counts.get("high", 0),
        "medium": counts.get("medium", 0),
        "low": counts.get("low", 0),
    }


def _row_to_dict(row: Any) -> dict:
    d = dict(row)
    d["id"] = str(d["id"])
    if d.get("product_id"):
        d["product_id"] = str(d["product_id"])
    for k in ("first_seen_at", "last_seen_at"):
        if isinstance(d.get(k), datetime):
            d[k] = d[k].isoformat()
    if isinstance(d.get("details"), str):
        try:
            d["details"] = json.loads(d["details"])
        except Exception:
            pass
    return d
