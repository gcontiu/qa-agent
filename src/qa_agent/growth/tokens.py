"""Signed tokens for public-facing growth flows (e.g. beta claim links)."""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
import time


def _secret() -> bytes:
    key = os.getenv("CLAIM_TOKEN_SECRET") or os.getenv("SUPABASE_SERVICE_ROLE_KEY", "dev-secret")
    return key.encode()


def make_claim_token(waitlist_id: str) -> str:
    """Return a URL-safe signed token encoding waitlist_id + timestamp."""
    ts = str(int(time.time()))
    payload = f"{waitlist_id}:{ts}"
    sig = hmac.new(_secret(), payload.encode(), hashlib.sha256).hexdigest()
    raw = f"{payload}:{sig}"
    return base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")


def verify_claim_token(token: str, max_age_seconds: int = 7 * 86400) -> str:
    """Verify token and return waitlist_id. Raises ValueError on failure."""
    try:
        padded = token + "=" * (-len(token) % 4)
        raw = base64.urlsafe_b64decode(padded).decode()
        waitlist_id, ts, sig = raw.rsplit(":", 2)
    except Exception:
        raise ValueError("malformed token")

    age = int(time.time()) - int(ts)
    if age < 0 or age > max_age_seconds:
        raise ValueError("token expired")

    expected = hmac.new(_secret(), f"{waitlist_id}:{ts}".encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, sig):
        raise ValueError("invalid signature")

    return waitlist_id
