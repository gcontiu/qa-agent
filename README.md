

## Commands

```bash
# Setup (first time)
bash scripts/install.sh
npx playwright install chromium   # required once — installs the headless browser

# Smoke test — validates Agent SDK + Playwright MCP chain
uv run python -m qa_agent.smoke [url]

# Run executor on hardcoded requirement GB-002 (lobby buttons visible)
uv run python -m qa_agent.agent
```

`uv` manages the Python 3.12 virtualenv automatically. No manual `pip install` needed.

The `npx playwright install chromium` step downloads the Chromium headless shell (~90 MB) to `~/.cache/ms-playwright/`. It is a one-time per-machine step. Without it `browser_snapshot` fails with "Chromium distribution not found".


## Proposed Directory layout

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