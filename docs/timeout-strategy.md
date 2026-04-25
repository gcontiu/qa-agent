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
- **Default:** per-model (see table below), resolved by `_resolve_timeout()` in `router.py`
- **Override:** Set `QA_LLM_TIMEOUT=<seconds>` env var — overrides all model-specific defaults
  ```bash
  QA_LLM_TIMEOUT=180 uv run python -m qa_agent.agent  # increase to 180s
  QA_LLM_TIMEOUT=10 uv run python -m qa_agent.agent   # strict 10s cutoff for testing
  ```
- **Per-role:** Use `QA_EXECUTOR_LLM_TIMEOUT`, `QA_REPORTER_LLM_TIMEOUT`, etc.

**Per-model defaults (`_LLM_TIMEOUT_DEFAULTS` in `router.py`):**

| Provider | Model | LLM timeout | Observed turn time |
|----------|-------|-------------|-------------------|
| anthropic | any | 30s | ~2s |
| ollama | qwen2.5:14b | 60s | ~23s (M4 Pro GPU) |
| ollama | qwen2.5:32b | 90s | — |
| ollama | any other | 120s | ~15s (7B GPU), ~60s (7B CPU) |

**Adding a new model:** add an entry to the `"ollama"` dict in `_LLM_TIMEOUT_DEFAULTS`. The `"__default__"` key covers all unlisted models.

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
- **Default:** per-model (see table below), resolved by `_resolve_timeout()` in `router.py`
- **Override:** Set `QA_TEST_TIMEOUT=<seconds>` env var
  ```bash
  QA_TEST_TIMEOUT=120 uv run python -m qa_agent.agent  # fail if test takes >120s
  QA_TEST_TIMEOUT=600 uv run python -m qa_agent.agent  # generous 10min per test
  ```
- **In code:** Pass `test_timeout=180` to `run_requirement()` directly

**Per-model defaults (`_TEST_TIMEOUT_DEFAULTS` in `router.py`):**

| Provider | Model | Test timeout | Rationale |
|----------|-------|-------------|-----------|
| anthropic | any | None (no cap) | ~2s/turn — virtually no risk of runaway |
| ollama | qwen2.5:14b | 180s | 23s/turn × ~8 turns max on M4 Pro GPU |
| ollama | any other | 360s | covers CPU inference at ~60s/turn × 6 turns |

**Adding a new model:** add an entry to the `"ollama"` dict in `_TEST_TIMEOUT_DEFAULTS`.

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