# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Setup (first time)
bash scripts/install.sh

# Smoke test — validates Agent SDK + Playwright MCP chain
uv run python -m qa_agent.smoke [url]

# Run executor on hardcoded requirement GB-002 (lobby buttons visible)
uv run python -m qa_agent.agent
```

`uv` manages the Python 3.12 virtualenv automatically. No manual `pip install` needed.

## Goal

A QA agent that:

1. Ingests specifications (one or more files) for any software target (web app, CLI, REST API).
2. Plans a testing strategy from those specs.
3. Executes tests autonomously.
4. Produces a structured report (JSON + markdown) consumable by downstream agents (notably a fix-agent).

The agent must be **agnostic** — the same binary/package must test different products by swapping the spec directory, with no code changes.

## Architectural decisions (tentative, pre-implementation)

These reflect the current design direction from the evaluation of `propunere1.md`. They are not yet locked in — if code is being written against a different choice, follow the code and update this file.

- **Runtime:** Claude Agent SDK (Python) for the agentic loop — not a hand-rolled tool-use loop. Subagents (`planner`, `executor`, `reporter`) live as markdown files, not hardcoded prompts.
- **Browser layer:** Playwright MCP (official Microsoft, `@playwright/mcp`) as an MCP server, consumed by the Agent SDK. Uses accessibility tree (not screenshots) — cheap and deterministic. A custom MCP server (small, ~100 LOC) hosts non-browser tools (API calls, DB seeding, artifact I/O).
- **Spec formats:** Dual support.
  - `.feature` (Gherkin) for behavioral end-to-end scenarios — parsed with `gherkin-official`, *not* run through `behave`/`pytest-bdd` (we do not want step-definition bindings; the LLM interprets steps as free text).
  - `.yaml` for API tests, config, and fixtures.
- **Fixtures:** Declarative YAML by default; imperative Python modules as an escape hatch. Support `function` / `scenario` / `feature` / `session` scopes (pytest-style). Cache session-scoped fixture state under `reports/.state/fixtures/` to avoid re-running expensive setup.
- **Invocation contract:** Expose both a CLI (`qa-agent run --spec ... --output ...`) *and* an MCP server so downstream agents (fix-agent) can call tools like `run_spec`, `get_last_report`, `rerun_failing` natively.
- **Output contract:** Stable JSON schema under `reports/run-<ID>/report.json` with `summary`, `results[]`, and per-failure `evidence` (screenshots, DOM snapshot, actions log). `code_hints` is *optional* and only populated when `--source-path` is passed — keeping the agent agnostic by default.
- **State store:** SQLite or JSON under `reports/.state/` tracks last status per `requirement_id` (powers `--only-failing`), flakiness, and seeds for reproducibility.
- **Telemetry:** Per-run `telemetry.json` with token counts, cost, latency breakdown, cache hit rate.
- **LLM provider:** Configurable per-role via env vars (`QA_EXECUTOR_PROVIDER`, `QA_REPORTER_PROVIDER`, etc.) through LiteLLM. Supports `anthropic` (default) and `ollama`. Set `QA_PROVIDER=ollama` to use local models for all roles.

## Ollama / small-model compatibility (`llm/router.py`, `agent.py`)

`qwen2.5:7b` (and similar small models) have two known quirks when used via LiteLLM tool-calling:

1. **Too many tools causes hallucination.** With 21 Playwright MCP tools exposed, the model ignores them and invents a fake answer. Fix: `_mcp_to_openai_tools(slim=True)` filters to 8 essential tools (`browser_navigate`, `browser_snapshot`, `browser_click`, `browser_type`, `browser_fill_form`, `browser_press_key`, `browser_wait_for`, `browser_select_option`). Activated automatically when `config.provider == "ollama"`.

2. **Ghost tool calls / serialized JSON output.** After receiving a tool result, the model sometimes outputs a tool call as plain-text JSON in `message.content` instead of as a structured `tool_calls` entry. Two fallbacks handle this:
   - **Fallback-A:** if `content` is valid JSON with `status` + `actual` keys → treat it as a `report_result` call.
   - **Fallback-B:** if `content` is valid JSON with `type: "function"` + `function.name` → execute the named tool, rewrite the last assistant message as a proper tool_call, and continue the loop.

## Timeout Strategy (`llm/router.py`, `agent.py`)

Two independent timeout layers prevent unbounded waits and runaway LLM calls:

### Per-Call LLM Timeout (`LLMConfig.llm_timeout`)

**What it does:** Each `litellm.completion()` call has a hard HTTP timeout. If the LLM provider doesn't respond within the timeout, LiteLLM raises `litellm.Timeout`, which is caught and reported as `status: error`.

**When it triggers:**
- LLM inference is too slow (e.g., Ollama on CPU running a large model)
- Network connectivity issue with the LLM provider
- LLM provider is overloaded and slow to respond

**Example failure (qwen2.5:7b on CPU):**
```
status: error
actual: "LLM error: litellm.APIConnectionError: OllamaException - litellm.Timeout: Connection timed out after 120.0 seconds."
reasoning: (same as actual)
```

**Configuration:**
- **Default:** `ollama=120s`, `anthropic=30s` (hardcoded in `_LLM_TIMEOUT_DEFAULTS`)
- **Override:** Set `QA_LLM_TIMEOUT=<seconds>` env var
  ```bash
  QA_LLM_TIMEOUT=180 uv run python -m qa_agent.agent  # increase to 180s
  QA_LLM_TIMEOUT=10 uv run python -m qa_agent.agent   # strict 10s cutoff for testing
  ```
- **Per-role:** Use `QA_EXECUTOR_LLM_TIMEOUT`, `QA_REPORTER_LLM_TIMEOUT`, etc. (read by `from_env(role=...)`)

**Tuning advice:**
- **Ollama on GPU:** 30–60s (fast inference)
- **Ollama on CPU:** 90–180s (slow inference; each turn takes ~60s per 7B model)
- **Anthropic API:** 20–30s (very fast; rarely needed)
- For CI/CD: set aggressively low (e.g. 30s) to fail fast; for local development, be generous

### Per-Test Soft Timeout (`run_requirement(test_timeout)`)

**What it does:** A soft timeout checked at the start of each turn in the main executor loop. If total elapsed time since test start exceeds `test_timeout`, the loop breaks and returns `status: fail` with reason "time limit exceeded".

**Why "soft"?** LiteLLM's `completion()` call is synchronous and blocks the entire event loop. Python's `asyncio.wait_for()` cannot interrupt a running synchronous call. The test timeout is checked *between* turns, not during them. Therefore:
- **Hard guarantee:** A single LLM call will not exceed `llm_timeout`
- **Soft guarantee:** Total test time *usually* won't exceed `test_timeout`, but if an LLM call starts near the deadline, it may run past it

**When it triggers:**
- LLM makes many turns without converging (model loops endlessly)
- Each turn takes longer than expected (e.g., model producing very long outputs)
- Playwright MCP tool calls are unexpectedly slow

**Example failure:**
```
Actual: "Test did not complete within the time limit"
Reasoning: "test_timeout=360s exceeded after 4 turns"
```

**Configuration:**
- **Default:** `ollama=360s`, `anthropic=None` (hardcoded in `_TEST_TIMEOUT_DEFAULTS`)
  - Ollama: 360s = ~3–4 turns at 90–120s per turn (reasonable buffer)
  - Anthropic: `None` = no cap (fast enough that timeout is rarely needed)
- **Override:** Set `QA_TEST_TIMEOUT=<seconds>` env var
  ```bash
  QA_TEST_TIMEOUT=120 uv run python -m qa_agent.agent  # fail if test takes >120s
  QA_TEST_TIMEOUT=600 uv run python -m qa_agent.agent  # generous 10min per test
  ```
- **In code:** Pass `test_timeout=180` to `run_requirement()` directly

**Tuning advice:**
- **For Ollama:** 180–360s (2–4 turns; model may loop or retry)
- **For Anthropic:** `None` or 120–180s (conservative, prevents infinite loops)
- **For CI/CD:** Set per-test timeout to 5–10 min per requirement; in combination with per-call timeout, prevents stuck jobs

### Timeout Interaction Example

Scenario: running GB-002 (Lobby buttons visible) with Ollama.

```bash
QA_PROVIDER=ollama QA_LLM_TIMEOUT=120 QA_TEST_TIMEOUT=360 uv run python -m qa_agent.agent
```

**Turn 1 (T=0–110s):** LLM inference takes 110s (under 120s limit) → continue
**Turn 2 (T=110–230s):** LLM inference takes 120s (at 120s limit) → continue
**Turn 3 (T=230–350s):** LLM inference takes 120s (at 120s limit) → continue
**Turn 4 start (T=350s):** Check `350 >= 360`? No → call LLM
**Turn 4 (T=350–470s):** LLM inference takes 120s → exceeds test_timeout mid-call
  → Test timeout check only happens at *next* turn start (T=470s)
  → 470 >= 360? Yes → break, return `status: fail`, reason "test_timeout=360s exceeded after 4 turns"

Result: test runs ~470s (slightly over the 360s soft limit due to synchronous LLM call).

---

## What *not* to build

- Do not use `ZeroStep` — the project is archived/unmaintained as of 2024.
- Do not wire `behave` or `pytest-bdd` step definitions — the point of using Gherkin here is LLM interpretation, not Python bindings.
- Do not put `suggested_fix_hints` that reference the SUT's source paths unless `--source-path` is explicitly provided. That would break agnosticism.
- Do not take a snapshot (`browser_snapshot`) after every action — it balloons token cost. Snapshot only after navigation or state-changing clicks, or when the LLM explicitly requests one.

## Proposed directory layout (from `propunere1.md`, adjusted)

```
qa-agent/
├── src/qa_agent/
│   ├── cli.py              # Typer entrypoint
│   ├── mcp_server.py       # exposes qa-agent as MCP to other agents
│   ├── agent.py            # Agent SDK orchestration
│   ├── specs/              # loader + Pydantic schema (YAML + Gherkin)
│   ├── fixtures/           # declarative + imperative fixture runtime
│   ├── tools/              # custom MCP server (api, db seed, artifacts)
│   └── prompts/            # subagent markdown files
├── specs/                  # user-provided spec directories (per product)
├── reports/                # gitignored; run artifacts + state store
└── tests/                  # the agent's own tests
```

## Conventions

- **Language:** Romanian is fine in user-facing conversation and commit messages; code, identifiers, and spec keywords stay English.
- **Spec IDs:** Requirements carry stable IDs (e.g. `GP-001`). IDs live in Gherkin tags (`@id:GP-001`) or YAML `id:` fields. The state store keys off these — do not rename them lightly.
- **Evidence paths:** Always relative to the run directory so reports are portable.
- [Token estimate before starting tasks] Estimate cost before every taskl ask scoping questions if > 2000 tokens before doing any work