"""
Smoke test: verify that Agent SDK + Playwright MCP can navigate a URL.
Usage: uv run python -m qa_agent.smoke [url]
"""
import asyncio
import json
import sys
from pathlib import Path

import anthropic
from dotenv import load_dotenv
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

load_dotenv(Path(__file__).parent.parent.parent / ".env")

MODEL = "claude-sonnet-4-6"
SYSTEM = (
    "You are a browser automation agent. Navigate to the URL given by the user, "
    "take a snapshot of the page, and report: the page title and one sentence "
    "describing what you see. Be concise. Stop after reporting."
)


async def run(url: str) -> None:
    server_params = StdioServerParameters(
        command="npx",
        args=["@playwright/mcp@latest", "--headless", "--isolated"],
    )

    print(f"[smoke] Starting Playwright MCP...")
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            tools_result = await session.list_tools()
            tools = [
                {
                    "name": t.name,
                    "description": t.description or "",
                    "input_schema": t.inputSchema,
                }
                for t in tools_result.tools
            ]
            print(f"[smoke] Connected — {len(tools)} tools available")
            print(f"[smoke] Navigating to {url} ...\n")

            client = anthropic.Anthropic()
            messages = [
                {"role": "user", "content": f"Navigate to {url} and report the page title and what you see."}
            ]

            turn = 0
            while turn < 20:
                turn += 1
                response = client.messages.create(
                    model=MODEL,
                    max_tokens=1024,
                    system=SYSTEM,
                    tools=tools,
                    messages=messages,
                )

                messages.append({"role": "assistant", "content": response.content})

                if response.stop_reason == "end_turn":
                    for block in response.content:
                        if hasattr(block, "text"):
                            print(f"[result] {block.text}")
                    break

                if response.stop_reason == "tool_use":
                    tool_results = []
                    for block in response.content:
                        if block.type == "tool_use":
                            args_preview = json.dumps(block.input, ensure_ascii=False)[:80]
                            print(f"[tool]   {block.name}({args_preview})")
                            result = await session.call_tool(block.name, block.input)
                            content_text = "\n".join(
                                c.text for c in result.content if hasattr(c, "text")
                            )
                            tool_results.append({
                                "type": "tool_result",
                                "tool_use_id": block.id,
                                "content": content_text,
                            })
                    messages.append({"role": "user", "content": tool_results})
                else:
                    print(f"[smoke] Unexpected stop_reason: {response.stop_reason}")
                    break
            else:
                print("[smoke] Hit turn limit without completion.")


def main() -> None:
    url = sys.argv[1] if len(sys.argv) > 1 else "https://german-brawl.vercel.app/"
    asyncio.run(run(url))


if __name__ == "__main__":
    main()
