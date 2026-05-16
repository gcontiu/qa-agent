"""
Executor — runs a single requirement via tool-use loop.
Uses LiteLLM (OpenAI-compatible format) so any provider works:
  Anthropic API (default) or Ollama local (--executor-provider ollama).
Usage: uv run python -m qa_agent.agent
"""
import asyncio
import json
import os
import re
import shutil
import time
from pathlib import Path

import anthropic  # still used for APIError type
from dotenv import load_dotenv
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from rich.console import Console
from rich.markup import escape as _esc_markup
from rich.panel import Panel
from rich.text import Text

from qa_agent.llm import LLMConfig, complete, ensure_provider_running, _resolve_timeout, _TEST_TIMEOUT_DEFAULTS
from qa_agent.llm.router import estimate_cost
from qa_agent import browserbase
from qa_agent.log_sink import LogSink, _humanize_tool_call

load_dotenv(Path(__file__).parent.parent.parent / ".env")

PROMPTS_DIR = Path(__file__).parent / "prompts"
MAX_TURNS = 25

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

# Tools that must NOT be subject to the loop guard.
# browser_evaluate: JS expressions are side-effect-free or intentional (e.g. repeated scrolls).
# browser_press_key / browser_wait_for: idempotent or intentionally repeatable.
_LOOP_GUARD_SKIP = frozenset({
    "browser_snapshot", "browser_evaluate", "browser_press_key", "browser_wait_for",
})


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

def _extract_given_url(given: str, base_url: str) -> str:
    """Return base_url+path if the Given clause names a specific URL path, else base_url.

    Matches Romanian/English patterns: 'la URL-ul /path', 'at URL /path', 'URL /path'.
    """
    match = re.search(r'(?:url[- ]ul\s+|url\s+)(/[^\s,\.]+)', given, re.IGNORECASE)
    if match:
        return base_url.rstrip('/') + match.group(1)
    return base_url


# ---------------------------------------------------------------------------
# When-action guardrail
# ---------------------------------------------------------------------------

_WHEN_ACTION_PATTERNS: list[tuple[str, list[str]]] = [
    (r'\bapas[aă]\b',          ["browser_click"]),
    (r'\bclick\b',             ["browser_click"]),
    (r'\bda\s+click\b',        ["browser_click"]),
    (r'\bcomplet[eă]az[aă]\b', ["browser_type", "browser_fill_form"]),
    (r'\bintroduce\b',         ["browser_type", "browser_fill_form"]),
    (r'\btasteaz[aă]\b',       ["browser_type"]),
    (r'\bselecte[ae]z[aă]\b',  ["browser_select_option"]),
    (r'\btrimite\b',           ["browser_click"]),
    (r'\bsubmit\b',            ["browser_click"]),
    (r'\bapas[aă]\s+tasta\b',  ["browser_press_key"]),
    (r'\bclicks?\b',           ["browser_click"]),
    (r'\bfills?\b',            ["browser_type", "browser_fill_form"]),
    (r'\btypes?\b',            ["browser_type"]),
    (r'\bselects?\b',          ["browser_select_option"]),
    (r'\bsubmits?\b',          ["browser_click"]),
    (r'\bpresses?\b',          ["browser_press_key"]),
]

_MAX_WHEN_RETRIES = 2


def _required_tools_for_when(when: str) -> list[str]:
    """Return tool names that must appear in actions before a PASS verdict."""
    lower = when.lower()
    required: set[str] = set()
    for pattern, tools in _WHEN_ACTION_PATTERNS:
        if re.search(pattern, lower):
            required.update(tools)
    return list(required)


def _when_guardrail(
    verdict_candidate: dict,
    req: dict,
    model_tool_names: list[str],
    guard_count: int,
) -> tuple[dict | None, int, str | None]:
    """Validate that required When actions were performed before accepting a PASS verdict.

    Returns:
      (verdict, count, None)       — accepted
      (None, count+1, message)     — blocked; caller injects message and continues
      (error_dict, count, None)    — retry budget exhausted; treated as FAIL
    """
    if verdict_candidate.get("status") != "pass":
        return verdict_candidate, guard_count, None

    when = req.get("when", "").strip()
    if not when:
        return verdict_candidate, guard_count, None

    required = _required_tools_for_when(when)
    if not required:
        return verdict_candidate, guard_count, None

    if set(model_tool_names) & set(required):
        return verdict_candidate, guard_count, None

    if guard_count >= _MAX_WHEN_RETRIES:
        return {
            "status": "fail",
            "actual": f"When action was never performed ('{when}').",
            "reasoning": (
                f"Guardrail: When clause requires {required} but model reported PASS "
                "without performing it — retry budget exhausted."
            ),
        }, guard_count, None

    correction = (
        f"report_result was blocked by the When-action guardrail.\n"
        f"The When clause requires you to perform: '{when}'\n\n"
        f"You must call {' or '.join(required)} before reporting a verdict. "
        "The page is already loaded — find the element ref in the snapshot above "
        "and perform the action. Then call report_result with your final verdict."
    )
    return None, guard_count + 1, correction


def _system_prompt() -> str:
    return (PROMPTS_DIR / "executor_system.md").read_text()


def _user_message(req: dict, url: str, context: str = "") -> str:
    parts = []
    if context:
        parts.append(f"Product context:\n{context.strip()}\n")
    parts.append(
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
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Verdict extraction (last-resort fallback when report_result is never called)
# ---------------------------------------------------------------------------

def _prune_for_verdict(messages: list[dict]) -> list[dict]:
    """Reduce conversation history to the essential context for verdict extraction.

    Keeps the system prompt, the original user requirement, a summary of which
    browser tools were called, and the last meaningful snapshot result.
    Discards intermediate snapshots, ghost retry loops, and error messages so
    the extractor receives a focused, cheap-to-process context.
    """
    system_msgs = [m for m in messages if m.get("role") == "system"]
    user_requirement = next((m for m in messages if m.get("role") == "user"), None)

    # Collect ordered action names from assistant tool_calls
    actions: list[str] = []
    for m in messages:
        if m.get("role") == "assistant":
            for tc in m.get("tool_calls") or []:
                name = (tc.get("function") or {}).get("name", "")
                if name and name not in ("report_result",):
                    try:
                        args = json.loads((tc.get("function") or {}).get("arguments", "{}"))
                    except (json.JSONDecodeError, TypeError):
                        args = {}
                    url = args.get("url", "")
                    actions.append(f"{name}({url})" if url else name)

    # Last non-trivial tool result (the most recent snapshot the model saw)
    last_snapshot_content: str | None = None
    for m in reversed(messages):
        if m.get("role") == "tool":
            content = m.get("content", "")
            if isinstance(content, str) and len(content) > 50:
                last_snapshot_content = content
                break

    pruned: list[dict] = list(system_msgs)
    if user_requirement:
        pruned.append(user_requirement)

    context_parts: list[str] = []
    if actions:
        context_parts.append(f"Actions taken: {' → '.join(actions[:15])}")
    if last_snapshot_content:
        context_parts.append(f"Last page state observed:\n{last_snapshot_content[:4000]}")

    if context_parts:
        pruned.append({"role": "user", "content": "\n\n".join(context_parts)})

    return pruned


async def _bootstrap(
    session: ClientSession,
    req: dict,
    base_url: str,
    snap_depth: int,
    console: Console,
) -> tuple[str, list[dict], list[dict]]:
    """Pre-execute browser_navigate + browser_snapshot before the LLM loop.

    Used by Ollama (where models struggle to initiate tool calls) and Anthropic
    (where it eliminates redundant first-turn navigation). Returns the snapshot
    text, conversation messages to extend, and actions_log entries — caller merges
    them into its state. Centralised to avoid duplication between providers.
    """
    boot_url = _extract_given_url(req.get("given", ""), base_url)

    console.print(f"  [dim cyan]→ browser_navigate({boot_url!r}) [bootstrap][/dim cyan]")
    nav_result = await session.call_tool("browser_navigate", {"url": boot_url})
    nav_text = "\n".join(c.text for c in nav_result.content if hasattr(c, "text"))

    snap_args = {"depth": snap_depth}
    console.print(f"  [dim cyan]→ browser_snapshot(depth={snap_depth}) [bootstrap][/dim cyan]")
    snap_result = await session.call_tool("browser_snapshot", snap_args)
    snap_text = "\n".join(c.text for c in snap_result.content if hasattr(c, "text"))

    nav_id, snap_id = "bootstrap_nav_0", "bootstrap_snap_0"
    boot_messages = [
        {
            "role": "assistant",
            "tool_calls": [{
                "id": nav_id, "type": "function",
                "function": {"name": "browser_navigate", "arguments": json.dumps({"url": boot_url})},
            }],
        },
        {"role": "tool", "tool_call_id": nav_id, "content": nav_text},
        {
            "role": "assistant",
            "tool_calls": [{
                "id": snap_id, "type": "function",
                "function": {"name": "browser_snapshot", "arguments": json.dumps(snap_args)},
            }],
        },
        {"role": "tool", "tool_call_id": snap_id, "content": snap_text},
    ]
    boot_actions = [
        {"tool": "browser_navigate", "input": {"url": boot_url}},
        {"tool": "browser_snapshot", "input": {}},
    ]
    return snap_text, boot_messages, boot_actions


async def _single_shot_verify(
    config: "LLMConfig",
    req: dict,
    context: str,
    snap_text: str,
    console: Console,
    _usage: dict | None = None,
) -> dict | None:
    """Verify Then conditions via a single LLM call with forced report_result.

    Uses tool_choice="required" with only report_result available — Anthropic and
    OpenAI-compatible providers (including Together.ai) all honour this. The tool
    schema's enum ["pass", "fail"] guarantees a structured verdict, more reliable
    than response_format=json_object across providers.

    Returns a verdict dict on success, None on any failure (caller falls through
    to the full tool loop).
    """
    user_msg = (
        (f"Product context:\n{context.strip()}\n\n" if context else "")
        + f"Test Requirement:\n"
          f"ID: {req['id']}\n"
          f"Title: {req['title']}\n"
          f"Given: {req['given']}\n"
          f"Then:  {req['then']}\n\n"
          f"Current page state:\n{snap_text}\n\n"
          "Based ONLY on the page state above, verify whether the Then conditions "
          "are met and call report_result with your verdict."
    )
    messages = [
        {"role": "system", "content": _system_prompt()},
        {"role": "user", "content": user_msg},
    ]
    try:
        response = complete(
            config, messages,
            tools=[_REPORT_TOOL],
            tool_choice="required",
            max_tokens=400,
            _usage=_usage,
        )
        for tc in response.choices[0].message.tool_calls or []:
            if tc.function.name == "report_result":
                args = json.loads(tc.function.arguments)
                if (isinstance(args, dict)
                        and args.get("status") in ("pass", "fail")
                        and "actual" in args):
                    console.print("[dim]Single-shot verification[/dim]")
                    return args
    except Exception as e:
        console.print(f"[dim red]Single-shot failed ({e}) — using tool loop[/dim red]")
    return None


def _prune_stale_snapshots(messages: list[dict]) -> None:
    """Replace all but the most recent browser_snapshot result with a placeholder.

    After each new snapshot the previous ones are stale — their refs no longer
    exist on the current page. Keeping them wastes tokens without helping the model.
    Runs in-place; called after every tool_results extension.
    """
    snapshot_ids: list[str] = []
    for msg in messages:
        if msg.get("role") == "assistant":
            for tc in (msg.get("tool_calls") or []):
                if isinstance(tc, dict) and tc.get("function", {}).get("name") == "browser_snapshot":
                    call_id = tc.get("id", "")
                    if call_id:
                        snapshot_ids.append(call_id)

    if len(snapshot_ids) <= 1:
        return

    stale_ids = set(snapshot_ids[:-1])
    for msg in messages:
        if (
            msg.get("role") == "tool"
            and msg.get("tool_call_id") in stale_ids
            and len(msg.get("content", "")) > 100
        ):
            msg["content"] = "[snapshot superseded — see latest snapshot above]"


async def _extract_verdict(
    executor_config: LLMConfig,
    messages: list[dict],
    then_clause: str,
    console: Console,
    _usage: dict | None = None,
) -> dict | None:
    """Last-resort verdict extraction from the executor's conversation history.

    Called when the executor loop ends without a report_result call.
    Builds a clean 2-message conversation (system + one user turn) to avoid
    the consecutive-user-message rejection that Anthropic enforces. Uses the
    dedicated extractor_system.md prompt and relies on instruction-following
    for JSON output rather than response_format (which LiteLLM translates to
    an internal tool call for Anthropic, leaving message.content empty).
    """
    extractor_config = LLMConfig.from_env(role="extractor")

    # If the user hasn't explicitly configured a separate extractor provider,
    # inherit the executor's provider so a local-only run stays local.
    if not os.getenv("QA_EXTRACTOR_PROVIDER"):
        extractor_config.provider = executor_config.provider
        if not os.getenv("QA_EXTRACTOR_MODEL"):
            extractor_config.model = None  # use extractor role default for this provider

    console.print(
        f"[dim yellow]Verdict extraction fallback "
        f"({extractor_config.provider}/{extractor_config.resolved_model()})[/dim yellow]"
    )

    # Collect action names from the executor conversation
    actions: list[str] = []
    for m in messages:
        if m.get("role") == "assistant":
            for tc in m.get("tool_calls") or []:
                name = (tc.get("function") or {}).get("name", "")
                if name and name != "report_result":
                    try:
                        args = json.loads((tc.get("function") or {}).get("arguments", "{}"))
                    except (json.JSONDecodeError, TypeError):
                        args = {}
                    url = args.get("url", "")
                    actions.append(f"{name}({url})" if url else name)

    # Build tool_call_id → tool_name index so we can filter by tool type below.
    _tool_name_for: dict[str, str] = {}
    for m in messages:
        if m.get("role") == "assistant":
            for tc in m.get("tool_calls") or []:
                tc_id = tc.get("id", "")
                tc_name = (tc.get("function") or {}).get("name", "")
                if tc_id and tc_name:
                    _tool_name_for[tc_id] = tc_name

    def _is_useful_snapshot(msg: dict) -> bool:
        content = msg.get("content", "")
        if not isinstance(content, str) or len(content) < 50:
            return False
        if "[snapshot superseded" in content:
            return False
        return True

    # Prefer the last browser_snapshot result — it is the accessibility tree.
    # browser_evaluate results (e.g. "Result: undefined") are not page state.
    last_snapshot: str = ""
    for m in reversed(messages):
        if m.get("role") == "tool":
            if _tool_name_for.get(m.get("tool_call_id", "")) == "browser_snapshot":
                if _is_useful_snapshot(m):
                    last_snapshot = m["content"][:4000]
                    break
    # Fall back to any large tool result if no snapshot is available.
    if not last_snapshot:
        for m in reversed(messages):
            if m.get("role") == "tool" and _is_useful_snapshot(m):
                last_snapshot = m["content"][:4000]
                break

    # Single user message with all evidence — no consecutive user turns
    evidence = ""
    if actions:
        evidence += f"Actions taken: {' → '.join(actions[:15])}\n\n"
    if last_snapshot:
        evidence += f"Last page state observed:\n{last_snapshot}\n\n"

    user_content = (
        f"Then clause to verify:\n{then_clause}\n\n"
        + evidence
        + "Based ONLY on the evidence above, respond with a JSON object."
    )

    clean_messages = [
        {"role": "system", "content": (PROMPTS_DIR / "extractor_system.md").read_text()},
        {"role": "user", "content": user_content},
    ]

    try:
        response = complete(
            extractor_config,
            clean_messages,
            max_tokens=300,
            _usage=_usage,
        )
        content = (response.choices[0].message.content or "").strip()
        # Strip markdown fences — some models wrap JSON in ```json ... ```
        if content.startswith("```"):
            content = re.sub(r"^```[^\n]*\n?", "", content)
            content = re.sub(r"\n?```$", "", content.rstrip())
            content = content.strip()
        parsed = json.loads(content)
        if (
            isinstance(parsed, dict)
            and parsed.get("status") in ("pass", "fail")
            and "actual" in parsed
            and "reasoning" in parsed
        ):
            return parsed
        console.print(f"[dim red]Extractor returned unexpected shape: {content[:100]}[/dim red]")
    except Exception as e:
        console.print(f"[dim red]Verdict extraction error: {e}[/dim red]")

    return None


# ---------------------------------------------------------------------------
# Playwright MCP server params (shared by executor and preflight)
# ---------------------------------------------------------------------------

def _make_server_params(cdp_endpoint: str | None = None) -> StdioServerParameters:
    """Build MCP server launch params.

    If cdp_endpoint is given (Browserbase), connect to the remote browser via
    CDP — no local browser is launched. Otherwise launch a local headless
    browser with an isolated context per scenario (QA_BROWSER, default chromium).
    """
    if cdp_endpoint:
        return StdioServerParameters(
            command="npx",
            args=["@playwright/mcp", f"--cdp-endpoint={cdp_endpoint}"],
        )
    browser = os.getenv("QA_BROWSER", "chromium")
    return StdioServerParameters(
        command="npx",
        args=["@playwright/mcp", "--headless", "--isolated", f"--browser={browser}"],
    )


async def preflight_check() -> None:
    """Verify npx, Playwright MCP tools, and the browser are all available.

    Raises RuntimeError with a human-readable fix hint on any failure.
    Three steps:
      1. (sync)  npx in PATH — Node.js installed?
      2. (async) MCP session starts + all essential tools present
      3. (async) browser_navigate("about:blank") — browser actually launches?
    """
    console = Console()
    console.rule("[bold]Preflight check[/bold]")

    # Step 1 — npx available
    if not shutil.which("npx"):
        console.print("[red]✗[/red] npx not found in PATH")
        raise RuntimeError("npx not found — install Node.js (https://nodejs.org)")
    console.print("[green]✓[/green] npx found")

    # Steps 2 + 3 — single MCP session
    browser = os.getenv("QA_BROWSER", "chromium")

    if browser == "browserbase" and not browserbase.is_configured():
        raise RuntimeError(
            "QA_BROWSER=browserbase is set but QA_BROWSERBASE_API_KEY / "
            "QA_BROWSERBASE_PROJECT_ID are missing. Set them or unset QA_BROWSER."
        )

    # Browserbase: create a cloud session if configured
    bb_session_id: str | None = None
    cdp_endpoint: str | None = None
    if browserbase.is_configured():
        console.print("[dim]Browserbase: creating preflight session...[/dim]")
        bb_session_id, cdp_endpoint = browserbase.create_session()
        console.print(f"[green]✓[/green] Browserbase session {bb_session_id}")

    server_params = _make_server_params(cdp_endpoint)

    try:
        async with stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()

                # Step 2 — tool discovery
                mcp_tools = await session.list_tools()
                available = {t.name for t in mcp_tools.tools}
                missing = _ESSENTIAL_TOOLS - available
                if missing:
                    console.print(f"[red]✗[/red] Missing essential tools: {missing}")
                    raise RuntimeError(f"MCP server missing tools: {missing}")
                console.print(
                    f"[green]✓[/green] {len(mcp_tools.tools)} tools available "
                    f"({len(_ESSENTIAL_TOOLS)}/{len(_ESSENTIAL_TOOLS)} essential present)"
                )

                # Step 3 — real browser launch
                nav_result = await session.call_tool(
                    "browser_navigate", {"url": "https://playwright.dev"}
                )
                nav_text = "\n".join(
                    c.text for c in nav_result.content if hasattr(c, "text")
                )
                _browser_error_markers = ("not installed", "is not found", "not found", "cannot find")
                if any(m in nav_text.lower() for m in _browser_error_markers):
                    label = "Browserbase" if cdp_endpoint else f"Browser '{browser}'"
                    console.print(f"[red]✗[/red] {label} not available")
                    if not cdp_endpoint:
                        console.print(f"[dim]  Fix: npx @playwright/mcp install-browser {browser}[/dim]")
                    raise RuntimeError(f"{label} not available: {nav_text[:200]}")
                label = "Browserbase" if cdp_endpoint else f"Browser '{browser}'"
                console.print(f"[green]✓[/green] {label} responsive")

    except RuntimeError:
        raise
    except Exception as e:
        console.print(f"[red]✗[/red] MCP server failed to start: {e}")
        raise RuntimeError(f"Playwright MCP failed: {e}") from e
    finally:
        if bb_session_id:
            browserbase.delete_session(bb_session_id)

    console.print("[bold green]Preflight passed.[/bold green]\n")


# ---------------------------------------------------------------------------
# Main executor
# ---------------------------------------------------------------------------

# _TEST_TIMEOUT_DEFAULTS imported from llm.router (per-model resolution)


async def run_requirement(
    req: dict,
    url: str,
    config: LLMConfig | None = None,
    test_timeout: int | None = ...,  # type: ignore[assignment]
    context: str = "",
    sink: LogSink | None = None,
) -> dict:
    if config is None:
        config = LLMConfig.from_env(role="executor")

    ensure_provider_running(config)

    # Sentinel ... means "use provider default"; None means "no cap"
    if test_timeout is ...:  # type: ignore[comparison-overlap]
        env_val = os.getenv("QA_TEST_TIMEOUT")
        if env_val is not None:
            test_timeout = int(env_val)
        else:
            test_timeout = _resolve_timeout(_TEST_TIMEOUT_DEFAULTS, config.provider, config.resolved_model())

    console = Console()
    console.rule(
        f"[bold]{req['id']}[/bold] — {req['title']} "
        f"[dim]({config.provider}/{config.resolved_model()})[/dim]"
    )
    console.print(f"[dim]Given:[/dim] {req['given']}")
    console.print(f"[dim]When: [/dim] {req['when']}")
    console.print(f"[dim]Then: [/dim] {req['then']}")
    console.print()

    # Browserbase: create a cloud session before starting Playwright MCP.
    # Each scenario gets its own isolated session (equivalent to --isolated locally).
    bb_session_id: str | None = None
    cdp_endpoint: str | None = None
    bb_session_start: float = 0.0
    if browserbase.is_configured():
        console.print("[dim]Browserbase: creating session...[/dim]")
        bb_session_id, cdp_endpoint = browserbase.create_session()
        bb_session_start = time.monotonic()
        console.print(f"[dim]Browserbase session: {bb_session_id}[/dim]")

    server_params = _make_server_params(cdp_endpoint)

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            mcp_tools = await session.list_tools()
            # Determine slim mode: explicit override > auto-detect
            if config.force_slim is not None:
                slim = config.force_slim
            else:
                slim = config.provider == "ollama"  # auto: only Ollama defaults to slim
            all_tools = _mcp_to_openai_tools(mcp_tools, slim=slim) + [_REPORT_TOOL]
            num_tools = len(all_tools) - 1  # exclude report_result
            console.print(f"[dim]Tools: {num_tools}/21 ({'slim' if slim else 'full'})[/dim]")

            messages: list[dict] = [
                {"role": "system", "content": _system_prompt()},
                {"role": "user", "content": _user_message(req, url, context)},
            ]

            actions_log: list[dict] = []
            guard_count = 0
            pending_correction: str | None = None
            verdict: dict | None = None
            scenario_usage: dict = {}  # accumulates token counts across all complete() calls

            # Bootstrap: pre-navigate + snapshot before the LLM loop.
            # Ollama: needed to initiate tool calls reliably for small models.
            # Anthropic: avoids first-turn navigation overhead and feeds single-shot.
            # Disable with QA_NO_BOOTSTRAP=true. Uses the URL from the Given clause
            # if one is specified (e.g. "la URL-ul /produse").
            should_bootstrap = (
                config.provider in ("ollama", "anthropic")
                and not os.getenv("QA_NO_BOOTSTRAP")
            )
            snap_text: str | None = None
            if should_bootstrap:
                snap_depth = int(os.getenv("QA_BOOTSTRAP_DEPTH", "5"))
                snap_text, boot_messages, boot_actions = await _bootstrap(
                    session, req, url, snap_depth, console
                )
                messages.extend(boot_messages)
                actions_log.extend(boot_actions)

            # Single-shot verdict: skip the tool loop entirely for Then-only scenarios
            # on Anthropic. Saves tool definitions (~6K) + multi-turn snapshot accumulation.
            # Falls through to tool loop on any failure (verdict stays None).
            then_only = not req.get("when", "").strip()
            if (config.provider == "anthropic" and then_only
                    and snap_text and verdict is None):
                _ss = await _single_shot_verify(
                    config, req, context, snap_text, console, _usage=scenario_usage
                )
                if _ss and _ss.get("status") == "pass":
                    verdict = _ss
                # fail falls through to tool loop — element may be below the fold

            bootstrap_count = len(actions_log)  # actions added by model start after this index
            action_counts: dict[str, int] = {}   # tracks (tool, primary_arg) repetitions
            consecutive_snapshots = 0            # counts snapshot-only turns in a row
            loop_threshold = int(os.getenv("QA_LOOP_THRESHOLD", "1"))
            # Max turns: lower default for Anthropic (12) vs Ollama (25, where test_timeout is primary cap)
            _default_max_turns = MAX_TURNS if config.provider == "ollama" else 12
            max_turns = int(os.getenv("QA_MAX_TURNS", _default_max_turns))
            start = time.monotonic()

            for turn in range(max_turns):
                if verdict is not None:
                    break

                if test_timeout and (time.monotonic() - start) >= test_timeout:
                    console.print(f"[red]Test timeout ({test_timeout}s) exceeded[/red]")
                    verdict = {
                        "status": "fail",
                        "actual": "Test did not complete within the time limit",
                        "reasoning": f"test_timeout={test_timeout}s exceeded after {turn} turns",
                    }
                    break

                try:
                    response = complete(config, messages, tools=all_tools, _usage=scenario_usage)
                except Exception as e:
                    verdict = {
                        "status": "error",
                        "actual": f"LLM error: {e}",
                        "reasoning": str(e),
                    }
                    break

                choice = response.choices[0]
                msg = choice.message
                if os.getenv("QA_DEBUG"):
                    import sys
                    print(f"[DEBUG turn={turn}] finish={choice.finish_reason!r} "
                          f"content={msg.content!r} tool_calls={msg.tool_calls!r}", file=sys.stderr)

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
                        # Fallback B: {"type":"function","function":{"name":"...","arguments":{...}}}
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
                                _mt = [a["tool"] for a in actions_log[bootstrap_count:]]
                                _v, guard_count, _c = _when_guardrail(ghost_args, req, _mt, guard_count)
                                if _v is not None:
                                    verdict = _v
                                    break
                                if _c:
                                    console.print(f"[dim yellow]When-action guardrail ({guard_count}/{_MAX_WHEN_RETRIES}) — '{req.get('when', '')}'[/dim yellow]")
                                    messages.append({"role": "user", "content": _c})
                                continue
                            ghost_id = parsed.get("id", f"ghost_{turn}")
                            args_preview = _esc_markup(json.dumps(ghost_args, ensure_ascii=False)[:100])
                            console.print(f"  [dim yellow]Ghost-B → {ghost_name}({args_preview})[/dim yellow]")
                            actions_log.append({"tool": ghost_name, "input": ghost_args})
                            mcp_result = await session.call_tool(ghost_name, ghost_args)
                            ghost_result_text = "\n".join(
                                c.text for c in mcp_result.content if hasattr(c, "text")
                            )
                            messages[-1] = {
                                "role": "assistant",
                                "tool_calls": [{
                                    "id": ghost_id, "type": "function",
                                    "function": {"name": ghost_name, "arguments": json.dumps(ghost_args)},
                                }],
                            }
                            messages.append({"role": "tool", "tool_call_id": ghost_id, "content": ghost_result_text})
                            continue
                        # Fallback C: {"function":"<name>","parameters":{...},...}
                        # llama3.1 / some Ollama models emit this format under tool_choice=required
                        if (
                            isinstance(parsed, dict)
                            and isinstance(parsed.get("function"), str)
                            and parsed["function"]
                        ):
                            ghost_name = parsed["function"]
                            ghost_args = parsed.get("parameters") or parsed.get("arguments") or {}
                            if isinstance(ghost_args, str):
                                ghost_args = json.loads(ghost_args) if ghost_args else {}
                            if ghost_name == "report_result":
                                console.print("[dim yellow]Fallback-C: report_result ghost call[/dim yellow]")
                                _mt = [a["tool"] for a in actions_log[bootstrap_count:]]
                                _v, guard_count, _c = _when_guardrail(ghost_args, req, _mt, guard_count)
                                if _v is not None:
                                    verdict = _v
                                    break
                                if _c:
                                    console.print(f"[dim yellow]When-action guardrail ({guard_count}/{_MAX_WHEN_RETRIES}) — '{req.get('when', '')}'[/dim yellow]")
                                    messages.append({"role": "user", "content": _c})
                                continue
                            ghost_id = f"ghost_c_{turn}"
                            args_preview = _esc_markup(json.dumps(ghost_args, ensure_ascii=False)[:100])
                            console.print(f"  [dim yellow]Ghost-C → {ghost_name}({args_preview})[/dim yellow]")
                            actions_log.append({"tool": ghost_name, "input": ghost_args})
                            mcp_result = await session.call_tool(ghost_name, ghost_args)
                            ghost_result_text = "\n".join(
                                c.text for c in mcp_result.content if hasattr(c, "text")
                            )
                            messages[-1] = {
                                "role": "assistant",
                                "tool_calls": [{
                                    "id": ghost_id, "type": "function",
                                    "function": {"name": ghost_name, "arguments": json.dumps(ghost_args)},
                                }],
                            }
                            messages.append({"role": "tool", "tool_call_id": ghost_id, "content": ghost_result_text})
                            continue
                        # Fallback D: {"type":"function","name":"<name>","parameters":{...}}
                        # flat variant — name at top level, no nested "function" dict
                        if (
                            isinstance(parsed, dict)
                            and parsed.get("type") == "function"
                            and isinstance(parsed.get("name"), str)
                            and parsed["name"]
                        ):
                            ghost_name = parsed["name"]
                            ghost_args = parsed.get("parameters") or parsed.get("arguments") or {}
                            if isinstance(ghost_args, str):
                                ghost_args = json.loads(ghost_args) if ghost_args else {}
                            if ghost_name == "report_result":
                                console.print("[dim yellow]Fallback-D: report_result ghost call[/dim yellow]")
                                _mt = [a["tool"] for a in actions_log[bootstrap_count:]]
                                _v, guard_count, _c = _when_guardrail(ghost_args, req, _mt, guard_count)
                                if _v is not None:
                                    verdict = _v
                                    break
                                if _c:
                                    console.print(f"[dim yellow]When-action guardrail ({guard_count}/{_MAX_WHEN_RETRIES}) — '{req.get('when', '')}'[/dim yellow]")
                                    messages.append({"role": "user", "content": _c})
                                continue
                            ghost_id = f"ghost_d_{turn}"
                            args_preview = _esc_markup(json.dumps(ghost_args, ensure_ascii=False)[:100])
                            console.print(f"  [dim yellow]Ghost-D → {ghost_name}({args_preview})[/dim yellow]")
                            actions_log.append({"tool": ghost_name, "input": ghost_args})
                            mcp_result = await session.call_tool(ghost_name, ghost_args)
                            ghost_result_text = "\n".join(
                                c.text for c in mcp_result.content if hasattr(c, "text")
                            )
                            messages[-1] = {
                                "role": "assistant",
                                "tool_calls": [{
                                    "id": ghost_id, "type": "function",
                                    "function": {"name": ghost_name, "arguments": json.dumps(ghost_args)},
                                }],
                            }
                            messages.append({"role": "tool", "tool_call_id": ghost_id, "content": ghost_result_text})
                            continue
                        # Fallback E: {"<tool_name>": {args}} — tool name as the sole key
                        if isinstance(parsed, dict) and len(parsed) == 1:
                            ghost_name, ghost_args = next(iter(parsed.items()))
                            if isinstance(ghost_name, str) and isinstance(ghost_args, dict):
                                if ghost_name == "report_result":
                                    console.print("[dim yellow]Fallback-E: report_result ghost call[/dim yellow]")
                                    _mt = [a["tool"] for a in actions_log[bootstrap_count:]]
                                    _v, guard_count, _c = _when_guardrail(ghost_args, req, _mt, guard_count)
                                    if _v is not None:
                                        verdict = _v
                                        break
                                    if _c:
                                        console.print(f"[dim yellow]When-action guardrail ({guard_count}/{_MAX_WHEN_RETRIES}) — '{req.get('when', '')}'[/dim yellow]")
                                        messages.append({"role": "user", "content": _c})
                                    continue
                                ghost_id = f"ghost_e_{turn}"
                                args_preview = _esc_markup(json.dumps(ghost_args, ensure_ascii=False)[:100])
                                console.print(f"  [dim yellow]Ghost-E → {ghost_name}({args_preview})[/dim yellow]")
                                actions_log.append({"tool": ghost_name, "input": ghost_args})
                                mcp_result = await session.call_tool(ghost_name, ghost_args)
                                ghost_result_text = "\n".join(
                                    c.text for c in mcp_result.content if hasattr(c, "text")
                                )
                                messages[-1] = {
                                    "role": "assistant",
                                    "tool_calls": [{
                                        "id": ghost_id, "type": "function",
                                        "function": {"name": ghost_name, "arguments": json.dumps(ghost_args)},
                                    }],
                                }
                                messages.append({"role": "tool", "tool_call_id": ghost_id, "content": ghost_result_text})
                                continue
                        # Fallback F: {"tool_calls":[{"type":"function","function":{"name":"...","arguments":{...}}}]}
                        # model wraps a single tool call in a tool_calls array
                        if (
                            isinstance(parsed, dict)
                            and isinstance(parsed.get("tool_calls"), list)
                            and parsed["tool_calls"]
                            and isinstance(parsed["tool_calls"][0], dict)
                        ):
                            first = parsed["tool_calls"][0]
                            fn = first.get("function") if isinstance(first.get("function"), dict) else {}
                            ghost_name = fn.get("name", "")
                            if ghost_name:
                                ghost_args = fn.get("arguments") or {}
                                if isinstance(ghost_args, str):
                                    ghost_args = json.loads(ghost_args) if ghost_args else {}
                                if ghost_name == "report_result":
                                    console.print("[dim yellow]Fallback-F: report_result ghost call[/dim yellow]")
                                    _mt = [a["tool"] for a in actions_log[bootstrap_count:]]
                                    _v, guard_count, _c = _when_guardrail(ghost_args, req, _mt, guard_count)
                                    if _v is not None:
                                        verdict = _v
                                        break
                                    if _c:
                                        console.print(f"[dim yellow]When-action guardrail ({guard_count}/{_MAX_WHEN_RETRIES}) — '{req.get('when', '')}'[/dim yellow]")
                                        messages.append({"role": "user", "content": _c})
                                    continue
                                ghost_id = f"ghost_f_{turn}"
                                args_preview = _esc_markup(json.dumps(ghost_args, ensure_ascii=False)[:100])
                                console.print(f"  [dim yellow]Ghost-F → {ghost_name}({args_preview})[/dim yellow]")
                                actions_log.append({"tool": ghost_name, "input": ghost_args})
                                mcp_result = await session.call_tool(ghost_name, ghost_args)
                                ghost_result_text = "\n".join(
                                    c.text for c in mcp_result.content if hasattr(c, "text")
                                )
                                messages[-1] = {
                                    "role": "assistant",
                                    "tool_calls": [{
                                        "id": ghost_id, "type": "function",
                                        "function": {"name": ghost_name, "arguments": json.dumps(ghost_args)},
                                    }],
                                }
                                messages.append({"role": "tool", "tool_call_id": ghost_id, "content": ghost_result_text})
                                continue
                        # Fallback G: {"id":"...","name":"<tool>","args":{...}} — flat, no "function" key
                        if (
                            isinstance(parsed, dict)
                            and isinstance(parsed.get("name"), str)
                            and parsed["name"]
                            and "function" not in parsed
                            and "tool_calls" not in parsed
                        ):
                            ghost_name = parsed["name"]
                            ghost_args = parsed.get("args") or parsed.get("arguments") or parsed.get("parameters") or {}
                            if isinstance(ghost_args, str):
                                ghost_args = json.loads(ghost_args) if ghost_args else {}
                            if isinstance(ghost_args, dict):
                                if ghost_name == "report_result":
                                    console.print("[dim yellow]Fallback-G: report_result ghost call[/dim yellow]")
                                    _mt = [a["tool"] for a in actions_log[bootstrap_count:]]
                                    _v, guard_count, _c = _when_guardrail(ghost_args, req, _mt, guard_count)
                                    if _v is not None:
                                        verdict = _v
                                        break
                                    if _c:
                                        console.print(f"[dim yellow]When-action guardrail ({guard_count}/{_MAX_WHEN_RETRIES}) — '{req.get('when', '')}'[/dim yellow]")
                                        messages.append({"role": "user", "content": _c})
                                    continue
                                ghost_id = f"ghost_g_{turn}"
                                args_preview = _esc_markup(json.dumps(ghost_args, ensure_ascii=False)[:100])
                                console.print(f"  [dim yellow]Ghost-G → {ghost_name}({args_preview})[/dim yellow]")
                                actions_log.append({"tool": ghost_name, "input": ghost_args})
                                mcp_result = await session.call_tool(ghost_name, ghost_args)
                                ghost_result_text = "\n".join(
                                    c.text for c in mcp_result.content if hasattr(c, "text")
                                )
                                messages[-1] = {
                                    "role": "assistant",
                                    "tool_calls": [{
                                        "id": ghost_id, "type": "function",
                                        "function": {"name": ghost_name, "arguments": json.dumps(ghost_args)},
                                    }],
                                }
                                messages.append({"role": "tool", "tool_call_id": ghost_id, "content": ghost_result_text})
                                continue
                    except (json.JSONDecodeError, TypeError):
                        pass
                    console.print(
                        "[yellow]Warning: agent stopped without calling report_result[/yellow]"
                    )
                    verdict = await _extract_verdict(
                        config, messages, req.get("then", ""), console, _usage=scenario_usage
                    )
                    if not verdict:
                        verdict = {
                            "status": "fail",
                            "actual": content_str or "No output",
                            "reasoning": "report_result was never called — extraction also failed",
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
                        _mt = [a["tool"] for a in actions_log[bootstrap_count:]]
                        _v, guard_count, _c = _when_guardrail(args, req, _mt, guard_count)
                        if _v is not None:
                            verdict = _v
                            break
                        if _c:
                            console.print(f"[dim yellow]When-action guardrail ({guard_count}/{_MAX_WHEN_RETRIES}) — '{req.get('when', '')}'[/dim yellow]")
                            tool_results.append({"role": "tool", "tool_call_id": tc.id, "content": "report_result blocked by When-action guardrail."})
                            pending_correction = _c
                        break

                    # Loop guard: block repeated stateful actions BEFORE executing them.
                    # Takes a fresh snapshot instead so the model has current page context.
                    # Threshold=1 means each unique (tool, target) can execute at most once.
                    # _LOOP_GUARD_SKIP tools are exempt: they are idempotent or intentionally
                    # repeatable (scrolling, waiting, key presses).
                    if name not in _LOOP_GUARD_SKIP:
                        _primary = args.get("target") or args.get("url") or ""
                        _loop_key = f"{name}:{_primary}"
                        if action_counts.get(_loop_key, 0) >= loop_threshold:
                            console.print(
                                f"[dim yellow]Loop guard — blocking {name}"
                                f"({_esc_markup(_primary[:60])}) "
                                f"already called {action_counts[_loop_key]}×[/dim yellow]"
                            )
                            _snap_depth = int(os.getenv("QA_SNAPSHOT_DEPTH", "5"))
                            snap_result = await session.call_tool("browser_snapshot", {"depth": _snap_depth})
                            snap_text = "\n".join(
                                c.text for c in snap_result.content if hasattr(c, "text")
                            )
                            tool_results.append({
                                "role": "tool",
                                "tool_call_id": tc.id,
                                "content": (
                                    f"[LOOP GUARD] {name}({_primary!r}) blocked — "
                                    f"already executed {action_counts[_loop_key]} time(s). "
                                    "The action has already been performed.\n\n"
                                    f"Current page state:\n{snap_text}\n\n"
                                    "Do NOT call any navigation element again. "
                                    "Verify the Then conditions from the page state above "
                                    "and call report_result."
                                ),
                            })
                            continue
                        action_counts[_loop_key] = action_counts.get(_loop_key, 0) + 1

                    # Normalize snapshot args: strip targeted snapshots and bound depth.
                    # Targeted snapshots (target=ref) give a narrow element-only view,
                    # hiding the rest of the page — harmful for all models/providers.
                    if name == "browser_snapshot":
                        args = {k: v for k, v in args.items() if k != "target"}
                        if "depth" not in args:
                            args["depth"] = int(os.getenv("QA_SNAPSHOT_DEPTH", "5"))

                    args_preview = _esc_markup(json.dumps(args, ensure_ascii=False)[:100])
                    console.print(f"  [dim cyan]→ {name}({args_preview})[/dim cyan]")
                    if sink:
                        human = _humanize_tool_call(name, args)
                        if human:
                            sink.emit(human)
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
                    _prune_stale_snapshots(messages)
                    _last_action = next(
                        (a["tool"] for a in reversed(actions_log[bootstrap_count:])), None
                    )
                    if _last_action in ("browser_snapshot", "browser_take_screenshot"):
                        consecutive_snapshots += 1
                    else:
                        consecutive_snapshots = 0
                    if not verdict:
                        if consecutive_snapshots == 2:
                            messages.append({
                                "role": "user",
                                "content": (
                                    "You have taken consecutive snapshots without any other action. "
                                    "If the target element is not visible, the page may need scrolling. "
                                    "Call browser_evaluate with "
                                    '{"expression": "window.scrollBy(0, 800)"} '
                                    "to scroll down, then snapshot again."
                                ),
                            })
                        elif consecutive_snapshots == 4:
                            messages.append({
                                "role": "user",
                                "content": (
                                    "You have now taken 4 consecutive snapshots. "
                                    "If the target element is not visible after scrolling, "
                                    "it is likely absent from this page. "
                                    "Call report_result with your best verdict now."
                                ),
                            })
                if pending_correction:
                    messages.append({"role": "user", "content": pending_correction})
                    pending_correction = None

            if not verdict:
                # Turn budget exhausted — try to extract a verdict from conversation history
                # before hard-failing. This produces a useful actual/reasoning instead of
                # the generic "Turn budget exhausted" message.
                verdict = await _extract_verdict(
                    config, messages, req.get("then", ""), console
                )
                if not verdict:
                    verdict = {
                        "status": "fail",
                        "actual": f"No verdict after {max_turns} turns",
                        "reasoning": "Turn budget exhausted — extractor also failed",
                    }

            duration = round(time.monotonic() - start, 1)

            # Display result
            console.print()
            status = (verdict.get("status") or "fail").upper()
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

            cost = estimate_cost(config.resolved_model(), scenario_usage)
            if cost is not None:
                scenario_usage["cost_usd"] = round(cost, 6)

            bb_duration = (
                round(time.monotonic() - bb_session_start, 1) if bb_session_id else None
            )
            if bb_session_id:
                browserbase.delete_session(bb_session_id)
                bb_session_id = None  # prevent double-delete

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
                "browser": "browserbase" if cdp_endpoint else "local",
                "bb_session_duration_s": bb_duration,
                "usage": scenario_usage,
            }


