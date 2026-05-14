"""CRUD for the `specs` table."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from qa_agent.db import get_pool


async def upsert(product_id: str, filename: str, content: str) -> str:
    """Insert or update a spec file. Returns the spec id."""
    pool = get_pool()
    if not pool:
        raise RuntimeError("Database not configured — set DATABASE_URL")
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO specs (product_id, filename, content)
            VALUES ($1::uuid, $2, $3)
            ON CONFLICT (product_id, filename)
            DO UPDATE SET content = EXCLUDED.content, updated_at = now()
            RETURNING id
            """,
            product_id, filename, content,
        )
    return str(row["id"])


async def list_by_product(product_id: str) -> list[dict]:
    pool = get_pool()
    if not pool:
        return []
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM specs WHERE product_id = $1::uuid ORDER BY filename",
            product_id,
        )
    return [_row_to_dict(r) for r in rows]


async def get_by_filename(product_id: str, filename: str) -> dict | None:
    pool = get_pool()
    if not pool:
        return None
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM specs WHERE product_id = $1::uuid AND filename = $2",
            product_id, filename,
        )
    return _row_to_dict(row) if row else None


async def update_content(product_id: str, filename: str, content: str) -> bool:
    pool = get_pool()
    if not pool:
        return False
    async with pool.acquire() as conn:
        result = await conn.execute(
            """
            UPDATE specs SET content = $3, updated_at = now()
            WHERE product_id = $1::uuid AND filename = $2
            """,
            product_id, filename, content,
        )
    return result != "UPDATE 0"


async def set_approved(product_id: str, filename: str, approved: bool) -> bool:
    pool = get_pool()
    if not pool:
        return False
    async with pool.acquire() as conn:
        result = await conn.execute(
            "UPDATE specs SET approved = $3 WHERE product_id = $1::uuid AND filename = $2",
            product_id, filename, approved,
        )
    return result != "UPDATE 0"


async def delete(product_id: str, filename: str) -> bool:
    pool = get_pool()
    if not pool:
        return False
    async with pool.acquire() as conn:
        result = await conn.execute(
            "DELETE FROM specs WHERE product_id = $1::uuid AND filename = $2",
            product_id, filename,
        )
    return result != "DELETE 0"


async def get_files_dict(product_id: str) -> dict[str, str]:
    """Return {filename: content} for all specs of a product — used to materialize to temp dir."""
    pool = get_pool()
    if not pool:
        return {}
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT filename, content FROM specs WHERE product_id = $1::uuid ORDER BY filename",
            product_id,
        )
    return {r["filename"]: r["content"] for r in rows}


def _row_to_dict(row: Any) -> dict:
    d = dict(row)
    d["id"] = str(d["id"])
    if d.get("product_id"):
        d["product_id"] = str(d["product_id"])
    for k in ("created_at", "updated_at"):
        if isinstance(d.get(k), datetime):
            d[k] = d[k].isoformat()
    return d
