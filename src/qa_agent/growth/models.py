"""Pydantic models shared across the growth module."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class ScanIssue(BaseModel):
    severity: Literal["critical", "warning", "info"]
    type: str
    message: str
    location: str | None = None


class MiniScanResult(BaseModel):
    issues: list[ScanIssue]
    page_count: int
    duration_ms: int
    cost_usd: float = 0.0
    full_report_url: str | None = None
    feature_files: dict[str, str] = {}  # filename → gherkin content


class WaitlistEntry(BaseModel):
    id: str
    email: str
    url: str | None
    segment: str | None
    ip: str | None
    submitted_at: datetime

    scan_status: str  # pending|running|done|failed|capped
    scan_started_at: datetime | None
    scan_done_at: datetime | None
    scan_result: MiniScanResult | None
    scan_cost_usd: float | None
    scan_email_sent_at: datetime | None

    invite_status: str  # none|sent|accepted
    invite_sent_at: datetime | None
    invite_user_id: str | None


class EmailCheckResult(BaseModel):
    ok: bool
    reason: str | None = None  # 'disposable' | 'no_mx' | 'invalid'


class RateCheckResult(BaseModel):
    ok: bool
    count: int
    limit: int


class CostSummary(BaseModel):
    total_usd: float
    breakdown: dict[str, float]
    run_count: int = 0
    last_event_at: datetime | None = None


class SegmentRule(BaseModel):
    pattern: str  # regex matched against URL
    segment: str


class SegmentCopy(BaseModel):
    email_subject: str
    email_intro: str
