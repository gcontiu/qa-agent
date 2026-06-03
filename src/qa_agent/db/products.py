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


async def get(product_id: str, user_id: str | None = None) -> dict | None:
    pool = get_pool()
    if not pool:
        return None
    async with pool.acquire() as conn:
        if user_id:
            row = await conn.fetchrow(
                "SELECT * FROM products WHERE id = $1::uuid AND user_id = $2::uuid",
                product_id, user_id,
            )
        else:
            row = await conn.fetchrow(
                "SELECT * FROM products WHERE id = $1::uuid", product_id
            )
    return _row_to_dict(row) if row else None


async def list_all(user_id: str | None = None) -> list[dict]:
    pool = get_pool()
    if not pool:
        return []
    async with pool.acquire() as conn:
        if user_id:
            rows = await conn.fetch(
                "SELECT * FROM products WHERE user_id = $1::uuid ORDER BY created_at DESC",
                user_id,
            )
        else:
            rows = await conn.fetch("SELECT * FROM products ORDER BY created_at DESC")
    return [_row_to_dict(r) for r in rows]


async def get_by_user_and_url(user_id: str, url: str) -> dict | None:
    pool = get_pool()
    if not pool:
        return None
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM products WHERE user_id = $1::uuid AND url = $2",
            user_id, url,
        )
    return _row_to_dict(row) if row else None


async def seed_specs_from_scan(product_id: str, scan_result: Any) -> int:
    """Insert feature files from a mini-scan into the specs table. Returns count inserted."""
    feature_files = getattr(scan_result, "feature_files", {}) or {}
    if not feature_files:
        return 0
    pool = get_pool()
    if not pool:
        return 0
    count = 0
    async with pool.acquire() as conn:
        for filename, content in feature_files.items():
            await conn.execute(
                """
                INSERT INTO specs (product_id, filename, content)
                VALUES ($1::uuid, $2, $3)
                ON CONFLICT (product_id, filename) DO UPDATE SET content = EXCLUDED.content
                """,
                product_id, filename, content,
            )
            count += 1
    return count


def _row_to_dict(row: Any) -> dict:
    d = dict(row)
    d["id"] = str(d["id"])
    if d.get("user_id"):
        d["user_id"] = str(d["user_id"])
    if isinstance(d.get("created_at"), datetime):
        d["created_at"] = d["created_at"].isoformat()
    # active defaults to True if the column hasn't been migrated yet
    d.setdefault("active", True)
    return d
