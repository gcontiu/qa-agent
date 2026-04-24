"""
Executor — runs a single requirement via tool-use loop.
Uses LiteLLM (OpenAI-compatible format) so any provider works:
  Anthropic API (default) or Ollama local (--executor-provider ollama).
Usage: uv run python -m qa_agent.agent
"""
import asyncio
import json
import os
import time
from pathlib import Path

import anthropic  # still used for APIError type
from dotenv import load_dotenv
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from qa_agent.llm import LLMConfig, complete

load_dotenv(Path(__file__).parent.parent.parent / ".env")

PROMPTS_DIR = Path(__file__).parent / "prompts"
MAX_TURNS = 25

# Hardcoded fallback for direct `python -m qa_agent.agent` invocation
_HARDCODED_REQ = {
    "id": "GB-002",
    "title": "Lobby displays all required navigation buttons",
    "priority": "high",
    "given": "The app is loaded at the target URL",
    "when": "The player views the lobby",
    "then": (
        "The Shop button is visible, "
        "the Brawlers button is visible, "
        "the GAMEMODES button is visible, "
        "the PLAY button is visible, "
        "the Quest button is visible, "
        "and the Brawl Pass progress bar is visible"
    ),
}
_TARGET_URL = "https://german-brawl.vercel.app/"

# ---------------------------------------------------------------------------
# Tool definitions (OpenAI format)
# ---------------------------------------------------------------------------

_REPORT_TOOL: dict = {
    "type": "function",
    "function": {
        "name": "report_result",
        "description": (
            "Call this when you have determined the test outcome. "
            "Required to finalize the test — do not stop without calling this."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "status": {
                    "type": "string",
                    "enum": ["pass", "fail"],
                    "description": "'pass' if the Then condition was satisfied, 'fail' otherwise",
                },
                "actual": {
                    "type": "string",
                    "description": "What you actually observed in the browser",
                },
                "reasoning": {
                    "type": "string",
                    "description": "Concise explanation of why you gave this verdict",
                },
            },
            "required": ["status", "actual", "reasoning"],
        },
    },
}


# Reduced set for smaller models that struggle with 20+ tools.
_ESSENTIAL_TOOLS = {
    "browser_navigate", "browser_snapshot", "browser_click",
    "browser_type", "browser_fill_form", "browser_press_key",
    "browser_wait_for", "browser_select_option",
}


def _mcp_to_openai_tools(tools_result, slim: bool = False) -> list[dict]:
    return [
        {
            "type": "function",
            "function": {
                "name": t.name,
                "description": t.description or "",
                "parameters": t.inputSchema,
            },
        }
        for t in tools_result.tools
        if not slim or t.name in _ESSENTIAL_TOOLS
    ]


# ---------------------------------------------------------------------------
# Prompt helpers
# ---------------------------------------------------------------------------

def _system_prompt() -> str:
    return (PROMPTS_DIR / "executor_system.md").read_text()


def _user_message(req: dict, url: str) -> str:
    return (
        f"Test Requirement:\n"
        f"ID: {req['id']}\n"
        f"Title: {req['title']}\n"
        f"Priority: {req['priority']}\n\n"
        f"Given: {req['given']}\n"
        f"When:  {req['when']}\n"
        f"Then:  {req['then']}\n\n"
        f"Target URL: {url}\n\n"
        f"Navigate to the target URL and execute the requirement. "
        f"Call report_result when you have a verdict."
    )


# ---------------------------------------------------------------------------
# Main executor
# ---------------------------------------------------------------------------

_TEST_TIMEOUT_DEFAULTS = {"ollama": 360, "anthropic": None}


async def run_requirement(
    req: dict,
    url: str,
    config: LLMConfig | None = None,
    test_timeout: int | None = ...,  # type: ignore[assignment]
) -> dict:
    if config is None:
        config = LLMConfig.from_env(role="executor")

    # Sentinel ... means "use provider default"; None means "no cap"
    if test_timeout is ...:  # type: ignore[comparison-overlap]
        env_val = os.getenv("QA_TEST_TIMEOUT")
        if env_val is not None:
            test_timeout = int(env_val)
        else:
            test_timeout = _TEST_TIMEOUT_DEFAULTS.get(config.provider)

    console = Console()
    console.rule(
        f"[bold]{req['id']}[/bold] — {req['title']} "
        f"[dim]({config.provider}/{config.resolved_model()})[/dim]"
    )
    console.print(f"[dim]Given:[/dim] {req['given']}")
    console.print(f"[dim]When: [/dim] {req['when']}")
    console.print(f"[dim]Then: [/dim] {req['then']}")
    console.print()

    server_params = StdioServerParameters(
        command="npx",
        args=["@playwright/mcp@latest", "--headless", "--isolated"],
    )

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            mcp_tools = await session.list_tools()
            slim = config.provider == "ollama"
            all_tools = _mcp_to_openai_tools(mcp_tools, slim=slim) + [_REPORT_TOOL]

            messages: list[dict] = [
                {"role": "system", "content": _system_prompt()},
                {"role": "user", "content": _user_message(req, url)},
            ]

            actions_log: list[dict] = []
            verdict: dict | None = None
            start = time.monotonic()

            for turn in range(MAX_TURNS):
                if test_timeout and (time.monotonic() - start) >= test_timeout:
                    console.print(f"[red]Test timeout ({test_timeout}s) exceeded[/red]")
                    verdict = {
                        "status": "fail",
                        "actual": "Test did not complete within the time limit",
                        "reasoning": f"test_timeout={test_timeout}s exceeded after {turn} turns",
                    }
                    break

                try:
                    response = complete(config, messages, tools=all_tools)
                except Exception as e:
                    verdict = {
                        "status": "error",
                        "actual": f"LLM error: {e}",
                        "reasoning": str(e),
                    }
                    break

                choice = response.choices[0]
                msg = choice.message

                # Append assistant turn (strip None fields for cleanliness)
                assistant_entry: dict = {"role": "assistant"}
                if msg.content:
                    assistant_entry["content"] = msg.content
                if msg.tool_calls:
                    assistant_entry["tool_calls"] = [
                        tc.model_dump() for tc in msg.tool_calls
                    ]
                messages.append(assistant_entry)

                finish = choice.finish_reason  # "stop" | "tool_calls" | "end_turn"

                if finish in ("stop", "end_turn") or not msg.tool_calls:
                    content_str = msg.content or ""
                    try:
                        parsed = json.loads(content_str)
                        # Fallback A: model emitted report_result payload as text JSON
                        if isinstance(parsed, dict) and "status" in parsed and "actual" in parsed:
                            console.print("[dim yellow]Fallback-A: report_result from content text[/dim yellow]")
                            verdict = parsed
                            break
                        # Fallback B: model emitted a ghost tool call as text JSON
                        # e.g. {"id": "...", "type": "function", "function": {"name": "...", "arguments": {...}}}
                        if (
                            isinstance(parsed, dict)
                            and parsed.get("type") == "function"
                            and isinstance(parsed.get("function"), dict)
                            and "name" in parsed["function"]
                        ):
                            fn = parsed["function"]
                            ghost_name = fn["name"]
                            ghost_args = fn.get("arguments") or {}
                            if isinstance(ghost_args, str):
                                ghost_args = json.loads(ghost_args) if ghost_args else {}
                            if ghost_name == "report_result":
                                console.print("[dim yellow]Fallback-B: report_result ghost call[/dim yellow]")
                                verdict = ghost_args
                                break
                            ghost_id = parsed.get("id", f"ghost_{turn}")
                            args_preview = json.dumps(ghost_args, ensure_ascii=False)[:100]
                            console.print(f"  [dim yellow]Ghost → {ghost_name}({args_preview})[/dim yellow]")
                            actions_log.append({"tool": ghost_name, "input": ghost_args})
                            mcp_result = await session.call_tool(ghost_name, ghost_args)
                            ghost_result_text = "\n".join(
                                c.text for c in mcp_result.content if hasattr(c, "text")
                            )
                            # Inject as a proper assistant tool_call + tool result pair
                            messages[-1] = {
                                "role": "assistant",
                                "tool_calls": [{
                                    "id": ghost_id,
                                    "type": "function",
                                    "function": {"name": ghost_name, "arguments": json.dumps(ghost_args)},
                                }],
                            }
                            messages.append({
                                "role": "tool",
                                "tool_call_id": ghost_id,
                                "content": ghost_result_text,
                            })
                            continue  # retry this turn with proper tool result
                    except (json.JSONDecodeError, TypeError):
                        pass
                    console.print(
                        "[yellow]Warning: agent stopped without calling report_result[/yellow]"
                    )
                    verdict = {
                        "status": "fail",
                        "actual": content_str or "No output",
                        "reasoning": "report_result was never called",
                    }
                    break

                tool_results: list[dict] = []
                for tc in msg.tool_calls:
                    name = tc.function.name
                    try:
                        args = json.loads(tc.function.arguments)
                    except json.JSONDecodeError:
                        args = {}

                    if name == "report_result":
                        verdict = args
                        break

                    args_preview = json.dumps(args, ensure_ascii=False)[:100]
                    console.print(f"  [dim cyan]→ {name}({args_preview})[/dim cyan]")
                    actions_log.append({"tool": name, "input": args})

                    mcp_result = await session.call_tool(name, args)
                    content_text = "\n".join(
                        c.text for c in mcp_result.content if hasattr(c, "text")
                    )
                    tool_results.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": content_text,
                    })

                if verdict:
                    break

                if tool_results:
                    messages.extend(tool_results)

            if not verdict:
                verdict = {
                    "status": "fail",
                    "actual": f"No verdict after {MAX_TURNS} turns",
                    "reasoning": "Turn budget exhausted",
                }

            duration = round(time.monotonic() - start, 1)

            # Display result
            console.print()
            status = verdict.get("status", "fail").upper()
            is_pass = status == "PASS"
            color = "green" if is_pass else "red"
            icon = "✓" if is_pass else "✗"

            label = Text()
            label.append(f" {icon} {status} ", style=f"bold {color}")
            label.append(f" │  {len(actions_log)} actions  │  {duration}s ")

            console.print(Panel(
                f"[bold]Actual:[/bold]    {verdict.get('actual', '')}\n"
                f"[bold]Reasoning:[/bold] {verdict.get('reasoning', '')}",
                title=label,
                border_style=color,
            ))

            return {
                **verdict,
                "id": req["id"],
                "title": req.get("title", ""),
                "then": req.get("then", ""),
                "priority": req.get("priority", "medium"),
                "actions_log": actions_log,
                "duration_s": duration,
                "turns": turn + 1,
                "provider": config.provider,
                "model": config.resolved_model(),
            }


async def main() -> None:
    config = LLMConfig.from_env(role="executor")
    result = await run_requirement(_HARDCODED_REQ, _TARGET_URL, config)
    import json as _json
    print("\n" + _json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
