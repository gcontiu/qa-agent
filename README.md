
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

# Analyze a site and auto-generate Gherkin specs (full site)
uv run qa-agent analyze <url> -d "<description>" -p <PREFIX> -o specs/<name>

# Analyze a site — scoped to specific pages only (faster, cheaper on large sites)
uv run qa-agent analyze <url> -d "<description>" -p <PREFIX> --pages "/,/about,/contact" -o specs/<name>

# Start the HTTP API server (Phase 1 — cloud-readiness)
uv run qa-agent serve                    # default 0.0.0.0:8000
uv run qa-agent serve --port 9000 --reload  # dev mode with auto-reload
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

### Browserbase (cloud browser)

| Variable | Default | Description |
|---|---|---|
| `QA_BROWSERBASE_API_KEY` | _(required for Browserbase)_ | Browserbase API key |
| `QA_BROWSERBASE_PROJECT_ID` | _(required for Browserbase)_ | Browserbase project ID |
| `QA_BROWSERBASE_REGION` | `us-east-1` | Cloud region for browser session |
| `QA_BROWSERBASE_TIMEOUT` | `300` | Session timeout in seconds before auto-expiry |

Browserbase provides an alternative to local browser management for cloud deployments. The Phase 1 roadmap includes cost/latency validation to decide between Browserbase vs self-hosted Playwright on Modal/Fly.io.

### Analyst behaviour

| Flag / Variable | Default | Description |
|---|---|---|
| `--pages` | _(unset — explore whole site)_ | Comma-separated URL paths for the analyst to visit. When set, the analyst skips link discovery and navigates directly to each listed path. Use on large sites (news, e-commerce) to keep cost predictable. Generated `config.yaml` records the scope under `meta.scope.pages`. |

### Execution behaviour

| Variable | Default | Description |
|---|---|---|
| `QA_FORCE_SLIM` | _(auto)_ | `true` = 8-tool slim set; `false` = full 21-tool set; unset = auto (slim for Ollama, full for Anthropic) |
| `QA_TOOL_CHOICE` | _(unset)_ | Set to `required` to force tool calls on every turn (fixes llama3.1:8b planning loop; breaks qwen2.5:7b) |
| `QA_NO_BOOTSTRAP` | _(unset)_ | Set to `true` to disable bootstrap navigation pre-injection (applies to both Ollama and Anthropic) |
| `QA_BOOTSTRAP_DEPTH` | `5` | Accessibility tree depth for the Ollama bootstrap snapshot. Reduce to `3` on dense pages to shrink input context |
| `QA_SNAPSHOT_DEPTH` | `5` | Default accessibility tree depth for mid-loop `browser_snapshot` calls. Applied when the model omits depth; model can override by passing `depth` explicitly |
| `QA_MAX_TURNS` | `12` (Anthropic) / `25` (Ollama) | Max LLM turns per scenario before forcing verdict extraction. Lower = cheaper; raise if complex flows need more turns |
| `QA_LOOP_THRESHOLD` | `1` | Max executions of the same (tool, target) before the loop guard blocks it. At threshold=1, each navigation target can be clicked at most once — the second attempt is blocked, a fresh snapshot is taken, and the model is told to verify Then conditions instead |

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

### Analyst — generate specs

```bash
# Full site exploration (small sites, ~10 pages)
uv run qa-agent analyze https://www.alconind.ro \
  -d "Distribuitor B2B de produse metalurgice (țevi, profile, tablă). Site în română." \
  -p AC -o specs/alconind-v2

# Scoped to specific pages (large sites — news, e-commerce)
uv run qa-agent analyze https://newspaper.ro \
  -d "Romanian news portal" -p NWS \
  --pages "/,/politica,/sport,/economie,/cultura,/contact" \
  -o specs/newspaper

# Opus analyst (higher quality specs, ~$1.40 for a 10-page site)
uv run qa-agent analyze https://www.alconind.ro \
  --analyst-model claude-opus-4-7 \
  -d "..." -p AC -o specs/alconind-v2
```

### Anthropic

```bash
# Default — full suite, Sonnet (Pro/Starter tier)
uv run qa-agent run specs/alconind --output reports/alconind-full

# Haiku — Free tier config (~$0.056/run)
QA_EXECUTOR_MODEL=claude-haiku-4-5-20251001 \
uv run qa-agent run specs/alconind-smoke --output reports/alconind-smoke-haiku

# Re-run only failures from last run
uv run qa-agent run specs/alconind --only-failing
```

### Together.ai

```bash
# Llama 3.3 70B — 3/3 PASS, proper CALL, fast (~9s/scenario)
QA_EXECUTOR_PROVIDER=together_ai \
QA_EXECUTOR_MODEL=meta-llama/Llama-3.3-70B-Instruct-Turbo \
TOGETHER_API_KEY=<key> \
QA_VERBOSE_LLM=true \
uv run qa-agent run specs/alconind-smoke --output reports/alconind-smoke-together-70b

# Qwen 2.5 7B Turbo — cheapest (~$0.04/run), fragile on navigation scenarios
QA_EXECUTOR_PROVIDER=together_ai \
QA_EXECUTOR_MODEL=Qwen/Qwen2.5-7B-Instruct-Turbo \
TOGETHER_API_KEY=<key> \
QA_VERBOSE_LLM=true \
uv run qa-agent run specs/alconind-smoke --output reports/alconind-smoke-together-7b
```

**Note:** Together.ai only supports `tools` (function calling) for specific models.
Confirmed working: `Llama-3.3-70B-Instruct-Turbo`, `Qwen2.5-7B-Instruct-Turbo`.
Other models (Qwen 14B, Hermes-3 8B, Llama 3.1 8B) fail with `UnsupportedParamsError`.

### Ollama (local)

```bash
# mistral-small:22b — recommended local model, 3/3 PASS at depth=6
QA_EXECUTOR_PROVIDER=ollama \
QA_EXECUTOR_MODEL=mistral-small:22b \
QA_BOOTSTRAP_DEPTH=6 \
QA_VERBOSE_LLM=true \
uv run qa-agent run specs/alconind-smoke --output reports/alconind-smoke-mistral

# Debug run — slim tools, verbose, reduced depth
QA_EXECUTOR_PROVIDER=ollama \
QA_EXECUTOR_MODEL=mistral-small:22b \
QA_FORCE_SLIM=true \
QA_BOOTSTRAP_DEPTH=4 \
QA_VERBOSE_LLM=true \
uv run qa-agent run specs/alconind-smoke
```

### Browserbase integration (Phase 1 cloud-readiness)

```bash
# Run with Browserbase cloud browser instead of local Chromium
QA_BROWSERBASE_API_KEY=<key> \
QA_BROWSERBASE_PROJECT_ID=<project-id> \
uv run qa-agent run specs/alconind --output reports/alconind-browserbase

# Check telemetry for cost: look for "browser" field ("browserbase" | "local") 
# and "bb_session_duration_s" in results/[].browser_metadata
cat reports/alconind-browserbase/telemetry.json
```

### HTTP API (Phase 1 cloud-readiness)

Start the server:
```bash
uv run qa-agent serve
```

Then in another terminal:

```bash
# Create a run (returns run_id immediately, 202 Accepted)
RUN_ID=$(curl -s -X POST http://localhost:8000/runs \
  -H "Content-Type: application/json" \
  -d '{"spec_dir": "specs/alconind"}' | jq -r '.run_id')

# Poll status until done
curl http://localhost:8000/runs/$RUN_ID

# Get the report (when done)
curl http://localhost:8000/runs/$RUN_ID/report | jq '.summary'

# Cancel a running run
curl -X POST http://localhost:8000/runs/$RUN_ID/cancel

# List all runs
curl http://localhost:8000/runs

# Health check
curl http://localhost:8000/health
```

On server restart, any runs left in `running` or `pending` state are marked as `failed` with error "Interrupted by server restart". The status is persisted to disk so polling `GET /runs/{run_id}` works across server restarts.
