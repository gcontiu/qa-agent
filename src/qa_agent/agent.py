"""
Iteration 1 — single hardcoded requirement executed end-to-end.
Usage: uv run python -m qa_agent.agent
"""
import asyncio
import json
import time
from pathlib import Path

import anthropic
from dotenv import load_dotenv
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from rich.console import Console
from rich.panel import Panel
from rich.rule import Rule
from rich.text import Text

load_dotenv(Path(__file__).parent.parent.parent / ".env")

PROMPTS_DIR = Path(__file__).parent / "prompts"
MODEL = "claude-sonnet-4-6"
MAX_TURNS = 25

# --- Hardcoded for iteration 1 ---
REQUIREMENT = {
    "id": "GB-001",
    "title": "PLAY button starts a battle",
    "priority": "high",
    "given": "The lobby is loaded with Shelly visible and the PLAY button present",
    "when": "The player clicks the PLAY button",
    "then": "The battle screen appears with a countdown timer visible",
}
TARGET_URL = "https://german-brawl.vercel.app/"
# ----------------------------------

REPORT_TOOL = {
    "name": "report_result",
    "description": (
        "Call this when you have determined the test outcome. "
        "Required to finalize the test — do not stop without calling this."
    ),
    "input_schema": {
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
}


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


async def run_requirement(req: dict, url: str) -> dict:
    console = Console()

    console.rule(f"[bold]{req['id']}[/bold] — {req['title']}")
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

            tools_result = await session.list_tools()
            playwright_tools = [
                {
                    "name": t.name,
                    "description": t.description or "",
                    "input_schema": t.inputSchema,
                }
                for t in tools_result.tools
            ]
            all_tools = playwright_tools + [REPORT_TOOL]

            client = anthropic.Anthropic()
            messages = [{"role": "user", "content": _user_message(req, url)}]
            actions_log: list[dict] = []
            verdict: dict | None = None
            start = time.monotonic()

            for turn in range(MAX_TURNS):
                response = client.messages.create(
                    model=MODEL,
                    max_tokens=2048,
                    system=_system_prompt(),
                    tools=all_tools,
                    messages=messages,
                )
                messages.append({"role": "assistant", "content": response.content})

                if response.stop_reason == "end_turn":
                    console.print("[yellow]Warning: agent stopped without calling report_result[/yellow]")
                    verdict = {
                        "status": "fail",
                        "actual": "Agent stopped without a verdict",
                        "reasoning": "report_result was never called",
                    }
                    break

                if response.stop_reason == "tool_use":
                    tool_results = []

                    for block in response.content:
                        if block.type != "tool_use":
                            continue

                        if block.name == "report_result":
                            verdict = block.input
                            break

                        args_preview = json.dumps(block.input, ensure_ascii=False)[:100]
                        console.print(f"  [dim cyan]→ {block.name}({args_preview})[/dim cyan]")
                        actions_log.append({"tool": block.name, "input": block.input})

                        mcp_result = await session.call_tool(block.name, block.input)
                        content_text = "\n".join(
                            c.text for c in mcp_result.content if hasattr(c, "text")
                        )
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": content_text,
                        })

                    if verdict:
                        break

                    if tool_results:
                        messages.append({"role": "user", "content": tool_results})

            if not verdict:
                verdict = {
                    "status": "fail",
                    "actual": f"No verdict after {MAX_TURNS} turns",
                    "reasoning": "Turn budget exhausted",
                }

            duration = round(time.monotonic() - start, 1)

            # --- Display result ---
            console.print()
            status = verdict["status"].upper()
            is_pass = status == "PASS"
            color = "green" if is_pass else "red"
            icon = "✓" if is_pass else "✗"

            summary = Text()
            summary.append(f" {icon} {status} ", style=f"bold {color}")
            summary.append(f" │  {len(actions_log)} actions  │  {duration}s ")

            console.print(Panel(
                f"[bold]Actual:[/bold]    {verdict['actual']}\n"
                f"[bold]Reasoning:[/bold] {verdict['reasoning']}",
                title=summary,
                border_style=color,
            ))

            return {
                **verdict,
                "id": req["id"],
                "actions_log": actions_log,
                "duration_s": duration,
                "turns": turn + 1,
            }


async def main() -> None:
    result = await run_requirement(REQUIREMENT, TARGET_URL)
    # Raw JSON for downstream consumers
    print("\n" + json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
