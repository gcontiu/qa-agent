"""
Issue detection — collects technical problems found during analyst crawl.

Two collection paths:
  DeterministicScanner — calls browser_console_messages + browser_network_requests
                         MCP tools after each navigation; no LLM tokens consumed.
  report_issue tool    — LLM-reported semantic issues (button doesn't respond, etc.)

IssueSink (Protocol) mirrors LogSink: thin, injectable, testable.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Literal, Protocol, runtime_checkable

IssueType = Literal[
    "console_error",
    "console_warning",
    "network_5xx",
    "network_4xx",
    "broken_link",
    "flow_stuck",
    "semantic",
]

Severity = Literal["high", "medium", "low"]

_SEVERITY_RANK: dict[str, int] = {"low": 0, "medium": 1, "high": 2}

# Analytics/tracking domains to ignore in network scans
_NOISE_DOMAINS = re.compile(
    r'(google-analytics|gtm\.js|googletagmanager|facebook\.net|hotjar|clarity\.ms'
    r'|doubleclick|adnxs|googlesyndication|cdn\.cookielaw|sentry\.io)',
    re.IGNORECASE,
)

# Console lines to ignore (framework noise)
_CONSOLE_NOISE = re.compile(
    r'(Download the React DevTools|\[HMR\]|\[vite\]|favicon\.ico'
    r'|Google Tag Manager|__webpack_hmr)',
    re.IGNORECASE,
)


@dataclass
class Issue:
    type: IssueType
    severity: Severity
    url: str
    message: str
    details: dict = field(default_factory=dict)
    fingerprint: str = field(default="")

    def __post_init__(self) -> None:
        if not self.fingerprint:
            self.fingerprint = _make_fingerprint(self.type, self.url, self.message)


def _make_fingerprint(type: str, url: str, message: str) -> str:
    """Stable 12-char hash for deduplication across runs."""
    # Normalize URL: strip query string + replace UUIDs with {id}
    norm_url = re.sub(r'\?.*$', '', url)
    norm_url = re.sub(
        r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}',
        '{id}', norm_url, flags=re.IGNORECASE,
    )
    norm_url = re.sub(r'/\d+(?=/|$)', '/{n}', norm_url)
    norm_msg = message[:120]
    raw = f"{type}:{norm_url}:{norm_msg}"
    return hashlib.sha1(raw.encode()).hexdigest()[:12]


@runtime_checkable
class IssueSink(Protocol):
    def add(self, issue: Issue) -> None: ...


class BufferingIssueSink:
    """
    Collects issues, deduplicates by fingerprint.
    Severity is escalated if the same fingerprint is seen again with higher severity.
    """

    def __init__(self) -> None:
        self._by_fp: dict[str, Issue] = {}

    def add(self, issue: Issue) -> None:
        fp = issue.fingerprint
        existing = self._by_fp.get(fp)
        if existing is None or _SEVERITY_RANK[issue.severity] > _SEVERITY_RANK[existing.severity]:
            self._by_fp[fp] = issue

    def finalize(self) -> list[Issue]:
        return list(self._by_fp.values())

    def __len__(self) -> int:
        return len(self._by_fp)


class DeterministicScanner:
    """
    Parses raw text output from browser_console_messages and browser_network_requests
    MCP tools, emitting Issue objects into a sink.

    Instantiate once per analyst session; call ingest_console() / ingest_network()
    after each browser_navigate result.
    """

    def ingest_console(self, current_url: str, result_text: str, sink: IssueSink) -> None:
        for line in result_text.splitlines():
            line = line.strip()
            if not line or _CONSOLE_NOISE.search(line):
                continue
            lower = line.lower()
            if 'error' in lower or 'uncaught' in lower or 'exception' in lower:
                sink.add(Issue(
                    type="console_error",
                    severity="high",
                    url=current_url,
                    message=line[:200],
                    details={"raw": line},
                ))
            elif 'warning' in lower or 'warn' in lower:
                sink.add(Issue(
                    type="console_warning",
                    severity="low",
                    url=current_url,
                    message=line[:200],
                    details={"raw": line},
                ))

    def ingest_network(self, current_url: str, result_text: str, sink: IssueSink) -> None:
        for line in result_text.splitlines():
            line = line.strip()
            if not line or _NOISE_DOMAINS.search(line):
                continue
            match = re.search(r'\b([45]\d{2})\b', line)
            if not match:
                continue
            status = int(match.group(1))
            if status >= 500:
                sink.add(Issue(
                    type="network_5xx",
                    severity="high",
                    url=current_url,
                    message=f"HTTP {status}: {line[:120]}",
                    details={"status": status, "raw": line},
                ))
            elif status >= 400:
                sink.add(Issue(
                    type="network_4xx",
                    severity="medium",
                    url=current_url,
                    message=f"HTTP {status}: {line[:120]}",
                    details={"status": status, "raw": line},
                ))

    @staticmethod
    def from_report_issue_args(url: str, args: dict) -> Issue:
        """Convert a report_issue tool call args dict into an Issue."""
        severity: Severity = args.get("severity", "medium")
        if severity not in ("high", "medium", "low"):
            severity = "medium"
        expected = args.get("expected", "")
        actual = args.get("actual", "")
        message = args.get("message", "")[:200]
        details: dict = {}
        if expected:
            details["expected"] = expected
        if actual:
            details["actual"] = actual
        return Issue(
            type="semantic",
            severity=severity,
            url=url or args.get("url", ""),
            message=message,
            details=details,
        )


def issues_to_dicts(issues: list[Issue]) -> list[dict]:
    return [
        {
            "type": i.type,
            "severity": i.severity,
            "url": i.url,
            "message": i.message,
            "details": i.details,
            "fingerprint": i.fingerprint,
        }
        for i in issues
    ]
