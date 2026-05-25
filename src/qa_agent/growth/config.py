"""FunnelConfig — all dials in one place."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta

from .models import SegmentRule, SegmentCopy


@dataclass
class FunnelConfig:
    cohort_monthly_cap: int = 50
    daily_scan_cap: int = 20
    ip_rate_limit_per_hour: int = 3
    beta_duration_days: int = 30
    mini_scan_wall_time_seconds: int = 60

    drip_schedule: dict[str, timedelta] = field(default_factory=lambda: {
        "mini_scan_running":  timedelta(seconds=0),
        "mini_scan_results":  timedelta(minutes=10),
        "invite":             timedelta(hours=24),
        "reinforce":          timedelta(days=3),
        "beta_check_in":      timedelta(days=14),
        "cohort_report":      timedelta(days=30),
    })

    segment_rules: list[SegmentRule] = field(default_factory=lambda: [
        SegmentRule(pattern=r"shopify\.com|woocommerce|myshopify", segment="ecommerce"),
        SegmentRule(pattern=r"saas|app\.|dashboard\.|platform\.", segment="saas"),
        SegmentRule(pattern=r"agency|studio|digital|creative", segment="agency"),
    ])

    segment_copy: dict[str, SegmentCopy] = field(default_factory=lambda: {
        "ecommerce": SegmentCopy(
            email_subject="We found {n} issues on your store",
            email_intro="E-commerce sites lose revenue with every checkout bug.",
        ),
        "saas": SegmentCopy(
            email_subject="We found {n} issues on {domain}",
            email_intro="Your users hit these bugs every time they log in.",
        ),
        "agency": SegmentCopy(
            email_subject="We found {n} issues on {domain}",
            email_intro="Here's what we found — before your client does.",
        ),
        "default": SegmentCopy(
            email_subject="We found {n} issues on {domain}",
            email_intro="Here's what Steadra found on your site.",
        ),
    })

    founder_notify_channel: str = "#signups"
    admin_email: str = ""
