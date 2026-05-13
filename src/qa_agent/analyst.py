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
import time
from pathlib import Path

from mcp import ClientSession
from mcp.client.stdio import stdio_client
from rich.console import Console
from rich.panel import Panel

from qa_agent.agent import _make_server_params
from qa_agent import browserbase
from qa_agent.llm import LLMConfig, complete, ensure_provider_running, estimate_cost

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


# ---------------------------------------------------------------------------
# Prompt helpers
# ---------------------------------------------------------------------------

def _system_prompt() -> str:
    return (PROMPTS_DIR / "analyst_system.md").read_text()


def _user_message(url: str, description: str, spec_prefix: str, output_dir: str, pages: list[str] | None = None) -> str:
    base = (
        f"Product URL: {url}\n"
        f"Product description: {description}\n"
        f"Scenario ID prefix: {spec_prefix}\n"
        f"Output directory: {output_dir}\n\n"
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
            ]
            # Analyst always uses full tool set — local models not recommended for this role
            all_tools = browser_tools + [_WRITE_TOOL, _FINISH_TOOL]
            console.print(f"[dim]Browser tools: {len(browser_tools)} + 2 analyst tools[/dim]\n")

            messages: list[dict] = [
                {"role": "system", "content": _system_prompt()},
                {"role": "user", "content": _user_message(url, description, spec_prefix, str(output_dir), pages)},
            ]

            start = time.monotonic()

            for turn in range(MAX_TURNS):
                try:
                    response = complete(config, messages, tools=all_tools, max_tokens=4096, _usage=usage)
                except Exception as e:
                    console.print(f"[red]LLM error on turn {turn}: {e}[/red]")
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
                        written_files[filename] = content
                        path = output_dir / filename
                        path.write_text(content, encoding="utf-8")
                        console.print(
                            f"  [dim green]→ write_feature_file({filename!r}, "
                            f"{len(content)} chars)[/dim green]"
                        )
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
                        tool_results.append({
                            "role": "tool",
                            "tool_call_id": tc.id,
                            "content": "Analysis complete. Files will now be written to disk.",
                        })

                    else:
                        # MCP browser tool
                        args_preview = json.dumps(args, ensure_ascii=False)[:120]
                        console.print(f"  [dim cyan]→ {name}({args_preview})[/dim cyan]")
                        try:
                            mcp_result = await session.call_tool(name, args)
                            result_text = "\n".join(
                                c.text for c in mcp_result.content if hasattr(c, "text")
                            )
                        except Exception as e:
                            result_text = f"Tool error: {e}"
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
