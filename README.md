
## Commands

```bash
# Setup (first time)
bash scripts/install.sh
npx playwright install chromium   # required once — installs the headless browser

# Smoke test — validates Agent SDK + Playwright MCP chain
uv run python -m qa_agent.smoke [url]

# Run a spec suite
uv run qa-agent run <spec-dir> [--output <reports-dir>]

# Re-run only failing requirements from the last run
uv run qa-agent run <spec-dir> --only-failing

# List past runs
uv run qa-agent list-runs

# Show a report
uv run qa-agent show-report <run-id>
```

`uv` manages the Python 3.12 virtualenv automatically. No manual `pip install` needed.

The `npx playwright install chromium` step downloads the Chromium headless shell (~90 MB) to `~/.cache/ms-playwright/`. It is a one-time per-machine step. Without it `browser_snapshot` fails with "Chromium distribution not found".

---

## Environment variables

### Provider & model

| Variable | Default | Description |
|---|---|---|
| `QA_PROVIDER` | `anthropic` | LLM provider for all roles (`anthropic`, `ollama`, `together_ai`) |
| `QA_MODEL` | _(role default)_ | Model name override for all roles |
| `QA_EXECUTOR_PROVIDER` | `QA_PROVIDER` | Provider for the executor role only |
| `QA_EXECUTOR_MODEL` | _(role default)_ | Model for the executor role only |
| `QA_EXTRACTOR_PROVIDER` | executor's provider | Provider for verdict extraction |
| `QA_EXTRACTOR_MODEL` | _(role default)_ | Model for verdict extraction |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama server URL |
| `TOGETHER_API_KEY` | _(required for together_ai)_ | Together.ai API key |

Default models per role:

| Role | Anthropic | Together.ai | Ollama |
|---|---|---|---|
| executor | `claude-sonnet-4-6` | `meta-llama/Llama-3.3-70B-Instruct-Turbo` | `qwen2.5:7b` |
| extractor | `claude-haiku-4-5-20251001` | `Qwen/Qwen2.5-7B-Instruct-Turbo` | `qwen2.5:7b` |
| analyst | `claude-opus-4-7` | `meta-llama/Llama-3.3-70B-Instruct-Turbo` | `qwen2.5:14b` |

### Timeouts

| Variable | Default | Description |
|---|---|---|
| `QA_LLM_TIMEOUT` | per-model (see below) | Per-call HTTP timeout in seconds |
| `QA_TEST_TIMEOUT` | per-model (see below) | Soft timeout per test scenario in seconds |

Per-model LLM timeout defaults (Ollama):

| Model | Default |
|---|---|
| `qwen2.5:14b` | 90s |
| `mistral-small:22b` | 300s |
| `qwen2.5:32b` | 150s |
| _(all others)_ | 120s |

### Execution behaviour

| Variable | Default | Description |
|---|---|---|
| `QA_FORCE_SLIM` | _(auto)_ | `true` = 8-tool slim set; `false` = full 21-tool set; unset = auto (slim for Ollama, full for Anthropic) |
| `QA_TOOL_CHOICE` | _(unset)_ | Set to `required` to force tool calls on every turn (fixes llama3.1:8b planning loop; breaks qwen2.5:7b) |
| `QA_NO_BOOTSTRAP` | _(unset)_ | Set to `true` to disable bootstrap navigation pre-injection for Ollama |
| `QA_BOOTSTRAP_DEPTH` | `5` | Accessibility tree depth for the bootstrap snapshot. Reduce to `3` on dense pages to shrink input context |

### Ollama context window

| Variable | Default | Description |
|---|---|---|
| `QA_NUM_CTX` | `8192` | `num_ctx` passed to Ollama on every request. Ollama's own default (4096) is too small for browser snapshots + tool definitions + system prompt. Increase for very long conversations; decrease on low-RAM machines |

### Rate limit retry

| Variable | Default | Description |
|---|---|---|
| `QA_RATE_LIMIT_RETRIES` | `2` | Max retries on `RateLimitError` (Anthropic, Together.ai, OpenAI). Set to `0` to disable |
| `QA_RATE_LIMIT_WAIT` | `60` | Seconds before retry 1; doubles for retry 2 (60s → 120s). Applies to all providers |

### Diagnostics

| Variable | Default | Description |
|---|---|---|
| `QA_VERBOSE_LLM` | _(unset)_ | Set to `true` to log each LLM turn to stderr: model name, role, tool calls or text output |

---

## Example runs

```bash
# Anthropic (default) — full alconind suite
uv run qa-agent run specs/alconind --output reports/alconind-full

# Together.ai — Starter tier candidate (Llama 3.3 70B)
QA_EXECUTOR_PROVIDER=together_ai \
QA_VERBOSE_LLM=true \
uv run qa-agent run specs/alconind-smoke --output reports/alconind-smoke-together-70b

# Together.ai — Free tier candidate (Qwen 2.5 7B Turbo)
QA_EXECUTOR_PROVIDER=together_ai \
QA_EXECUTOR_MODEL=Qwen/Qwen2.5-7B-Instruct-Turbo \
QA_VERBOSE_LLM=true \
uv run qa-agent run specs/alconind-smoke --output reports/alconind-smoke-together-7b

# Ollama — smoke test with mistral-small:22b
QA_EXECUTOR_PROVIDER=ollama \
QA_EXECUTOR_MODEL=mistral-small:22b \
QA_BOOTSTRAP_DEPTH=6 \
QA_VERBOSE_LLM=true \
uv run qa-agent run specs/alconind-smoke

# Re-run only failures from last run
uv run qa-agent run specs/alconind --only-failing

# Ollama debug — verbose LLM output, slim tools, reduced snapshot depth
QA_EXECUTOR_PROVIDER=ollama \
QA_EXECUTOR_MODEL=mistral-small:22b \
QA_FORCE_SLIM=true \
QA_BOOTSTRAP_DEPTH=4 \
QA_VERBOSE_LLM=true \
uv run qa-agent run specs/alconind-smoke
```
