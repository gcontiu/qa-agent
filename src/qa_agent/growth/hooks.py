"""FunnelHooks — project-specific extension points.

Growth calls these but never imports host-app code directly.
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable

from .models import MiniScanResult, WaitlistEntry, CostSummary


@runtime_checkable
class FunnelHooks(Protocol):
    async def run_mini_scan(self, email: str, url: str) -> MiniScanResult:
        """Produce the value delivered in the activation email."""
        ...

    async def seed_user_account(self, user_id: str, waitlist_row: WaitlistEntry) -> None:
        """Called once when a beta user signs in for the first time. Must be idempotent."""
        ...

    async def grant_tier(self, user_id: str, tier: str = "beta") -> None:
        """Mark the user as beta-enrolled in the host's auth/tier system."""
        ...

    async def revoke_tier(self, user_id: str) -> None:
        """Called on beta expiry. Host decides what 'expired' means."""
        ...

    # Optional hooks — growth degrades gracefully if not implemented

    async def get_host_summary(self, user_id: str) -> dict | None:
        """Arbitrary key/value host-domain data for the per-user timeline."""
        return None

    async def get_user_cost_summary(self, user_id: str) -> CostSummary | None:
        """Host-side accumulated cost for a beta user."""
        return None
