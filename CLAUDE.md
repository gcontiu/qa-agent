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