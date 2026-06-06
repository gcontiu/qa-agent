"""Anti-abuse stack: MX check, disposable blocklist, IP rate-limit, Turnstile, composite."""
from __future__ import annotations

import asyncio
import logging
import os
import re
import time
from collections import defaultdict
from typing import Protocol

logger = logging.getLogger(__name__)

import dns.resolver  # type: ignore
import httpx

from ...models import EmailCheckResult, RateCheckResult


# ---------------------------------------------------------------------------
# Protocols
# ---------------------------------------------------------------------------

class AntiAbuseGuard(Protocol):
    async def verify_token(self, token: str, remote_ip: str) -> bool: ...
    async def check_email(self, email: str) -> EmailCheckResult: ...
    async def check_ip_rate(self, ip: str) -> RateCheckResult: ...


# ---------------------------------------------------------------------------
# MX check
# ---------------------------------------------------------------------------

class MXCheck:
    async def verify_token(self, token: str, remote_ip: str) -> bool:
        return True  # not responsible for token

    async def check_email(self, email: str) -> EmailCheckResult:
        domain = email.rsplit("@", 1)[-1]
        try:
            loop = asyncio.get_event_loop()
            records = await loop.run_in_executor(
                None, lambda: dns.resolver.resolve(domain, "MX")
            )
            if records:
                return EmailCheckResult(ok=True)
        except Exception:
            logger.debug("MX check failed for domain=%s", domain, exc_info=True)
        return EmailCheckResult(ok=False, reason="no_mx")

    async def check_ip_rate(self, ip: str) -> RateCheckResult:
        return RateCheckResult(ok=True, count=0, limit=99)


# ---------------------------------------------------------------------------
# Disposable domain blocklist (in-memory, seeded from env or hardcoded list)
# ---------------------------------------------------------------------------

_DISPOSABLE_DOMAINS: set[str] = {
    "mailinator.com", "guerrillamail.com", "tempmail.com",
    "throwam.com", "yopmail.com", "sharklasers.com",
    "10minutemail.com", "trashmail.com", "fakeinbox.com",
    "dispostable.com", "maildrop.cc", "getnada.com",
}


class DisposableBlocklist:
    def __init__(self, extra_domains: set[str] | None = None) -> None:
        self._blocked = _DISPOSABLE_DOMAINS | (extra_domains or set())

    async def verify_token(self, token: str, remote_ip: str) -> bool:
        return True

    async def check_email(self, email: str) -> EmailCheckResult:
        domain = email.rsplit("@", 1)[-1].lower()
        if domain in self._blocked:
            return EmailCheckResult(ok=False, reason="disposable")
        return EmailCheckResult(ok=True)

    async def check_ip_rate(self, ip: str) -> RateCheckResult:
        return RateCheckResult(ok=True, count=0, limit=99)


# ---------------------------------------------------------------------------
# In-memory IP rate limiter (per-hour sliding window)
# ---------------------------------------------------------------------------

class IPRateLimit:
    def __init__(self, limit_per_hour: int = 3) -> None:
        self._limit = limit_per_hour
        self._hits: dict[str, list[float]] = defaultdict(list)

    async def verify_token(self, token: str, remote_ip: str) -> bool:
        return True

    async def check_email(self, email: str) -> EmailCheckResult:
        return EmailCheckResult(ok=True)

    async def check_ip_rate(self, ip: str) -> RateCheckResult:
        now = time.time()
        window = 3600.0
        self._hits[ip] = [t for t in self._hits[ip] if now - t < window]
        count = len(self._hits[ip])
        if count >= self._limit:
            return RateCheckResult(ok=False, count=count, limit=self._limit)
        self._hits[ip].append(now)
        return RateCheckResult(ok=True, count=count + 1, limit=self._limit)


# ---------------------------------------------------------------------------
# Cloudflare Turnstile
# ---------------------------------------------------------------------------

class TurnstileGuard:
    def __init__(self, secret: str) -> None:
        self._secret = secret

    async def verify_token(self, token: str, remote_ip: str) -> bool:
        if not token:
            return False
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                "https://challenges.cloudflare.com/turnstile/v0/siteverify",
                data={
                    "secret": self._secret,
                    "response": token,
                    "remoteip": remote_ip,
                },
                timeout=10,
            )
        data = resp.json()
        return bool(data.get("success"))

    async def check_email(self, email: str) -> EmailCheckResult:
        return EmailCheckResult(ok=True)

    async def check_ip_rate(self, ip: str) -> RateCheckResult:
        return RateCheckResult(ok=True, count=0, limit=99)


# ---------------------------------------------------------------------------
# No-op guard (dev / test)
# ---------------------------------------------------------------------------

class NoopGuard:
    async def verify_token(self, token: str, remote_ip: str) -> bool:
        return True

    async def check_email(self, email: str) -> EmailCheckResult:
        return EmailCheckResult(ok=True)

    async def check_ip_rate(self, ip: str) -> RateCheckResult:
        return RateCheckResult(ok=True, count=1, limit=3)


# ---------------------------------------------------------------------------
# Composite — chains all guards, returns strictest verdict
# ---------------------------------------------------------------------------

class CompositeGuard:
    def __init__(self, *guards: AntiAbuseGuard) -> None:
        self._guards = guards

    async def verify_token(self, token: str, remote_ip: str) -> bool:
        results = await asyncio.gather(
            *[g.verify_token(token, remote_ip) for g in self._guards],
            return_exceptions=True,
        )
        return all(r is True for r in results)

    async def check_email(self, email: str) -> EmailCheckResult:
        results = await asyncio.gather(
            *[g.check_email(email) for g in self._guards],
            return_exceptions=True,
        )
        for r in results:
            if isinstance(r, EmailCheckResult) and not r.ok:
                return r
        return EmailCheckResult(ok=True)

    async def check_ip_rate(self, ip: str) -> RateCheckResult:
        results = await asyncio.gather(
            *[g.check_ip_rate(ip) for g in self._guards],
            return_exceptions=True,
        )
        for r in results:
            if isinstance(r, RateCheckResult) and not r.ok:
                return r
        # Return the most restrictive count
        counts = [r for r in results if isinstance(r, RateCheckResult)]
        if counts:
            return max(counts, key=lambda r: r.count)
        return RateCheckResult(ok=True, count=0, limit=99)


def from_env(ip_limit: int = 3) -> AntiAbuseGuard:
    guards: list[AntiAbuseGuard] = [IPRateLimit(limit_per_hour=ip_limit), DisposableBlocklist(), MXCheck()]
    turnstile_secret = os.getenv("TURNSTILE_SECRET")
    if turnstile_secret:
        guards.append(TurnstileGuard(secret=turnstile_secret))
    return CompositeGuard(*guards)
