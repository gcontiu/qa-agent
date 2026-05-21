"""
Analyst role — crawls a product site and auto-generates Gherkin feature files.

Flow:
  1. LLM navigates the site using Playwright MCP browser tools.
  2. LLM calls write_feature_file() for each page it covers.
  3. LLM calls finish_analysis() to signal completion.
  4. Python writes the generated files to disk.

Usage (CLI):
  uv run qa-agent analyze --url https://example.com --description "B2B SaaS dashboard" \\
      --prefix EX --output specs/example
"""
import asyncio
import json
import re
import time
from pathlib import Path

from mcp import ClientSession
from mcp.client.stdio import stdio_client
from rich.console import Console
from rich.panel import Panel

from qa_agent.agent import _make_server_params
from qa_agent import browserbase
from qa_agent.llm import LLMConfig, complete, ensure_provider_running, estimate_cost
from qa_agent.log_sink import LogSink, _humanize_tool_call
from qa_agent.issues import (
    BufferingIssueSink, DeterministicScanner, Issue, IssueSink, issues_to_dicts,
)

PROMPTS_DIR = Path(__file__).parent / "prompts"
MAX_TURNS = 50  # Analyst needs more turns to crawl a full site

# ---------------------------------------------------------------------------
# Custom tool definitions (not MCP — handled in Python)
# ---------------------------------------------------------------------------

_WRITE_TOOL: dict = {
    "type": "function",
    "function": {
        "name": "write_feature_file",
        "description": (
            "Write a Gherkin feature file (or config.yaml) to the output spec directory. "
            "Call once per file. Calling again with the same filename overwrites it."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "filename": {
                    "type": "string",
                    "description": "Filename with extension, e.g. 'homepage.feature' or 'config.yaml'. No path separators.",
                },
                "content": {
                    "type": "string",
                    "description": "Full file content as a string.",
                },
            },
            "required": ["filename", "content"],
        },
    },
}

_FINISH_TOOL: dict = {
    "type": "function",
    "function": {
        "name": "finish_analysis",
        "description": (
            "Call this when you have written all feature files and config.yaml. "
            "Signals the end of analysis — do not call any tools after this."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "summary": {
                    "type": "string",
                    "description": "Brief summary of pages discovered and files written.",
                },
                "file_count": {
                    "type": "integer",
                    "description": "Total number of files written (including config.yaml).",
                },
            },
            "required": ["summary", "file_count"],
        },
    },
}

_REPORT_ISSUE_TOOL: dict = {
    "type": "function",
    "function": {
        "name": "report_issue",
        "description": (
            "Report a UX or functional problem you observe during exploration. "
            "Use for things like: a button that does nothing when clicked, a form "
            "that shows a generic error, a page that never finishes loading, or "
            "broken layouts. Do NOT use for JavaScript console errors or HTTP failures "
            "— those are captured automatically."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "The page URL where the issue was observed.",
                },
                "severity": {
                    "type": "string",
                    "enum": ["high", "medium", "low"],
                    "description": "high = blocks core user flow; medium = degrades UX; low = cosmetic.",
                },
                "message": {
                    "type": "string",
                    "description": "Concise description of the problem (max 200 chars).",
                },
                "expected": {
                    "type": "string",
                    "description": "What should have happened.",
                },
                "actual": {
                    "type": "string",
                    "description": "What actually happened.",
                },
            },
            "required": ["url", "severity", "message"],
        },
    },
}


# ---------------------------------------------------------------------------
# Prompt helpers
# ---------------------------------------------------------------------------

def _system_prompt() -> str:
    return (PROMPTS_DIR / "analyst_system.md").read_text()


def _truncate_gherkin(content: str, max_scenarios: int) -> str:
    """Hard-cap a .feature file to at most max_scenarios Scenario blocks."""
    pattern = re.compile(r'(?=^\s*Scenario(?:\s+Outline)?:)', re.MULTILINE)
    parts = pattern.split(content)
    if len(parts) <= 1 + max_scenarios:
        return content
    return (parts[0] + ''.join(parts[1:1 + max_scenarios])).rstrip() + '\n'


def _user_message(url: str, description: str, spec_prefix: str, output_dir: str, pages: list[str] | None = None, max_scenarios_per_file: int | None = None) -> str:
    scenario_cap_line = (
        f"IMPORTANT: Write at most {max_scenarios_per_file} Scenario(s) per feature file.\n\n"
        if max_scenarios_per_file else ""
    )
    base = (
        f"Product URL: {url}\n"
        f"Product description: {description}\n"
        f"Scenario ID prefix: {spec_prefix}\n"
        f"Output directory: {output_dir}\n\n"
        f"{scenario_cap_line}"
    )
    if pages:
        paths_block = "\n".join(f"  - {p}" for p in pages)
        scope_yaml = "    pages:\n" + "\n".join(f'      - "{p}"' for p in pages)
        return base + (
            f"EXPLORE_ONLY — visit exactly these paths and no others:\n{paths_block}\n\n"
            f"For each path: navigate → snapshot → write one feature file → move to next.\n"
            f"In config.yaml, add this under `meta:`:\n  scope:\n{scope_yaml}\n\n"
            f"Call finish_analysis() when all {len(pages)} paths are covered."
        )
    return base + (
        "Explore the site systematically. Write a feature file for each distinct page "
        "or section, plus config.yaml. Call finish_analysis() when done."
    )


# ---------------------------------------------------------------------------
# Main analyst loop
# ---------------------------------------------------------------------------

async def run_analysis(
    url: str,
    description: str,
    output_dir: Path,
    spec_prefix: str = "SC",
    config: LLMConfig | None = None,
    pages: list[str] | None = None,
    product_id: str | None = None,
    max_scenarios_per_file: int | None = None,
    sink: LogSink | None = None,
    issues_sink: IssueSink | None = None,
) -> dict:
    """
    Crawl a product site and generate Gherkin feature files.

    Args:
        url:         Root URL of the product to analyze.
        description: One-line product description to guide scenario generation.
        output_dir:  Directory where feature files and config.yaml will be written.
        spec_prefix: Prefix for scenario IDs (e.g. "AC" → AC-001, AC-002, …).
        config:      LLMConfig for the analyst role (defaults to QA_ANALYST_* env vars).

    Returns:
        Summary dict with files_written, file_count, duration_s, summary.
    """
    if config is None:
        config = LLMConfig.from_env(role="analyst")

    ensure_provider_running(config)
    output_dir.mkdir(parents=True, exist_ok=True)

    console = Console()
    console.rule(
        f"[bold]Analyst[/bold] — {url}  "
        f"[dim]({config.provider}/{config.resolved_model()})[/dim]"
    )
    scope_note = f"  │  Pages: {len(pages)} scoped" if pages else ""
    console.print(f"[dim]Prefix: {spec_prefix}  │  Output: {output_dir}{scope_note}[/dim]\n")

    bb_session_id: str | None = None
    cdp_endpoint: str | None = None
    if browserbase.is_configured():
        console.print("[dim]Browserbase: creating analyst session...[/dim]")
        bb_session_id, cdp_endpoint = browserbase.create_session()
        console.print(f"[green]✓[/green] Browserbase session {bb_session_id}")

    server_params = _make_server_params(cdp_endpoint)

    written_files: dict[str, str] = {}
    finished: dict | None = None
    usage: dict = {}

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            mcp_tools = await session.list_tools()
            available_tool_names = {t.name for t in mcp_tools.tools}
            browser_tools = [
                {
                    "type": "function",
                    "function": {
                        "name": t.name,
                        "description": t.description or "",
                        "parameters": t.inputSchema,
                    },
                }
                for t in mcp_tools.tools
                # Keep diagnostic tools for LLM visibility but exclude from standard flow
                if t.name not in ("browser_console_messages", "browser_network_requests")
            ]
            # Analyst always uses full tool set — local models not recommended for this role
            all_tools = browser_tools + [_WRITE_TOOL, _FINISH_TOOL, _REPORT_ISSUE_TOOL]
            console.print(f"[dim]Browser tools: {len(browser_tools)} + 3 analyst tools[/dim]\n")

            scanner = DeterministicScanner()
            # Track whether diagnostic MCP tools are available (graceful degradation)
            _has_console_tool = "browser_console_messages" in available_tool_names
            _has_network_tool = "browser_network_requests" in available_tool_names
            _current_url = url
            _scanner_msg = f"[scanner-init] has_console={_has_console_tool} has_network={_has_network_tool} tools={sorted(available_tool_names)}"
            console.print(f"[cyan]{_scanner_msg}[/cyan]")
            if sink:
                sink.emit(_scanner_msg)

            messages: list[dict] = [
                {"role": "system", "content": _system_prompt()},
                {"role": "user", "content": _user_message(url, description, spec_prefix, str(output_dir), pages, max_scenarios_per_file)},
            ]

            start = time.monotonic()

            for turn in range(MAX_TURNS):
                try:
                    response = complete(config, messages, tools=all_tools, max_tokens=4096, _usage=usage)
                except Exception as e:
                    console.print(f"[red]LLM error on turn {turn}: {e}[/red]")
                    if sink:
                        sink.emit(f"LLM error on turn {turn}: {e}")
                    break

                choice = response.choices[0]
                msg = choice.message

                assistant_entry: dict = {"role": "assistant"}
                if msg.content:
                    assistant_entry["content"] = msg.content
                if msg.tool_calls:
                    assistant_entry["tool_calls"] = [tc.model_dump() for tc in msg.tool_calls]
                messages.append(assistant_entry)

                if not msg.tool_calls:
                    # Model stopped without finish_analysis — treat as done if we have files
                    console.print("[yellow]Warning: model stopped without calling finish_analysis[/yellow]")
                    break

                tool_results: list[dict] = []

                for tc in msg.tool_calls:
                    name = tc.function.name
                    try:
                        args = json.loads(tc.function.arguments)
                    except json.JSONDecodeError:
                        args = {}

                    if name == "write_feature_file":
                        filename = Path(args.get("filename", f"file_{turn}.feature")).name
                        content = args.get("content", "")
                        if max_scenarios_per_file and filename.endswith(".feature"):
                            content = _truncate_gherkin(content, max_scenarios_per_file)
                        written_files[filename] = content
                        path = output_dir / filename
                        path.write_text(content, encoding="utf-8")
                        console.print(
                            f"  [dim green]→ write_feature_file({filename!r}, "
                            f"{len(content)} chars)[/dim green]"
                        )
                        if sink:
                            n_sc = len(re.findall(r'^\s*Scenario(?:\s+Outline)?:', content, re.MULTILINE))
                            sink.emit(f"Writing {filename} ({n_sc} scenario{'s' if n_sc != 1 else ''})")
                        tool_results.append({
                            "role": "tool",
                            "tool_call_id": tc.id,
                            "content": f"OK: {filename} written to {path}.",
                        })

                    elif name == "finish_analysis":
                        finished = args
                        console.print(
                            f"  [dim green]→ finish_analysis: "
                            f"{args.get('summary', '')[:120]}[/dim green]"
                        )
                        if sink:
                            sink.emit(f"Analysis complete: {args.get('summary', '')[:120]}")
                        tool_results.append({
                            "role": "tool",
                            "tool_call_id": tc.id,
                            "content": "Analysis complete. Files will now be written to disk.",
                        })

                    elif name == "report_issue":
                        issue = DeterministicScanner.from_report_issue_args(_current_url, args)
                        if issues_sink:
                            issues_sink.add(issue)
                        msg_preview = args.get("message", "")[:60]
                        console.print(
                            f"  [dim yellow]→ report_issue({issue.severity}: {msg_preview})[/dim yellow]"
                        )
                        if sink:
                            sink.emit(f"Issue found: {msg_preview} [{issue.severity}]")
                        tool_results.append({
                            "role": "tool",
                            "tool_call_id": tc.id,
                            "content": "Issue recorded.",
                        })

                    else:
                        # MCP browser tool
                        args_preview = json.dumps(args, ensure_ascii=False)[:120]
                        console.print(f"  [dim cyan]→ {name}({args_preview})[/dim cyan]")
                        if sink:
                            human = _humanize_tool_call(name, args)
                            if human:
                                sink.emit(human)
                        try:
                            mcp_result = await session.call_tool(name, args)
                            result_text = "\n".join(
                                c.text for c in mcp_result.content if hasattr(c, "text")
                            )
                        except Exception as e:
                            result_text = f"Tool error: {e}"

                        # After navigation: run deterministic issue scanner
                        if sink:
                            sink.emit(f"SCAN_CHECK: name={name!r} issues_sink={issues_sink is not None} has_console={_has_console_tool} has_network={_has_network_tool}")
                        if name == "browser_navigate" and issues_sink:
                            nav_url = args.get("url", _current_url)
                            _current_url = nav_url
                            if sink:
                                sink.emit(f"SCAN_START: nav_url={nav_url}")
                            if _has_console_tool:
                                if sink:
                                    sink.emit("SCAN_CONSOLE: calling browser_console_messages")
                                try:
                                    cr = await session.call_tool("browser_console_messages", {})
                                    ct = "\n".join(c.text for c in cr.content if hasattr(c, "text"))
                                    if sink:
                                        sink.emit(f"SCAN_CONSOLE: got {len(ct)} chars / {len(ct.splitlines())} lines")
                                        if ct.strip():
                                            sink.emit(f"SCAN_CONSOLE: preview={ct[:400]!r}")
                                    issues_before = len(issues_sink._by_fp) if hasattr(issues_sink, '_by_fp') else -1
                                    scanner.ingest_console(nav_url, ct, issues_sink)
                                    issues_after = len(issues_sink._by_fp) if hasattr(issues_sink, '_by_fp') else -1
                                    if sink:
                                        sink.emit(f"SCAN_CONSOLE: ingested, issues {issues_before} -> {issues_after}")
                                except Exception as e:
                                    msg = f"SCAN_CONSOLE_ERROR: {type(e).__name__}: {e}"
                                    if sink:
                                        sink.emit(msg)
                            if _has_network_tool:
                                if sink:
                                    sink.emit("SCAN_NETWORK: calling browser_network_requests")
                                try:
                                    nr = await session.call_tool("browser_network_requests", {})
                                    nt = "\n".join(c.text for c in nr.content if hasattr(c, "text"))
                                    if sink:
                                        sink.emit(f"SCAN_NETWORK: got {len(nt)} chars / {len(nt.splitlines())} lines")
                                        if nt.strip():
                                            sink.emit(f"SCAN_NETWORK: preview={nt[:400]!r}")
                                    issues_before = len(issues_sink._by_fp) if hasattr(issues_sink, '_by_fp') else -1
                                    scanner.ingest_network(nav_url, nt, issues_sink)
                                    issues_after = len(issues_sink._by_fp) if hasattr(issues_sink, '_by_fp') else -1
                                    if sink:
                                        sink.emit(f"SCAN_NETWORK: ingested, issues {issues_before} -> {issues_after}")
                                except Exception as e:
                                    msg = f"SCAN_NETWORK_ERROR: {type(e).__name__}: {e}"
                                    if sink:
                                        sink.emit(msg)

                        tool_results.append({
                            "role": "tool",
                            "tool_call_id": tc.id,
                            "content": result_text,
                        })

                messages.extend(tool_results)

                if finished:
                    break

    if bb_session_id:
        browserbase.delete_session(bb_session_id)

    issues_list: list[Issue] = []
    if issues_sink and isinstance(issues_sink, BufferingIssueSink):
        issues_list = issues_sink.finalize()
        if sink:
            sink.emit(f"SCAN_FINAL: {len(issues_list)} unique issues collected by scanner")
            for issue in issues_list[:5]:
                sink.emit(f"  → [{issue.severity}] {issue.type}: {issue.message[:120]}")

    if product_id:
        from qa_agent.db import is_configured
        from qa_agent.db import specs as db_specs
        from qa_agent.db import issues as db_issues
        if is_configured():
            if written_files:
                for filename, content in written_files.items():
                    await db_specs.upsert(product_id, filename, content)
                console.print(f"[dim]DB: {len(written_files)} spec(s) saved for product {product_id}[/dim]")
            if issues_list:
                await db_issues.bulk_upsert(product_id, issues_to_dicts(issues_list))
                console.print(f"[dim]DB: {len(issues_list)} issue(s) saved for product {product_id}[/dim]")

    console.print()
    for filename in written_files:
        console.print(f"[green]✓[/green] {output_dir / filename}")

    duration = round(time.monotonic() - start, 1)
    summary = finished.get("summary", "incomplete") if finished else "incomplete — finish_analysis not called"

    cost = estimate_cost(config.resolved_model(), usage)
    if cost is not None:
        usage["cost_usd"] = round(cost, 6)

    telemetry = {
        "role": "analyst",
        "url": url,
        "provider": config.provider,
        "model": config.resolved_model(),
        "duration_s": duration,
        "files_written": len(written_files),
        "tokens": usage,
    }
    (output_dir / "analyst_telemetry.json").write_text(
        json.dumps(telemetry, indent=2), encoding="utf-8"
    )

    console.print()
    console.print(Panel(
        f"[bold]Files written:[/bold] {len(written_files)}\n"
        f"[bold]Duration:[/bold]     {duration}s\n"
        + (f"[bold]Cost:[/bold]         ${cost:.4f}\n" if cost is not None else "")
        + f"[bold]Summary:[/bold]      {summary}",
        title=(
            "[green]Analysis complete[/green]"
            if finished else
            "[yellow]Analysis incomplete[/yellow]"
        ),
        border_style="green" if finished else "yellow",
    ))

    return {
        "url": url,
        "output_dir": str(output_dir),
        "files_written": list(written_files.keys()),
        "file_count": len(written_files),
        "duration_s": duration,
        "summary": summary,
        "complete": finished is not None,
        "provider": config.provider,
        "model": config.resolved_model(),
        "scoped_pages": pages,
        "tokens": usage,
        "cost_usd": cost,
        "issues_count": len(issues_list),
    }


async def main() -> None:
    import sys
    url = sys.argv[1] if len(sys.argv) > 1 else "https://german-brawl.vercel.app"
    description = sys.argv[2] if len(sys.argv) > 2 else "PWA vocabulary learning game"
    prefix = sys.argv[3] if len(sys.argv) > 3 else "SC"
    output = Path(sys.argv[4]) if len(sys.argv) > 4 else Path("specs/generated")

    config = LLMConfig.from_env(role="analyst")
    result = await run_analysis(url, description, output, prefix, config)
    print("\n" + json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
