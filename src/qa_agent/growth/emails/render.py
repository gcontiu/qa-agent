"""Segment-aware email template rendering."""
from __future__ import annotations

import os
import re
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from ..models import MiniScanResult, WaitlistEntry

_TEMPLATES_DIR = Path(__file__).parent / "templates"
_env = Environment(loader=FileSystemLoader(str(_TEMPLATES_DIR)), autoescape=True)


def _domain(url: str | None) -> str:
    if not url:
        return "your site"
    m = re.match(r"https?://([^/]+)", url)
    return m.group(1) if m else url


def render_mini_scan_running(entry: WaitlistEntry) -> tuple[str, str]:
    """Returns (subject, html)."""
    domain = _domain(entry.url)
    subject = f"We're scanning {domain} right now…"
    tmpl = _env.get_template("mini_scan_running.html")
    html = tmpl.render(email=entry.email, url=entry.url, domain=domain)
    return subject, html


def render_invite(entry: WaitlistEntry, magic_link: str) -> tuple[str, str]:
    """Returns (subject, html)."""
    domain = _domain(entry.url)
    subject = "Your Steadra beta access is ready"
    tmpl = _env.get_template("invite.html")
    html = tmpl.render(email=entry.email, domain=domain, magic_link=magic_link)
    return subject, html


def render_reinforce(entry: WaitlistEntry) -> tuple[str, str]:
    domain = _domain(entry.url)
    result = entry.scan_result
    top_issues = (result.issues[:3] if result else [])
    n_issues = len(result.issues) if result else 0
    n_critical = sum(1 for i in (result.issues if result else []) if i.severity == "critical")
    n_warning = sum(1 for i in (result.issues if result else []) if i.severity == "warning")
    subject = f"Still thinking about {domain}? Here's what we found"
    tmpl = _env.get_template("reinforce.html")
    html = tmpl.render(
        email=entry.email, url=entry.url, domain=domain,
        top_issues=top_issues, n_issues=n_issues,
        n_critical=n_critical, n_warning=n_warning,
        app_url=os.getenv("APP_URL", "https://steadra.dev"),
        unsubscribe_url=f"{os.getenv('APP_URL', 'https://steadra.dev')}/unsubscribe",
    )
    return subject, html


def render_beta_check_in(entry: WaitlistEntry) -> tuple[str, str]:
    subject = "How's Steadra working for you?"
    tmpl = _env.get_template("beta_check_in.html")
    html = tmpl.render(
        email=entry.email,
        app_url=os.getenv("APP_URL", "https://steadra.dev"),
        admin_email=os.getenv("ADMIN_EMAIL", "hello@steadra.dev"),
        unsubscribe_url=f"{os.getenv('APP_URL', 'https://steadra.dev')}/unsubscribe",
    )
    return subject, html


def render_cohort_report(
    entry: WaitlistEntry,
    total_runs: int = 0,
    issues_found: int = 0,
    cost_usd: float = 0.0,
) -> tuple[str, str]:
    domain = _domain(entry.url)
    subject = f"Your 30-day Steadra summary for {domain}"
    tmpl = _env.get_template("cohort_report.html")
    html = tmpl.render(
        email=entry.email, domain=domain,
        total_runs=total_runs, issues_found=issues_found, cost_usd=cost_usd,
        app_url=os.getenv("APP_URL", "https://steadra.dev"),
        unsubscribe_url=f"{os.getenv('APP_URL', 'https://steadra.dev')}/unsubscribe",
    )
    return subject, html


def render_mini_scan_results(
    entry: WaitlistEntry,
    result: MiniScanResult,
    segment: str | None,
) -> tuple[str, str]:
    """Returns (subject, html)."""
    domain = _domain(entry.url)
    n = len(result.issues)
    subject = f"Your site looks clean ✓ — {domain}" if n == 0 else f"We found {n} issue{'s' if n != 1 else ''} on {domain}"
    tmpl = _env.get_template("mini_scan_results.html")
    html = tmpl.render(
        email=entry.email,
        url=entry.url,
        domain=domain,
        result=result,
        segment=segment or "default",
        n=n,
    )
    return subject, html
