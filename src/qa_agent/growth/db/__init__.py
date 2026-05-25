"""Growth module DB — thin wrapper around the shared asyncpg pool."""
from __future__ import annotations

import asyncpg  # type: ignore

_pool: asyncpg.Pool | None = None


def set_pool(pool: asyncpg.Pool | None) -> None:
    global _pool
    _pool = pool


def get_pool() -> asyncpg.Pool | None:
    return _pool
