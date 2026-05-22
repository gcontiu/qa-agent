"""
Diagnostic script: test DeterministicScanner via real Playwright MCP, zero LLM cost.

Navigates to known-broken pages and checks if scanner picks up console errors
and network failures. Prints all raw MCP output + scanner findings.

Usage:
    uv run python scripts/test_scanner_mcp.py
"""
from __future__ import annotations

import asyncio
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

sys.path.insert(0, "src")
from qa_agent.issues import BufferingIssueSink, DeterministicScanner

TEST_URLS = [
    "https://the-internet.herokuapp.com/javascript_error",
    "https://the-internet.herokuapp.com/broken_images",
    "https://the-internet.herokuapp.com/status_codes/404",
]

SERVER_PARAMS = StdioServerParameters(
    command="npx",
    args=["@playwright/mcp", "--headless", "--isolated", "--browser=chromium"],
)


async def call(session: ClientSession, tool: str, args: dict) -> str:
    result = await session.call_tool(tool, args)
    return "\n".join(c.text for c in result.content if hasattr(c, "text"))


async def main() -> None:
    print("=== Playwright MCP Scanner Diagnostic ===\n")

    async with stdio_client(SERVER_PARAMS) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            tools = await session.list_tools()
            tool_names = {t.name for t in tools.tools}
            print(f"Available tools ({len(tool_names)}):")
            for name in sorted(tool_names):
                print(f"  {name}")
            print()

            has_console = "browser_console_messages" in tool_names
            has_network = "browser_network_requests" in tool_names
            print(f"browser_console_messages: {'✓' if has_console else '✗ MISSING'}")
            print(f"browser_network_requests: {'✓' if has_network else '✗ MISSING'}")
            print()

            if not has_console and not has_network:
                print("ERROR: Neither diagnostic tool is available. Scanner cannot work.")
                print("This is the root cause — these tools are not exposed by this MCP version.")
                return

            scanner = DeterministicScanner()
            sink = BufferingIssueSink()

            for url in TEST_URLS:
                print(f"{'='*60}")
                print(f"URL: {url}")
                print(f"{'='*60}")

                nav_out = await call(session, "browser_navigate", {"url": url})
                print(f"[navigate] {len(nav_out)} chars")

                if has_console:
                    console_out = await call(session, "browser_console_messages", {})
                    print(f"\n[browser_console_messages] raw output ({len(console_out)} chars):")
                    print(console_out[:1000] if console_out.strip() else "  (empty)")
                    issues_before = len(sink)
                    scanner.ingest_console(url, console_out, sink)
                    print(f"→ scanner found {len(sink) - issues_before} new issue(s) from console")
                else:
                    print("[browser_console_messages] SKIPPED — tool not available")

                if has_network:
                    network_out = await call(session, "browser_network_requests", {})
                    print(f"\n[browser_network_requests] raw output ({len(network_out)} chars):")
                    print(network_out[:1000] if network_out.strip() else "  (empty)")
                    issues_before = len(sink)
                    scanner.ingest_network(url, network_out, sink)
                    print(f"→ scanner found {len(sink) - issues_before} new issue(s) from network")
                else:
                    print("[browser_network_requests] SKIPPED — tool not available")

                print()

            print(f"{'='*60}")
            print(f"TOTAL ISSUES FOUND: {len(sink)}")
            print(f"{'='*60}")
            for issue in sink.finalize():
                print(f"  [{issue.severity.upper()}] {issue.type} @ {issue.url}")
                print(f"    {issue.message}")


if __name__ == "__main__":
    asyncio.run(main())
