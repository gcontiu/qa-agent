## Local provider auto-start (`llm/router.py`)

`ensure_provider_running(config)` is called automatically at the start of every test. It:

1. Checks if the provider is in `_LOCAL_PROVIDERS` — remote APIs (anthropic, openai) are skipped.
2. Does an HTTP health check against `config.base_url`.
3. If unreachable, finds the provider executable via `_resolve_executable(cmd_candidates)` — tries PATH first, then a list of well-known macOS/Linux paths.
4. Spawns the process in the background and polls until reachable (up to `ready_timeout` seconds).

**Adding a new local provider** — add one entry to `_LOCAL_PROVIDERS` in `router.py`:

```python
"myprovider": {
    "cmd_candidates": ["myprovider", "/usr/local/bin/myprovider"],
    "start_args": ["serve"],
    "health_path": "/health",   # appended to config.base_url
    "ready_timeout": 20,
},
```

**Current registry:**

| Provider | Executable locations | Health path | Timeout |
|----------|---------------------|-------------|---------|
| `ollama` | PATH, `/usr/local/bin`, `/opt/homebrew/bin`, `/Applications/Ollama.app/...` | `/` | 20s |
| `vllm` | PATH, `/usr/local/bin/vllm` | `/health` | 60s |
| `lmstudio` | PATH, `/usr/local/bin`, `/Applications/LM Studio.app/...` | `/v1/models` | 30s |

## Ollama / small-model compatibility (`llm/router.py`, `agent.py`)

`qwen2.5:7b` (and similar small models) have several known quirks when used via LiteLLM tool-calling:

### 1. Too many tools causes hallucination

With 21 Playwright MCP tools exposed, the model ignores them and invents a fake answer. Fix: `_mcp_to_openai_tools(slim=True)` filters to 8 essential tools (`browser_navigate`, `browser_snapshot`, `browser_click`, `browser_type`, `browser_fill_form`, `browser_press_key`, `browser_wait_for`, `browser_select_option`).

- **Default behavior (auto-detect):** Slim mode activated only for Ollama provider
- **Override with `QA_FORCE_SLIM` env var:**
  ```bash
  QA_FORCE_SLIM=true   # Force slim mode (8 tools) for any provider
  QA_FORCE_SLIM=false  # Force full mode (21 tools) for Ollama with capable models
  # Not set → auto-detect: Ollama=slim, others=full
  ```
- **When to use `QA_FORCE_SLIM=false`:**
  ```bash
  QA_EXECUTOR_PROVIDER=ollama QA_EXECUTOR_MODEL=llama3.1:8b QA_FORCE_SLIM=false uv run python -m qa_agent.agent
  # llama3.1:8b on M4 Pro GPU handles the full 21-tool set correctly
  ```

### 2. Model outputs test plan instead of calling tools

Some models (observed: `llama3.1:8b` in early tests) output a JSON test plan as plain text instead of executing tool calls. `tool_choice="required"` forces a tool call on every response.

**This is opt-in** via `QA_TOOL_CHOICE=required`. It is NOT the default.

**Why not default:** `qwen2.5:7b` was confirmed to regress with `tool_choice="required"` — it enters a `browser_snapshot` loop and never calls `report_result`. Without `tool_choice`, qwen2.5:7b works correctly via ghost call fallbacks.

**Confirmed model behavior (as of last test session):**

| Model | slim | `tool_choice=required` | Outcome |
|-------|------|----------------------|---------|
| qwen2.5:7b | ✓ (default) | ✗ regresses (snapshot loop) | Use default — no `QA_TOOL_CHOICE` |
| llama3.1:8b | off (`QA_FORCE_SLIM=false`) | not needed — bootstrap is enough | Use default — no `QA_TOOL_CHOICE` |
| llama3.1:8b | off | `QA_TOOL_CHOICE=required` | Also works, but unnecessary |

```bash
# Only use if a new model outputs test plans with the default config:
QA_TOOL_CHOICE=required uv run python -m qa_agent.agent
```

### 3. Ghost tool calls / serialized JSON output

After receiving a tool result, models sometimes output a tool call as plain-text JSON in `message.content` instead of as a structured `tool_calls` entry. Four fallbacks handle every observed format:

| Fallback | Detected format | Observed in |
|----------|----------------|-------------|
| **A** | `{"status":"…","actual":"…"}` | Any model — plain report_result |
| **B** | `{"type":"function","function":{"name":"…","arguments":{…}}}` | qwen2.5:7b, llama3.1:8b, qwen2.5:14b |
| **C** | `{"function":"<name>","parameters":{…}}` | llama3.1:8b under `tool_choice=required` |
| **D** | `{"type":"function","name":"<name>","parameters":{…}}` | llama3.1:8b (flat variant) |
| **E** | `{"<tool_name>":{…}}` — sole key is the tool name | llama3.1:8b (wrapper variant) |
| **F** | `{"tool_calls":[{"type":"function","function":{"name":"…"}}]}` — array wrapper | qwen2.5:14b |
| **G** | `{"name":"<tool>","args":{…}}` — flat, no "function" key | qwen2.5:14b (turn exhaustion) |

Each ghost call is executed via MCP and rewritten as a proper `tool_call` + `tool` result pair so the conversation history stays well-formed for subsequent turns.

**Adding support for a new ghost format:** add a new `Fallback-E` block inside the `if finish in ("stop", "end_turn") or not msg.tool_calls:` branch in `agent.py`, following the same pattern as B/C/D.

### 4. Bootstrap — navigate + snapshot (Ollama only)

For `provider == "ollama"`, `run_requirement()` pre-executes two MCP calls before the LLM loop starts and injects them into message history as completed tool calls:

1. `browser_navigate(url)` — page is loaded
2. `browser_snapshot()` — **Variant B**: model receives the full accessibility tree with element refs at turn 0

The model starts mid-stream with both the page loaded and its structure visible. It can immediately act on elements (click, type) without spending a turn on orientation.

**Without bootstrap snapshot** — turn 0 is wasted:
```
Turn 0: browser_snapshot({})   ← model takes snapshot to see the page (~23s)
Turn 1: browser_click(ref="e77")  ← now it can act
```

**With bootstrap snapshot** — model acts immediately:
```
Turn 0: browser_click(ref="e77")  ← refs already in context from bootstrap
```

**Side effects:**
- Both bootstrap actions count in `actions_log`.
- The model may still call `browser_navigate` or `browser_snapshot` again — both are idempotent.
- Does not apply to Anthropic — those models initiate correctly on their own.

**Disable if the pre-injected context confuses a model:**
```bash
QA_NO_BOOTSTRAP=true uv run python -m qa_agent.agent
```