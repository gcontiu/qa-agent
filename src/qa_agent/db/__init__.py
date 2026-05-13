"""
Postgres connection pool for qa-agent.

Graceful degradation: if DATABASE_URL is not set, all functions are no-ops
and the caller falls back to in-memory / filesystem state. This preserves
backward compatibility for local development without a database.

Usage:
    await db.init()          # call once at FastAPI startup
    pool = db.get_pool()     # None if no DATABASE_URL
    await db.close()         # call at FastAPI shutdown
"""
from __future__ import annotations

import asyncpg  # type: ignore
import os

_pool: asyncpg.Pool | None = None


async def init() -> None:
    """Create the connection pool. No-op if DATABASE_URL is unset."""
    global _pool
    url = os.getenv("DATABASE_URL")
    if not url:
        return
    _pool = await asyncpg.create_pool(
        url,
        min_size=1,
        max_size=5,
        command_timeout=10,
        # Supabase requires SSL
        ssl="require",
    )


async def close() -> None:
    """Close the connection pool. No-op if pool was never created."""
    global _pool
    if _pool:
        await _pool.close()
        _pool = None


def get_pool() -> asyncpg.Pool | None:
    """Return the active pool, or None if database is not configured."""
    return _pool


def is_configured() -> bool:
    return _pool is not None
