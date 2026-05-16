"""
LogSink — thin abstraction for emitting log events during analyst/executor runs.

Two concrete implementations:
  ConsoleSink  — wraps Rich; no change to CLI UX
  BufferSink   — appends {"ts": float, "msg": str} to an in-memory list (for API)
"""
from __future__ import annotations

import time
from typing import Protocol, runtime_checkable

_MAX_EVENTS = 500


@runtime_checkable
class LogSink(Protocol):
    def emit(self, msg: str) -> None: ...


class ConsoleSink:
    """Forwards log events to a Rich Console (CLI use)."""

    def __init__(self, console) -> None:
        self._console = console

    def emit(self, msg: str) -> None:
        self._console.print(f"  [dim]{msg}[/dim]")


class BufferSink:
    """Accumulates log events in memory for the HTTP API to serve."""

    def __init__(self, target: list) -> None:
        self._target = target

    def emit(self, msg: str) -> None:
        if len(self._target) >= _MAX_EVENTS:
            excess = len(self._target) - _MAX_EVENTS // 2
            del self._target[:excess]
            self._target.insert(0, {"ts": time.time(), "msg": f"… {excess} earlier events truncated"})
        self._target.append({"ts": time.time(), "msg": msg})


def _humanize_tool_call(name: str, args: dict) -> str | None:
    """Convert a browser tool call name+args into a human-readable log message.

    Returns None for calls not worth surfacing in the UI.
    """
    if name == "browser_navigate":
        return f"Navigating to {args.get('url', '?')}"
    if name == "browser_snapshot":
        return "Reading page content"
    if name == "browser_click":
        target = args.get("element") or args.get("target") or args.get("ref") or "element"
        if len(str(target)) > 40:
            target = str(target)[:40] + "…"
        return f"Clicking {target!r}"
    if name == "browser_type":
        target = args.get("element") or args.get("target") or "field"
        if len(str(target)) > 40:
            target = str(target)[:40] + "…"
        return f"Typing into {target!r}"
    if name == "browser_fill_form":
        return "Filling form"
    if name == "browser_press_key":
        return f"Pressing {args.get('key', '?')!r}"
    if name == "browser_select_option":
        target = args.get("element") or args.get("target") or "element"
        return f"Selecting option on {target!r}"
    if name == "browser_wait_for":
        return "Waiting for page"
    if name == "browser_scroll":
        return "Scrolling page"
    return None
