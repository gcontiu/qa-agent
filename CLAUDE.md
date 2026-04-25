# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

For commands and folder structure see README.md

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

---

## What *not* to build

- Do not use `ZeroStep` — the project is archived/unmaintained as of 2024.
- Do not wire `behave` or `pytest-bdd` step definitions — the point of using Gherkin here is LLM interpretation, not Python bindings.
- Do not put `suggested_fix_hints` that reference the SUT's source paths unless `--source-path` is explicitly provided. That would break agnosticism.
- Do not take a snapshot (`browser_snapshot`) after every action — it balloons token cost. Snapshot only after navigation or state-changing clicks, or when the LLM explicitly requests one.

## Conventions

- **Language:** Romanian is fine in user-facing conversation and commit messages; code, identifiers, and spec keywords stay English.
- **Spec IDs:** Requirements carry stable IDs (e.g. `GP-001`). IDs live in Gherkin tags (`@id:GP-001`) or YAML `id:` fields. The state store keys off these — do not rename them lightly.
- **Evidence paths:** Always relative to the run directory so reports are portable.
- **Token estimate:** Estimate cost before every task; ask scoping questions if > 2000 tokens before doing any work.
- **Backward compatibility:** Before any change, run the checklist in `docs/backward-compatibility-rule.md`.

## Reference docs

- `docs/backward-compatibility-rule.md` — mandatory checklist before every change
- `docs/local-llms.md` — Ollama auto-start, slim/full tools, ghost fallbacks, bootstrap navigation, per-model compatibility matrix
- `docs/timeout-strategy.md` — per-call LLM timeout and per-test soft timeout configuration
