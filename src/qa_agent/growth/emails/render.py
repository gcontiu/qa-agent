"""Segment-aware email template rendering."""
from __future__ import annotations

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


def render_mini_scan_results(
    entry: WaitlistEntry,
    result: MiniScanResult,
    segment: str | None,
) -> tuple[str, str]:
    """Returns (subject, html)."""
    domain = _domain(entry.url)
    n = len(result.issues)
    subject = f"We found {n} issue{'s' if n != 1 else ''} on {domain}"
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
