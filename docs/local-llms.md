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
| qwen2.5:7b | ✓ (default) | ✗ regresses (snapshot loop) | Use default |
| qwen2.5:14b | ✓ (default) | not tested | 5/6 PASS — slim is optimal; full (21 tools) causes invented tool names |
| llama3.1:8b | off (`QA_FORCE_SLIM=false`) | not needed | Use default |

`QA_FORCE_SLIM=false` is not recommended for any tested model. Slim mode (8 tools) is the correct default for all Ollama models.

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

### 5. Bootstrap snapshot depth limit

Large accessibility trees (e.g. production marketing sites) overwhelm small models — they retrieve the data but fail to reason about it and never call `report_result`. The bootstrap snapshot now accepts a `depth` parameter to truncate the tree.

```bash
QA_BOOTSTRAP_DEPTH=5 uv run python -m qa_agent.agent  # default
QA_BOOTSTRAP_DEPTH=3 uv run python -m qa_agent.agent  # for very dense pages
```

Lower values mean less context and faster inference, but risk hiding nested elements (e.g. links inside cards inside sections). `depth=5` is the empirical sweet spot for qwen2.5:14b.

---

## Summary of local-LLM runs to date

Empirical results across two test targets:
- **German Brawl** (gaming site, simple DOM, ~6 scenarios)
- **alconind.ro** (industrial B2B marketing site, dense DOM, 7 homepage scenarios)

| Model | Hardware | German Brawl | alconind.ro | Primary failure mode |
|-------|----------|--------------|-------------|----------------------|
| `qwen2.5:7b` | M4 Pro (CPU/GPU) | ✓ stable with slim+bootstrap | not tested at scale | Limited reasoning on dense pages — fine for simple sites |
| `qwen2.5:14b` | M4 Pro GPU | ✓ 5/6 PASS | partial: 2/7 PASS (only homepage AC-001/AC-002) | **Does not call `report_result` on large accessibility trees** — emits JSON verdict as text in `message.content` instead of structured tool call. Ghost fallbacks F/G recover some, not all |
| `qwen2.5:32b` | M4 Pro | not tested | **0/7 PASS — every scenario LLM-timeout at 150s** | Hardware bottleneck: 19GB weights + memory bandwidth limit on Apple Silicon. Inference too slow even with extended timeouts. Not viable on this hardware |
| `llama3.1:8b` | M4 Pro GPU | ✓ functional | not tested | Outputs full test plan as JSON text instead of tool calls. Requires `QA_TOOL_CHOICE=required` + ghost fallbacks C/D/E to function |

### Key takeaways

1. **Tool-calling is solved; reasoning is the bottleneck.** All ghost-output edge cases (A–G) are now caught by fallbacks. The remaining failure mode is *the model retrieves correct evidence but does not synthesize a verdict* on dense pages.

2. **Ollama is viable only for simple/medium-complexity targets.** Production marketing sites with 100+ accessibility-tree nodes per page exceed what `qwen2.5:7b` and `qwen2.5:14b` reliably handle end-to-end.

3. **Hardware ceiling on M4 Pro** is around 14B parameters. `qwen2.5:32b` is not memory-bandwidth-feasible — even when not OOM, inference is slow enough that 150s LLM timeout (already 5× the Anthropic default) is exhausted before the first response.

4. **Recommended configurations:**
   - **Local-only, simple targets:** `qwen2.5:14b` with `QA_BOOTSTRAP_DEPTH=3-5`, slim mode (default), no `tool_choice`.
   - **Hybrid (best cost/reliability):** `QA_EXECUTOR_PROVIDER=anthropic` + `QA_PLANNER_PROVIDER=ollama` + `QA_REPORTER_PROVIDER=ollama`. Cuts API spend ~75% while keeping the difficult role on a capable model.
   - **Anthropic-only:** the only path with consistent passes on production marketing sites today.

5. **Future evaluation candidates** (not yet tested in this repo): `qwen2.5-coder:14b` (specialized for tool-use), `mistral-small:22b` (fits in M4 Pro RAM), `llama3.3:8b` (improved tool-calling over 3.1). vLLM with MLX backend remains an unexplored optimization for Apple Silicon throughput.