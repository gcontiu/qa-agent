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

---

## Ollama / small-model compatibility (`llm/router.py`, `agent.py`)

### 1. Too many tools causes hallucination

With 21 Playwright MCP tools exposed, the model ignores them and invents a fake answer. Fix: `_mcp_to_openai_tools(slim=True)` filters to 8 essential tools (`browser_navigate`, `browser_snapshot`, `browser_click`, `browser_type`, `browser_fill_form`, `browser_press_key`, `browser_wait_for`, `browser_select_option`).

- **Default behavior (auto-detect):** Slim mode activated only for Ollama provider
- **Override with `QA_FORCE_SLIM` env var:**
  ```bash
  QA_FORCE_SLIM=true   # Force slim mode (8 tools) for any provider
  QA_FORCE_SLIM=false  # Force full mode (21 tools) — only tested successfully with mistral-small:22b
  # Not set → auto-detect: Ollama=slim, others=full
  ```

### 2. Model outputs test plan instead of calling tools

Some models output a JSON test plan as plain text instead of executing tool calls. `tool_choice="required"` forces a tool call on every response.

**This is opt-in** via `QA_TOOL_CHOICE=required`. It is NOT the default.

**Why not default:** `qwen2.5:7b` was confirmed to regress with `tool_choice="required"` — it enters a `browser_snapshot` loop and never calls `report_result`.

**Confirmed model behavior:**

| Model | slim | `tool_choice=required` | Outcome |
|-------|------|----------------------|---------|
| qwen2.5:7b | ✓ (default) | ✗ regresses (snapshot loop) | Use default |
| qwen2.5:14b | ✓ (default) | not tested | Ghost-B/F/G fallbacks handle output |
| mistral-small:22b | ✓ default, ✗ full not needed | not needed | Emits proper CALL — best local performer |
| llama3.1:8b | ✓ (default) | not tested | Mixed CALL+TEXT; structural Given/Then confusion |

### 3. Ghost tool calls / serialized JSON output

After receiving a tool result, models sometimes output a tool call as plain-text JSON in `message.content` instead of as a structured `tool_calls` entry. Seven fallbacks handle every observed format:

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

**Important:** `[ref=eXX]` values in ghost call args are passed correctly to MCP. Earlier logs made it appear refs were stripped — this was a rich markup rendering bug (fixed: `_esc_markup()` applied to all args previews in `agent.py`).

### 4. Bootstrap — navigate + snapshot (Ollama only)

For `provider == "ollama"`, `run_requirement()` pre-executes two MCP calls before the LLM loop starts and injects them into message history as completed tool calls:

1. `browser_navigate(boot_url)` — page is loaded at the URL extracted from the Given clause (see §6)
2. `browser_snapshot(depth=N)` — model receives the full accessibility tree with element refs at turn 0

The model starts mid-stream with both the page loaded and its structure visible.

**Disable if the pre-injected context confuses a model:**
```bash
QA_NO_BOOTSTRAP=true uv run qa-agent run ...
```

### 5. Bootstrap snapshot depth limit

Large accessibility trees overwhelm small models — they retrieve the data but fail to reason about it. The bootstrap snapshot accepts a `depth` parameter to truncate the tree.

```bash
QA_BOOTSTRAP_DEPTH=4   # was default; shown to be too shallow for /produse
QA_BOOTSTRAP_DEPTH=5   # previous default
QA_BOOTSTRAP_DEPTH=6   # confirmed correct for alconind.ro /produse page
```

**Empirical findings (alconind.ro, mistral-small:22b):**

| depth | AC-001 (homepage) | AC-100 (/produse categories) | Notes |
|-------|-------------------|------------------------------|-------|
| 4 | PASS | **FAIL** — only Țevi visible; Profile Laminate/Tablă Metalică truncated | Too shallow |
| 6 | PASS | **PASS** — all three categories visible | +15% time cost |

**Current default:** `QA_BOOTSTRAP_DEPTH=5` (env var). For pages with deeply nested category sections (e.g. product listing pages), use `6`.

### 6. Bootstrap URL from Given clause

Bootstrap now extracts a specific URL path from the Given clause if present, rather than always navigating to the base target URL.

```
Given: utilizatorul accesează pagina de produse la URL-ul /produse
→ bootstrap navigates to https://www.alconind.ro/produse  (not the root)
```

Pattern matched: `"URL-ul /path"`, `"URL /path"` (case-insensitive, Romanian and English).

**Why this matters:** Without this fix, scenarios with `Given: accesează /produse` had the model navigating from root, spending 10+ ghost turns on CSS/XPath selectors trying to reach the right page (and often failing).

### 7. Ollama context window — `num_ctx`

Ollama defaults to `num_ctx=4096` if not specified. This is far too small for browser snapshot + system prompt + tool definitions (typically 6,000–15,000 tokens on real pages).

**Symptom:** model sees only the first part of the page, misses navigation menus or content, reports FAIL or makes hallucinated verdicts.

**Fix:** `extra_kwargs()` for Ollama now passes `num_ctx` on every request via `extra_body.options`. Override with `QA_NUM_CTX`.

```bash
QA_NUM_CTX=8192    # default — sufficient for depth=4-6 on most pages
QA_NUM_CTX=16384   # for very long conversations or many ghost fallback turns
QA_NUM_CTX=4096    # reduce on low-RAM machines
```

**Note on model reload:** Changing `num_ctx` between runs forces Ollama to reload the model with a new KV cache. First request after a `num_ctx` change is slower. Consistent `num_ctx` = no reload penalty.

### 8. Determinism — temperature, seed

**Problem:** Without fixed sampling parameters, identical inputs produce different outputs across runs, making it impossible to evaluate whether a prompt or code change helped.

**Fix:** `complete()` now passes `temperature=0` to all providers. Ollama additionally receives `top_p=1`, `top_k=1`, and a fixed `seed` via `extra_body.options`.

```bash
QA_TEMPERATURE=0    # default — deterministic (overrides to e.g. 0.7 for stochastic)
QA_SEED=42          # default Ollama seed (Anthropic does not expose seed)
```

**Provider-level determinism:**

| Provider | Mechanism | Guarantee |
|----------|-----------|-----------|
| Ollama | `temperature=0` + `top_k=1` + `top_p=1` + `seed=42` | ~99.5% token-identical across runs |
| Anthropic | `temperature=0` | ~99% — backend FP non-determinism introduces rare token-level variance |

**Practical impact:** with determinism, broken model behavior is consistently broken — you can iterate on prompts and code and observe reliable signal, rather than lucky/unlucky sampling.

### 9. When-action guardrail

**Problem:** Models (particularly qwen2.5:14b and mistral-small:22b at high bootstrap depth) report PASS for scenarios with a When action clause without actually performing the action — they infer a plausible verdict from the bootstrap snapshot alone.

**Fix:** `_when_guardrail()` in `agent.py` intercepts every `report_result(status=pass)` and checks whether the When clause required a browser action that was never executed.

**Behavior:**

1. Detects action verbs in When clause (Romanian + English): `apasă/click`, `completează/fill`, `selectează/select`, `trimite/submit`, `apasă tasta/press`
2. Checks `actions_log[bootstrap_count:]` — model-initiated actions only, bootstrap is excluded
3. If required tool (e.g. `browser_click`) is absent:
   - **Retry 1-2:** Injects corrective message: *"report_result blocked — you must call browser_click before reporting. Find the ref in the snapshot and perform the action."*
   - **After 2 retries:** Forces `status=fail` with guardrail reasoning
4. Applies to all 7 ghost fallback paths (B–G) and the regular CALL path

**When it does NOT fire:**
- When clause is empty (pure verification scenario like AC-001, AC-100)
- Required tool was performed by the model before report_result
- `status=fail` verdicts — only PASS verdicts are validated

**Known limitation — extractor bypass:** The guardrail only intercepts `report_result` calls (direct CALL or ghost A-G). If the model never reaches `report_result` at all (e.g. qwen2.5:14b emitting a test plan as TEXT that matches no ghost pattern, or qwen2.5-coder:14b emitting a safety refusal), the flow falls through to `_extract_verdict` which has no guardrail. The extractor can then synthesize a false-positive PASS. Extending the guardrail to `_extract_verdict` would close this gap.

**Max retries:** 2, controlled by `_MAX_WHEN_RETRIES` constant in `agent.py`.

---

## Summary of local-LLM runs to date

Empirical results across two test targets:
- **German Brawl** (gaming site, simple DOM, ~6 scenarios)
- **alconind.ro** (industrial B2B marketing site, dense DOM, 42 scenarios + 3-scenario smoke)

| Model | Hardware | Tool calls | Ghost fallbacks | alconind smoke (3 scenarios) | Primary failure mode |
|-------|----------|-----------|-----------------|------------------------------|----------------------|
| `qwen2.5:7b` | M4 Pro CPU | TEXT only | B | not tested at scale | Insufficient reasoning on dense pages |
| `qwen2.5:14b` | M4 Pro GPU | TEXT only (~100% Ghost-B/F/G) | B, F, G | 3/3 via fallback + extractor (false positives) | **Never emits proper CALL** — all verdicts via ghost fallback chain; snapshot loop on /produse |
| `qwen2.5-coder:14b` | M4 Pro GPU | Mixed (CALL on simple, Ghost-B on complex) | B | 3/3 via Ghost-B/extractor | **Safety refusal** on AC-003 (`"I'm sorry, but I can't assist with that request."`) — disqualifying for automation |
| `qwen2.5:32b` | M4 Pro | — | — | 0/3 (LLM timeout at 150s) | **Hardware bottleneck:** 19GB model exceeds M4 Pro memory bandwidth |
| `llama3.1:8b` | M4 Pro GPU | Mixed CALL+TEXT | B, C, D, E | 1/3 | Structural Given/Then confusion; treats Then conditions as Given preconditions |
| `mistral-small:22b` | M4 Pro GPU | **Proper CALL** (dominant) | G (rare) | **3/3 with depth=6** | Context-as-criteria confusion; partially addressed by system prompt rules |

### Key takeaways

1. **mistral-small:22b is the recommended local model on M4 Pro.** It is the only tested model that consistently emits proper `tool_calls` rather than ghost JSON. This removes the ghost fallback chain as a source of fragility.

2. **qwen2.5:14b never emits proper tool calls** in the current setup (LiteLLM → Ollama). All verdicts go through ghost fallback B/F/G → extractor. Works functionally but produces false positives (PASS without performing When actions). Root cause: likely a mismatch between LiteLLM's tool-call format translation and qwen2.5's Modelfile template in Ollama.

3. **llama3.1:8b has structural reasoning gaps.** It confuses Then conditions with Given preconditions, producing confident FAIL verdicts that are structurally wrong. Not recommended.

4. **`num_ctx=4096` (Ollama default) is always too small.** Real page snapshots + system prompt + tool definitions + conversation history typically exceed 6,000 tokens. Default raised to 8192 in `extra_kwargs()`.

5. **Determinism is now the default.** `temperature=0` + fixed seed ensures reproducible runs. Required for reliable prompt iteration and regression detection.

6. **Bootstrap depth matters per page type:**
   - Homepage/simple pages: `depth=4-5` sufficient
   - Product listing / deep-structured pages: `depth=6` required
   - Dense/complex pages: balance depth against model reasoning capacity

7. **Recommended configurations:**
   - **Local, any complexity:** `mistral-small:22b`, `QA_NUM_CTX=8192`, `QA_BOOTSTRAP_DEPTH=6`, slim tools (default)
   - **Hybrid (cost/reliability):** `QA_EXECUTOR_PROVIDER=anthropic` + Ollama for planner/reporter — cuts API spend ~75%
   - **Production / paid tiers:** Anthropic Sonnet — only path with consistent results on all page types

8. **qwen2.5-coder:14b is disqualified.** Tested 2026-05-04. Emits proper CALL only on simple direct-verification scenarios (AC-100); still uses Ghost-B on homepage checks (AC-001). Critical issue: **safety refusal** on benign navigation tasks (AC-003 — "I'm sorry, but I can't assist with that request."). A model that randomly refuses automation tasks cannot be used in production. Do not retry.

9. **Future evaluation candidates:** `mistral-nemo:12b` (~7GB, Mistral tool-use optimized, faster than mistral-small:22b), `granite3-dense:8b` (IBM, agentic workflow training).
