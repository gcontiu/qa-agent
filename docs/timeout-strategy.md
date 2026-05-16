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

### Rate-Limit Retry (`complete()` in `router.py`)

**What it does:** When a provider returns a rate-limit error (`litellm.RateLimitError`), `complete()` waits and retries rather than propagating the error as a test `ERROR` verdict.

**Why needed:** Anthropic's free/Tier-1 API enforces a 30,000 input-token-per-minute limit. A single alconind.ro page snapshot plus tool definitions approaches this limit, so back-to-back scenarios exhaust the quota within seconds. Without retry, consecutive tests fail with `ERROR` even though the LLM is fully operational.

**Behavior:**
- Retry up to `QA_RATE_LIMIT_RETRIES` times (default: **2** extra attempts = 3 total)
- Wait `QA_RATE_LIMIT_WAIT × (attempt + 1)` seconds before each retry (default: **60s**, then **120s**)
- Logs each wait to stderr: `[qa-agent] RateLimitError — waiting 60s before retry 1/2 (anthropic/claude-sonnet-4-6)...`
- After exhausting retries, re-raises the error (becomes `status: error` in the report)

**Configuration:**

```bash
QA_RATE_LIMIT_RETRIES=2   # default — 2 retries after first failure
QA_RATE_LIMIT_WAIT=60     # default — 60s before retry 1, 120s before retry 2
QA_RATE_LIMIT_RETRIES=0   # disable retry (fail immediately on rate limit)
QA_RATE_LIMIT_WAIT=30     # shorter wait (if you know your quota resets faster)
```

**Provider applicability:** Fires on any provider that returns `RateLimitError` — Anthropic, Together.ai, OpenAI. No effect on Ollama (local inference, no rate limits).

**Interaction with test timeout:** The wait counts toward `QA_TEST_TIMEOUT`. A 60s retry wait on a scenario with a 180s test timeout will exhaust most of the budget. If running suites against rate-limited APIs, set `QA_TEST_TIMEOUT` generously or disable it (`QA_TEST_TIMEOUT=0`).

### Inter-Scenario Delay (`QA_SCENARIO_DELAY`)


**What it does:** Inserts an `asyncio.sleep()` pause *between* scenario executions — after one scenario completes and before the next Browserbase session is created.

**Why needed:** Anti-bot systems (Cloudflare, reCAPTCHA) detect repeated automated sessions from the same IP pool. Empirically observed on emag.ro: the first 6–7 consecutive Browserbase sessions succeed; subsequent ones trigger human-verification challenges. A short delay between sessions lowers the request frequency below the detection threshold.

**Defaults:**
- **API / cloud (`api.py`):** 3 seconds — always on, since cloud runs use Browserbase
- **CLI (`cli.py`):** 0 seconds — off by default for local Playwright runs (no anti-bot concern)

**Configuration:**
```bash
QA_SCENARIO_DELAY=5   # 5s between scenarios (aggressive anti-bot sites)
QA_SCENARIO_DELAY=0   # disable (local Playwright or trusted environments)
QA_SCENARIO_DELAY=3   # default in cloud API
```

**Interaction with run duration:** Adds `(N-1) × delay` seconds to total run time. For 20 scenarios with 3s delay: +57s overhead. Acceptable for cloud runs; disable for local speed.

**Example output:**
```
[qa-agent] RateLimitError — waiting 60s before retry 1/2 (anthropic/claude-sonnet-4-6)...
  → browser_snapshot({})
```

---

### Per-User API Rate Limiting (`slowapi`)

**What it does:** Limits how many expensive operations (executor runs and analyst crawls) a single user can trigger per hour. Prevents runaway LLM costs caused by accidental spam or a malicious actor.

**Applies to:**

| Endpoint | Limit | Rationale |
|---|---|---|
| `POST /runs` | **10/hour** | Executor run: ~$0.78 each — 10 runs = ~$7.80/user/hour cap |
| `POST /products/{id}/analyze` | **3/hour** | Analyst crawl: ~$1.40 each — 3 crawls = ~$4.20/user/hour cap |

All other endpoints (GET polling, spec CRUD) are unlimited — they are cheap reads with no LLM cost.

**Key function:** Limits are keyed on the **user UUID** extracted from the JWT `sub` claim. If the JWT is absent or invalid, falls back to client IP. This ensures the limit is per-authenticated-user, not per IP — two users on the same office network have independent buckets.

**Error response (HTTP 429):**
```json
{"detail": "Rate limit exceeded: 10 per 1 hour. Please try again later."}
```

**Implementation:** `slowapi` middleware registered on the FastAPI app (`api.py`). The `_rate_limit_key()` helper decodes the JWT header to extract `sub` without going through the `get_current_user` dependency.

**Impact on legitimate MVP users:**
A user testing their product typically does 1 analyst run + 2–3 executor runs in a session. Both limits reset hourly, so a typical day of 3–4 cycles (analyst + several runs) stays well within the caps. The limit only triggers for accidental loops or abuse.

**Dev mode:** When `SUPABASE_JWT_SECRET` is absent (local dev without Supabase), the key function falls back to IP. The limit still applies but is keyed on the machine's IP — effectively no isolation between roles, which is intentional for local dev.

**Changing the limits:** Edit the `@limiter.limit(...)` decorators in `src/qa_agent/api.py`. Limits use slowapi string format: `"N/period"` where period is `second`, `minute`, `hour`, `day`.

```python
# api.py — current defaults
@limiter.limit("10/hour")   # POST /runs
@limiter.limit("3/hour")    # POST /products/{id}/analyze
```