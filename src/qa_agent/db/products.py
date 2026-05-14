"""CRUD for the `products` table."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from qa_agent.db import get_pool


async def create(name: str, url: str, description: str | None = None, user_id: str | None = None) -> str:
    pool = get_pool()
    if not pool:
        raise RuntimeError("Database not configured — set DATABASE_URL")
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO products (user_id, name, url, description)
            VALUES ($1::uuid, $2, $3, $4)
            RETURNING id
            """,
            user_id, name, url, description,
        )
    return str(row["id"])


async def get(product_id: str) -> dict | None:
    pool = get_pool()
    if not pool:
        return None
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM products WHERE id = $1::uuid", product_id
        )
    return _row_to_dict(row) if row else None


async def list_all() -> list[dict]:
    pool = get_pool()
    if not pool:
        return []
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT * FROM products ORDER BY created_at DESC")
    return [_row_to_dict(r) for r in rows]


def _row_to_dict(row: Any) -> dict:
    d = dict(row)
    d["id"] = str(d["id"])
    if d.get("user_id"):
        d["user_id"] = str(d["user_id"])
    if isinstance(d.get("created_at"), datetime):
        d["created_at"] = d["created_at"].isoformat()
    return d
