# qa-agent — Architecture

Technical architecture reference. Describes how the system is structured, how components interact, and the rationale behind key design choices.

---

## System Overview

qa-agent is a spec-driven browser testing agent. It ingests Gherkin `.feature` files and YAML config, executes each scenario autonomously via a browser, and produces structured reports (JSON + Markdown).

```
specs/                   ← input: user-provided spec directories (per product)
  alconind/
    config.yaml          ← product config: URL, environments, context
    homepage.feature     ← Gherkin scenarios with stable IDs (@id:AC-001)

src/qa_agent/
  cli.py                 ← Typer entry point (qa-agent run / list-runs / show-report)
  agent.py               ← executor loop: LLM ↔ Playwright MCP ↔ verdicts
  analyst.py             ← spec generation from a live URL
  llm/
    router.py            ← LiteLLM abstraction: providers, defaults, timeouts
    __init__.py
  reporter/              ← Python-template report generation (no LLM)
  prompts/
    executor_system.md   ← system prompt for the executor role
  specs/                 ← Gherkin + YAML parser, Pydantic schema

reports/                 ← gitignored: run artifacts + state store
  .state/                ← SQLite: last status per requirement_id, flakiness
  run-<ID>/
    report.json          ← stable schema: summary, results[], evidence
    report.md
    telemetry.json
```

---

## LLM Provider Architecture

### Design principle

All LLM calls go through a single function `complete()` in `src/qa_agent/llm/router.py`. This function accepts a provider-agnostic `LLMConfig` and delegates to **LiteLLM**, which translates OpenAI-format requests to any provider's native API. Adding a new provider requires at most 5 lines in `router.py`.

### Roles

The agent uses three distinct LLM roles, each independently configurable:

| Role | Responsibility | Default model |
|------|---------------|---------------|
| `executor` | Drives the browser: navigates, snapshots, clicks, reports verdict | claude-sonnet-4-6 |
| `extractor` | Last-resort verdict extraction when executor doesn't call `report_result` | claude-haiku-4-5-20251001 |
| `analyst` | Generates Gherkin specs by crawling a live URL | claude-opus-4-7 |

Override per role: `QA_EXECUTOR_PROVIDER`, `QA_EXECUTOR_MODEL`, `QA_EXTRACTOR_PROVIDER`, etc.
Global override: `QA_PROVIDER`, `QA_MODEL`.

### Supported providers

| Provider key | Auth env var | Notes |
|---|---|---|
| `anthropic` | `ANTHROPIC_API_KEY` | Default. Production-grade reliability. |
| `ollama` | _(none, local)_ | Local development only. Auto-starts `ollama serve`. |
| `together_ai` | `TOGETHER_API_KEY` | Available as opt-in / BYOK. See constraints below. |
| `vllm` | _(none, local)_ | Self-hosted; needs `vllm serve <model>` running. |
| `lmstudio` | _(none, local)_ | LM Studio server mode. |

Adding a new remote provider: add a branch in `litellm_model()` and a defaults entry in `_DEFAULTS`. No other changes required.

### Provider selection — SaaS tier mapping

**Final configuration (as of 2026-05-04, see BD-001):**

| Tier | Provider | Executor model | Cost/run |
|------|----------|----------------|----------|
| Free (5 runs/month) | Anthropic | claude-haiku-4-5-20251001 | ~$0.056 |
| Starter ($19/month, 50 runs) | Anthropic | claude-sonnet-4-6 | ~$0.21 |
| Pro ($49/month, 200 runs) | Anthropic | claude-sonnet-4-6 | ~$0.21 |
| BYOK (any tier) | User's key | User's choice | $0 LLM cost |

**Why a single provider for all tiers:**

Empirical testing (2026-05-04) across Anthropic Sonnet, Anthropic Haiku, Together.ai Llama 3.3 70B, Together.ai Qwen 2.5 7B, and five local Ollama models revealed:

1. **Anthropic models are uniquely reliable** — 100% proper tool call format, chain-of-thought self-recovery from navigation loops, zero ghost fallbacks. All other models require fallback chains or fail on complex pages.

2. **Haiku is cheap enough for Free tier** — ~$0.056/run vs ~$0.04 for the best Together.ai alternative (Qwen 2.5 7B Turbo). The $0.016/run difference does not justify the quality degradation (Qwen 2.5 7B hallucinates tool response formats, requires extractor for every verdict, fails on interaction scenarios).

3. **Together.ai `tools` parameter constraint** — Together.ai only supports OpenAI function calling for a subset of hosted models. Llama 3.3 70B and Qwen 2.5 7B work; Qwen 2.5 14B, Hermes-3 8B, Llama 3.1 8B all fail with `UnsupportedParamsError`. This eliminates the mid-size cheap model tier that the original roadmap assumed.

4. **Single provider simplifies operations** — one API contract, one billing account, one set of failure modes in production. No provider-switching logic in the hot path.

**Together.ai remains available** as an opt-in BYOK option and as a hedge against Anthropic pricing changes. LiteLLM abstraction allows switching within hours if needed.

### Determinism

All LLM calls use `temperature=0` by default, making runs reproducible. Ollama additionally receives `top_k=1`, `top_p=1`, and a fixed `seed` via `extra_body.options`.

Override: `QA_TEMPERATURE=0.7` for stochastic behaviour, `QA_SEED=123` for a different seed.

### Reliability mechanisms in `complete()`

Beyond the basic call, `complete()` implements:

**Rate-limit retry:** catches `litellm.RateLimitError`, waits `QA_RATE_LIMIT_WAIT` seconds (default 60), retries up to `QA_RATE_LIMIT_RETRIES` times (default 2). Anthropic free/Tier-1 API enforces 30K input TPM; consecutive scenario runs hit this limit without retry logic.

**Ghost fallback chain (A–G):** when a model emits a tool call as plain-text JSON instead of a structured `tool_calls` entry, `agent.py` detects and executes it. Seven formats handled (A = plain report_result, B–G = various JSON wrapper formats observed in Qwen, Llama, Mistral families). All ghost calls are rewritten as proper `tool_call` + `tool` result pairs to keep conversation history well-formed.

**Verdict extraction fallback:** if the executor loop ends without a `report_result` call and all ghost fallbacks fail, a separate extractor LLM call synthesises a verdict from the pruned conversation history using structured JSON output.

**Loop guard:** if the same `(tool, target)` combination is called `QA_LOOP_THRESHOLD` times (default 1 = block on second attempt), the call is blocked before execution. A fresh `browser_snapshot` is taken and returned as the tool result with a corrective instruction. Prevents infinite click loops that occur when navigation menu links persist across pages with the same `[ref=eXX]` identifier.

**When-action guardrail:** if the executor reports `status=pass` but the When clause contained an action verb (`apasă`, `click`, `completează`, etc.) and no corresponding tool call was made, the verdict is blocked. A corrective message is injected and the model has up to `_MAX_WHEN_RETRIES` (2) attempts to perform the action before the verdict is forced to `fail`.

### Token cost optimisation

Three layers reduce token consumption for Anthropic runs. Together they cut a 36-scenario suite from ~$10 (baseline) to ~$1–1.50.

#### 1. Prompt caching (`router.py` — `_apply_anthropic_cache_control`)

Applied automatically for every Anthropic call. Two cache breakpoints are set:

| Breakpoint | What is cached | Cache write cost | Cache read cost |
|---|---|---|---|
| First system message | System prompt (~3K tokens) | 1.25× input | 0.1× input |
| Last tool definition | All 23 tool definitions (~6K tokens) | 1.25× input | 0.1× input |

For a 4-turn scenario the static 9K (system + tools) drops from 9K × 4 = 36K billed at full rate to one cache write (~11K) + three reads (~2.7K) = **~14K effective**. Across consecutive scenarios within the 5-minute TTL the cache persists, so scenario N+1 pays only cache reads on system + tools.

Implementation: `_apply_anthropic_cache_control(messages, tools)` converts the system message from a plain string to a `content` array with `cache_control: {type: "ephemeral"}`, and adds the same marker to the last tool dict. Does not mutate caller data.

#### 2. Stale snapshot pruning (`agent.py` — `_prune_stale_snapshots`)

After each turn's tool results are appended to the message history, all but the most recent `browser_snapshot` result are replaced with the placeholder `"[snapshot superseded — see latest snapshot above]"`. Old snapshots contain refs that no longer exist on the current page and serve no purpose in later turns.

Per scenario (avg 3 snapshots, 4 turns): without pruning the second and third snapshots are re-sent on every subsequent turn, accumulating ~75K duplicate tokens. With pruning only the latest ~25K snapshot is ever in the active context.

The pruner identifies snapshot results by cross-referencing `tool_call_id` fields in assistant messages where `function.name == "browser_snapshot"`. The bootstrap snapshot (Ollama) and loop-guard snapshots are handled by the same logic.

#### 3. Bounded snapshot depth (`agent.py` — `QA_SNAPSHOT_DEPTH`)

When the model calls `browser_snapshot` without a `depth` argument, the executor injects `depth=5` (configurable via `QA_SNAPSHOT_DEPTH`). Without a depth limit, MCP returns the full accessibility tree; on dense sites like alconind.ro this can exceed 1 500 nodes and 30K tokens per snapshot.

The model can override by explicitly passing `depth: N` in its tool call. The loop guard's corrective snapshot also uses `QA_SNAPSHOT_DEPTH`.

`QA_BOOTSTRAP_DEPTH` (Ollama bootstrap, default 5) is a separate knob for the pre-injection snapshot.

#### 4. Bootstrap (shared) + single-shot for Then-only scenarios (`agent.py`)

`_bootstrap()` pre-executes `browser_navigate` + `browser_snapshot` and returns the snapshot text plus the conversation messages and `actions_log` entries to merge into caller state. Used by both Ollama (initiates tool calls reliably for small models) and Anthropic (eliminates redundant first-turn navigation, feeds single-shot).

For scenarios with no `When` clause (`then_only = True`) on Anthropic, `_single_shot_verify()` skips the tool loop entirely. It calls the LLM with **only `report_result` available and `tool_choice="required"`**, forcing a structured tool call. The tool's enum schema (`["pass", "fail"]`) guarantees the verdict is well-formed across providers (Anthropic, OpenAI, Together.ai) — more reliable than `response_format=json_object`, which has inconsistent translation in LiteLLM.

Benefits per Then-only scenario (~25 of 33 in alconind):
- Eliminates tool definitions from the call (~6K tokens)
- Eliminates multi-turn snapshot accumulation
- 1 LLM call instead of 3–4

If single-shot fails (parse error, no tool call, exception), the code falls through to the full tool loop with messages already populated by bootstrap.

#### 5. Configurable turn budget + verdict extraction on timeout (`agent.py`)

`QA_MAX_TURNS` (default 12 for Anthropic, 25 for Ollama) caps the tool loop. When the budget is exhausted, `_extract_verdict` is called on the conversation history before hard-failing — producing a real `actual`/`reasoning` verdict instead of `"Turn budget exhausted"`.

In the second measured run, 5 scenarios consumed 25 turns each, accounting for ~50% of total token spend. With `max_turns=12` those scenarios are bounded to ≤48% of that budget.

#### Cost trajectory (alconind.ro)

| Configuration | Scenarios | Cost (Haiku) | Pass rate |
|---|---|---|---|
| No caching, no pruning, no depth limit (baseline) | 42 | ~$10 (extrapolated) | n/a |
| + Prompt caching only | 36 | ~$3 (measured) | 19/36 (53%) |
| + Pruning + depth + bootstrap + single-shot (buggy) | 33 | $2.40 (measured) | 14/33 (42%) ⚠ |
| + Bug fixes (forced-tool single-shot, message injection) | 33 | ~$1.50 (estimated) | TBD |

The third row reflects a buggy intermediate where Anthropic bootstrap didn't populate `messages` and `response_format=json_object` failed silently — costs dropped but pass rate regressed. Both bugs were fixed by extracting `_bootstrap()` (shared with Ollama) and switching single-shot to forced `report_result` tool calls.

---

### Ollama specifics

Ollama runs are configured differently from remote API calls:

- **Bootstrap:** pre-executes `browser_navigate` + `browser_snapshot` before the first LLM call. Injects both as completed turns. The URL used is extracted from the Given clause if a path is specified (e.g. `"la URL-ul /produse"` → navigates to `/produse` not root).
- **Slim tools:** Ollama defaults to 8 essential tools instead of 21 — prevents hallucination on small models overwhelmed by large tool definitions.
- **Context window:** `num_ctx=8192` passed on every request via `extra_body.options`. Ollama's own default (4096) is insufficient for browser snapshot + system prompt + tool definitions.
- **Auto-start:** `ensure_provider_running()` starts `ollama serve` automatically if not reachable.

### Timeout layers

Two independent layers prevent unbounded waits. See `docs/timeout-strategy.md` for full detail.

| Layer | Default | Override |
|-------|---------|---------|
| Per-call LLM timeout | 30s (Anthropic), 60–300s (Ollama model-dependent) | `QA_LLM_TIMEOUT` |
| Per-test soft timeout | None (Anthropic), 180–600s (Ollama) | `QA_TEST_TIMEOUT` |
| Rate-limit retry wait | 60s → 120s | `QA_RATE_LIMIT_WAIT`, `QA_RATE_LIMIT_RETRIES` |

---

## Browser Automation

Playwright MCP (`@playwright/mcp`) runs as a subprocess, spawned fresh per test scenario (`--isolated` flag). The executor communicates with it via the MCP protocol (JSON-RPC over stdio). The agent uses the **accessibility tree** (not screenshots) — cheaper, deterministic, no vision model required.

**Slim tool set (8 tools, default for Ollama):**
`browser_navigate`, `browser_snapshot`, `browser_click`, `browser_type`, `browser_fill_form`, `browser_press_key`, `browser_wait_for`, `browser_select_option`

**Full tool set (23 tools, default for Anthropic/Together.ai):** includes `browser_scroll`, `browser_hover`, `browser_drag`, `browser_select_option`, `browser_evaluate`, and others. Anthropic handles the larger context without hallucination; small models do not.

**Preflight check:** before running any scenarios, verifies npx is available, MCP starts correctly, all essential tools are present, and the browser can actually navigate (`browser_navigate("https://playwright.dev")`).

#### Browserbase Cloud Browser (Phase 1 — optional)

Browserbase provides a cloud alternative to local Playwright. When configured via `QA_BROWSERBASE_API_KEY` and `QA_BROWSERBASE_PROJECT_ID` env vars, qa-agent creates a remote browser session and connects Playwright MCP via CDP endpoint instead of launching a local headless browser.

**Session lifecycle:**
- Before scenario: `browserbase.create_session()` → POST to Browserbase API, get `(session_id, cdp_url)`
- `_make_server_params(cdp_endpoint)` routes @playwright/mcp to `--cdp-endpoint=<wss://...>` instead of `--headless --isolated`
- After scenario: `browserbase.delete_session(session_id)` → best-effort DELETE (swallows errors so test results never lost)

**Configuration:**
```
QA_BROWSERBASE_API_KEY       — required; Browserbase API key
QA_BROWSERBASE_PROJECT_ID    — required; Browserbase project ID
QA_BROWSERBASE_REGION        — default: us-east-1
QA_BROWSERBASE_TIMEOUT       — session timeout in seconds, default 300
```

**Telemetry:**
Each scenario result includes:
- `browser`: "browserbase" (if CDP endpoint used) or "local"
- `bb_session_duration_s`: browser-only time in seconds (for cost metering: $0.50/run estimate assumes 10 min/run average)

**Use case:**
Cloud deployments where local browser management is infeasible. The roadmap (D6) treats Browserbase as the primary Phase 1 test; if cost or latency is unacceptable, fall back to self-hosted Playwright on Modal/Fly.io.

---

## Known Limitations — Free Tiers (Fly.io + Browserbase)

Empirically validated 2026-05-13. Applies to the current MVP deployment (`qa-agent-sp` on Fly.io hobby plan + Browserbase free tier).

### Fly.io (hobby / shared-cpu-1x, 2GB)

| Limitation | Detail | Trigger / Workaround |
|---|---|---|
| **OOM under concurrent load** | uvicorn (~250MB) + asyncio BackgroundTask (~200MB) + npx Node.js process (~200MB) = ~650MB under active run. 512MB and 1GB both OOM'd in testing. | Fixed at 2GB (`fly.toml`). If OOM recurs: separate worker process (Step 5). |
| **BackgroundTasks killed on restart** | Fly restarts the machine on deploy or health-check failure. All in-flight `asyncio.BackgroundTask` runs are killed; they appear as "Interrupted by server restart" in status. | `min_machines_running=1` prevents auto-stop. Proper fix: job queue (Step 5). |
| **Specs lost on redeploy** | Specs written to container filesystem (e.g. `specs/emag/`) are wiped on each deploy. Only `/app/reports/` is on the persistent volume. | Always use `-o reports/specs/<name>` in `qa-agent analyze`, and `spec_dir: "reports/specs/<name>"` in API calls. |
| **Single machine = no horizontal scale** | Volume is mounted on one machine only. A second instance would have a separate volume and split in-memory `_runs` dict. | Acceptable for MVP. Fix: Postgres + R2 (Step 5). |
| **Region latency** | Machine in `iad` (US East); Browserbase auto-assigns sessions (observed: `us-west-2`). Cross-region WebSocket adds ~30–80ms per browser tool call. | Acceptable for correctness testing. Optimise after launch. |

### Browserbase (free tier)

| Limitation | Detail | Trigger / Workaround |
|---|---|---|
| **Rate-based anti-bot detection** | Sites with Cloudflare or similar protection block requests after 6–7 consecutive Browserbase sessions in a short window. Observed on emag.ro (first 6 sessions succeed, subsequent ones receive human-verification challenge). | `QA_SCENARIO_DELAY=3` (default in API) adds 3s between sessions. Proper fix: Browserbase Stealth Mode (paid tier) — see `docs/roadmap.md` deferred items. |
| **Session region auto-assigned** | Free tier assigns sessions to any available region (observed: `us-west-2` even when not requested). `connectUrl` in API response is the authoritative endpoint; constructing the URL manually fails. | Always use `data["connectUrl"]` from the session creation response (implemented in `browserbase.py`). |
| **No stealth mode** | Free tier does not support `proxies: true` or fingerprint randomization. Aggressive anti-bot systems detect cloud browser fingerprint even with delays. | Document limitation to users in UI. Upgrade to paid Stealth Mode when first user reports consistent blocks. |
| **Session cost unvalidated** | $0.50/run estimate in cost model is untested. Actual cost depends on session duration and Browserbase plan. | Measure once first paid plan is activated. |
| **Session timeout** | Default 300s. Long analyst runs or slow sites may exhaust the timeout mid-crawl. | Configurable via `QA_BROWSERBASE_TIMEOUT`. Analyst on a 1-page scope completes in <60s typically. |

### Summary — what works reliably on free tiers

- Analyst on standard marketing pages (no aggressive anti-bot): ✓
- Executor with `max_scenarios ≤ 5` and `QA_SCENARIO_DELAY=3`: ✓ on most sites
- HTTP API + polling pattern: ✓
- Persistent reports and specs (when stored under `reports/`): ✓
- Sites with Cloudflare Enterprise or strict bot protection: ⚠ unreliable beyond 6 sessions

---

## Spec Format

Dual format support:

**Gherkin (`.feature`):** behavioural end-to-end scenarios. LLM interprets steps as free text — no step definition bindings. Requirements carry stable IDs in tags: `@id:AC-001`. The state store keys off these IDs.

**YAML (`config.yaml`):** product configuration — target URL, environments, product context string injected into the executor system prompt.

---

## HTTP API (Phase 1 — cloud-readiness)

The CLI is wrapped in a FastAPI server for cloud deployment. Runs are executed as asyncio background tasks, allowing clients to trigger and poll asynchronously.

**Starting the server:**
```bash
uv run qa-agent serve [--host 0.0.0.0] [--port 8000] [--reload]
```

**Endpoints:**

| Method | Path | Status | Purpose |
|---|---|---|---|
| POST | `/runs` | 202 Accepted | Create a run; returns run_id immediately; execution happens in background |
| GET | `/runs` | 200 | List all runs (in-memory + disk) |
| GET | `/runs/{run_id}` | 200 / 404 | Poll run status |
| POST | `/runs/{run_id}/cancel` | 202 / 409 | Cancel a pending/running run (409 if already terminal) |
| GET | `/runs/{run_id}/report` | 200 / 404 | Return report.json for a completed run |
| GET | `/health` | 200 | Liveness probe |

**Request body for `POST /runs`:**
```json
{
  "spec_dir": "specs/alconind",
  "env": null,
  "output": "reports",
  "only_failing": false,
  "executor_provider": null,
  "executor_model": null
}
```

**Response body (all endpoints return `RunStatus`):**
```json
{
  "run_id": "2026-05-13T08-41-28Z",
  "status": "pending|running|done|failed|cancelled",
  "spec_dir": "specs/alconind",
  "started_at": "2026-05-13T08:41:28.552111+00:00",
  "completed_at": null,
  "summary": {"total": 73, "passed": 52, "failed": 21, "errored": 0},
  "report_path": "reports/run-2026-05-13T08-41-28Z/report.json",
  "error": null
}
```

**Execution model:**

Runs execute as independent asyncio tasks in the background. The server responds to requests immediately (`202 Accepted` for POST /runs, `200` for GET /runs/{run_id}). Clients poll `GET /runs/{run_id}` to track progress until status becomes `done`, `failed`, or `cancelled`.

Status is persisted to `run_dir/run_status.json` so it survives server restarts. On server startup, any runs left in `running` or `pending` state are marked as `failed` with error "Interrupted by server restart" — preventing stale status from previous sessions.

**Cancellation:**

`POST /runs/{run_id}/cancel` requests the cancellation of a background task. The task stops at the next `await` point (typically between scenarios). Returns `409 Conflict` if the run is already in a terminal state (`done`, `failed`, `cancelled`) or if the task has no live asyncio reference (orphaned from a previous server session).

---

## Authentication

qa-agent is multi-tenant. Every product, spec, and job belongs to exactly one user, and the API enforces ownership on every request. Authentication is built on **Supabase Auth**; the design is structured to keep vendor lock-in bounded so the auth provider can be swapped (Clerk, Auth0, custom) in 1–2 days if needed.

### Identity model

| Layer | Owner | Purpose |
|---|---|---|
| `auth.users` (Supabase-managed schema) | Supabase | Source of truth for credentials, password hashes, OAuth provider links, session tokens. Not referenced directly from business tables. |
| `public.users` (our schema) | qa-agent | Mirror keyed by the same UUID. All business-table foreign keys (`products.user_id`, `jobs.user_id`) reference this table. |
| Sync trigger `on_auth_user_created` | Postgres trigger | When Supabase inserts into `auth.users`, the trigger inserts a matching row into `public.users` (`id`, `email`, `created_at`). |

**Why the mirror exists (D1 = Option B):** business tables never depend on `auth.users` directly. If we migrate away from Supabase Auth, `public.users` stays intact — only the sync trigger and the JWT verification middleware need to change. Without the mirror, every business FK would point at a Supabase-specific table and a migration would require schema-level rewrites.

### JWT verification (D2 = local)

The frontend obtains a Supabase session and sends `Authorization: Bearer <access_token>` on every request. The FastAPI middleware decodes the JWT **locally** using the Supabase project's JWT secret (HS256), no network call to Supabase per request.

```
SUPABASE_JWT_SECRET   — project JWT secret (HS256). Set as Fly secret.
SUPABASE_URL          — used only by frontend SDK; backend doesn't need it.
```

The middleware extracts `sub` (user UUID) and `email` from the JWT claims and exposes them as `current_user` via `Depends(get_current_user)`. Tokens are verified for signature, expiry, and audience (`authenticated`).

**Why local:** ~50–100ms saved per request vs. calling `/auth/v1/user`. The trade-off — a revoked session remains valid until the access token expires (default 1h) — is acceptable for an MVP.

### Multi-tenancy enforcement (D3 = both layers)

Two independent layers, applied together:

1. **Application-level filters** in `db/products.py`, `db/specs.py`, `db/jobs.py`. Every CRUD function takes `user_id` and includes it in `WHERE` clauses. First line of defense, easy to read and debug.
2. **Row Level Security (RLS) in Postgres** on `products`, `specs`, `jobs`. Policies key off `auth.uid()` (Supabase's helper that reads the JWT claim from the connection). Defense-in-depth — even if the application accidentally omits a filter, RLS blocks cross-tenant reads/writes.

Example policy:
```sql
ALTER TABLE products ENABLE ROW LEVEL SECURITY;
CREATE POLICY "users_own_products" ON products
  FOR ALL USING (user_id = auth.uid());
```

`auth.uid()` is the only Supabase-specific surface inside our SQL. On migration, it is replaced with `current_setting('app.user_id')::uuid` populated by the new auth middleware.

### CLI and local development

The CLI bypasses JWT verification by connecting to Postgres with the **service-role key** (`DATABASE_URL` configured for service role). Service-role connections automatically bypass RLS. This keeps the CLI usable for local dev and ops without requiring login flows.

Never use the service-role key from the FastAPI server in production — the server connects with a constrained role and relies on RLS for isolation.

### Vendor lock-in summary

| Component | Lock-in | Migration cost |
|---|---|---|
| Postgres database | None | `pg_dump` → restore anywhere. |
| `public.users` mirror | None | Owned by us; survives provider change. |
| JWT middleware | Low | Swap the verification function (one file). |
| RLS policies | Low | Replace `auth.uid()` with `current_setting('app.user_id')`. |
| OAuth providers | Low | Re-register apps with the new provider; users re-login. |
| Email flows (verify, reset, magic link) | Low | Config change to Resend/Postmark/SES. |
| `auth.users` + sessions | Medium | Real migration cost. Mitigated by user-import APIs on Clerk/Auth0 and the mirror pattern above. |

**Targeted migration to Clerk or Auth0:** estimated 1–2 days. **Targeted migration to fully self-hosted auth:** 1–2 weeks (rewrite signup/login/reset, password hashing, email sender).

### Open features not covered

| Feature | Status |
|---|---|
| SAML SSO | Supabase Pro tier; deferred to Phase 5 |
| SCIM provisioning | Supabase Enterprise tier; Phase 5 |
| TOTP 2FA | Built into Supabase Auth; enable in dashboard if needed |
| Audit log of credential access | Phase 4 (deferred) |
| BYOK per tenant for LLM keys | Phase 4 (deferred) |

---

## Output Contract

Per-run artifacts under `reports/run-<ISO-timestamp>/`:

| File | Contents |
|------|---------|
| `report.json` | `{summary, results[], run_id}` — stable schema for downstream agents |
| `report.md` | Human-readable Markdown report generated from Python template (no LLM) |
| `telemetry.json` | Token counts, cost, latency, cache hit rate |
| `evidence/` | Screenshots, DOM snapshots (future) |

The state store at `reports/.state/` tracks the last status per `requirement_id` across runs — powers `--only-failing` to re-run only regressions.
