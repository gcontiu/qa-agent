# qa-agent — SaaS Roadmap

Strategic plan for transitioning qa-agent from a local CLI tool to a hosted SaaS where users authenticate, configure their products (including auth), and run automated test suites. Captures phased deliverables, open decisions, cost projections, and risk register.

> **Status:** CLI mature; SaaS Phase 0.5 complete (cost optimization + analyst quality validated on alconind.ro v2); public-sites-only MVP web app is next.
>
> **Last updated:** 2026-05-11

---

## Executive summary

The end goal is a multi-tenant SaaS at `qa-agent.io` (or similar) where:

1. Users sign up, add their product (URL + description; **auth deferred to Phase 3**)
2. Analyst auto-generates Gherkin specs by crawling the public site (evidence-only, no invented features)
3. Users edit/approve specs, then run tests on demand or on schedule
4. Reports are stored, viewable, and consumable by downstream agents (fix-agent)

The biggest design pressures are:

- **Cost** — measured $0.78/run on a 73-scenario suite with optimizations; needs scenario caps + tier-aware pricing
- **Reliability** — verdicts must be consistent; Anthropic remains the gold standard, with single-shot guardrails for Then-only scenarios
- **Analyst quality** — must produce specs that reflect the site, not idealised features; validated on one site, generalization still unconfirmed
- **Security** — handling user credentials at scale is a serious responsibility, deferred to Phase 3 after MVP validates demand

The key strategic insight: **don't self-host LLMs**. Inference APIs (Anthropic; Together.ai as opt-in) host the same open-weight models we use locally, at API prices competitive with self-hosted GPUs for our volume. Self-hosted GPUs only make sense at >3000 runs/month or for on-prem enterprise deployments.

---

## Current state (CLI)

### What works today

- Provider-agnostic via LiteLLM: Anthropic (default), Together.ai (opt-in), Ollama (local dev)
- Three roles implemented: Analyst, Executor, Reporter, Extractor (verdict fallback)
- Playwright MCP for browser automation
- Spec format: Gherkin `.feature` files + `config.yaml`
- **Cost optimization stack (Phase 0.5, all measured)**:
  - Anthropic prompt caching (system + tools cached at 0.1× input rate after first turn)
  - Stale snapshot pruning (only latest snapshot kept in context)
  - Bounded snapshot depth (`QA_SNAPSHOT_DEPTH=5` default)
  - Shared bootstrap helper (Ollama + Anthropic both pre-navigate)
  - Single-shot for Then-only scenarios (forced `report_result` via `tool_choice=required`)
  - `QA_MAX_TURNS=12` for Anthropic + verdict extraction on timeout
- **Analyst quality** — evidence-only prompt prevents inventing features (table of common failure modes embedded); writes feature files to disk per-call (no data loss on timeout)
- **Telemetry** — per-scenario and per-run token capture (`input/output/cache_write/cache_read/cost_usd`) in `telemetry.json`
- Local development on macOS (M4 Pro)

### Empirical limits

- **Anthropic Haiku 4.5 on alconind.ro v2 (73 scenarios, 2026-05-11):** $0.78/run, 71% pass rate (52/73), 46% cache hit rate, single-shot used on ~25 of 73 scenarios
- **Anthropic Opus 4.7 analyst on alconind.ro:** $1.40 to generate canonical specs (13 files, 73 scenarios) — one-time per site
- **Anthropic Sonnet 4.6:** ~$2/run estimated, 100% reliable (not measured on v2 yet, only old 42-scenario suite)
- **Local Ollama:** mistral-small:22b stable on simple sites; qwen2.5:14b fails on dense pages (reasoning saturation)
- **Pipeline generalization:** validated on a single site (alconind.ro). Not yet confirmed on a 2nd site.
- **No auth support yet** — only public/marketing pages can be tested

---

## Strategic phases

### Phase 0.5 — Cost validation & analyst quality (DONE, 2026-05-04..11)

**Goal:** Bring cost per run down from baseline ~$10 to a sustainable level; ensure analyst produces specs grounded in observed site content.

| Task | Status |
|------|--------|
| Together.ai provider integration in `router.py` | ✓ Done (BD-001) |
| Anthropic prompt caching (`_apply_anthropic_cache_control`) | ✓ Done |
| Stale snapshot pruning (`_prune_stale_snapshots`) | ✓ Done |
| Bounded snapshot depth (`QA_SNAPSHOT_DEPTH`) | ✓ Done |
| Shared bootstrap helper (Ollama + Anthropic) | ✓ Done |
| Single-shot for Then-only (forced `report_result`) | ✓ Done |
| Configurable turn budget + verdict extraction on timeout | ✓ Done |
| Real token telemetry + cost calculation | ✓ Done |
| Analyst evidence-only prompt | ✓ Done |
| Analyst write-on-each-call (no data loss on timeout) | ✓ Done |
| Validation on alconind.ro v2 | ✓ Done (71% pass, $0.78) |
| Validation on a 2nd site | ⚠ Pending — Phase 1 prereq |

**Result:** $10 → $0.78 per 73-scenario run (~92% reduction). Analyst confirmed evidence-based on alconind.ro.

### Phase 1 — Cloud-readiness (1–2 weeks)

**Goal:** Prove qa-agent runs on cloud infrastructure with hosted LLM and browser providers, not just locally.

| Task | Deliverable |
|------|-------------|
| **Validate pipeline on a 2nd site** | Spec generation + run on a different domain (SPA, English, or auth-light). Confirms analyst generalizes; budgeted ~$5. |
| Test Browserbase as drop-in for `npx @playwright/mcp` | Verify session persistence works; latency acceptable; cost meter |
| Wrap CLI in FastAPI endpoint (`POST /api/runs`) | Single endpoint that accepts spec_dir + config, returns run_id |
| Containerize qa-agent (Docker image) | Multi-stage Dockerfile; runs in any cloud |

**Success criteria:** A run can be triggered via HTTP from any cloud machine, using cloud LLM + cloud browser, no local dependencies. Pipeline confirmed on a second site (alconind generalization).

### Phase 2 — MVP web app (public sites only, 3–4 weeks)

**Goal:** Public-facing web app where users sign up, add a public product URL, and run tests. **No app auth in MVP** — only public marketing sites. Auth is Phase 3.

| Task | Deliverable |
|------|-------------|
| Frontend Next.js scaffold (Vercel) | Landing page + dashboard layout |
| User auth: Clerk or Supabase Auth | Email/password + Google OAuth for users (not for target products) |
| "Add product" flow | URL + description; analyst runs in background |
| Spec viewer/editor (Monaco or CodeMirror) | View analyst-generated specs, edit Gherkin inline, approve before run. **UI must surface limitations:** (1) anti-bot blocks — show warning when analyst couldn't access the page ("Site-ul blochează crawling-ul automat; activează Stealth Mode sau verifică manual specs-urile"); (2) scenario cap — show how many scenarios were capped vs total discovered; (3) Browserbase session cost per run. |
| Run trigger + status page | Trigger run, show live progress, display report when done |
| Cost meter in UI | Display per-run cost from `telemetry.json`; show scenario cap usage |
| Job queue (Inngest or Trigger.dev) | Async run execution; users don't wait for HTTP response |
| Stripe billing | Subscription tiers + per-run overage |
| Postgres schema (Supabase) | users, products, specs, runs, reports |

**Success criteria:** A new user can sign up, add a public product URL, review analyst-generated specs, run tests, view a report — all via the web UI. Cost transparent to user.

#### Phase 2 — MVP implementation order

Strict order. Each step gates the next; do not parallelize without reason.

| # | Step | Why this step, why now |
|---|------|------------------------|
| 1 | **Validate pipeline on a 2nd site** (Phase 1 prereq) | Hard gate. If analyst/executor don't generalize, the rest is wasted work. ~$5, ~1 day. |
| 2 | **Hardcoded scenario cap per request** (env `QA_MAX_SCENARIOS`) | Single biggest cost-blowup vector. Must land before any public access. Tiered caps come later. |
| 3 | **Dockerfile + Fly.io deploy** of existing FastAPI (single process) | Prove cloud deploy works with current code. No queue yet — `BackgroundTasks` is enough at zero traffic. |
| 4 | **Browserbase wired as default** (`QA_BROWSER=browserbase`) | Remove local Chromium dependency from server. Phase 1 task pulled forward. |
| 5 | **Postgres schema** (`users`, `products`, `jobs`, `specs`, `reports`) via Supabase | Multi-tenancy foundation. `jobs` replaces in-memory `_runs` dict in `api.py`. |
| 6 | **Own-auth: Clerk or Supabase Auth** + FastAPI JWT middleware | Users sign up to the SaaS. *Not* auth into the products being tested — that is Phase 3. |
| 7 | **Per-user rate limit** (slowapi, ~20 LOC) | Prevents single-user cost runaway on day 1 of public access. |
| 8 | **Next.js scaffold on Vercel**: login → new job → spec review → report | Three pages, shadcn/ui defaults. No design polish yet. |
| 9 | **Spec viewer/editor (Monaco)** with explicit "Approve & Run" step | Mandatory human-in-the-loop between analyst and executor. Without it, analyst hallucinations create false-fail reports and erode trust. |
| 10 | **Cost meter component** reading `telemetry.json` / `cost_usd` | Surfaces existing data. Decisive for user trust and perceived value. |
| 11 | **Live run status page** (poll `GET /runs/{id}`) + final report view | Wraps existing endpoints; no new backend work. |

**Stop here for closed beta.** Onboard 5–10 hand-picked users. Validate demand. Stripe + tiered scenario caps come *after* this stage answers "do people want this?".

#### Phase 2 — Deferred from MVP

Each item is deferred against a specific trigger. When the trigger fires, move it into the active scope; not before.

| Deferred item | Trigger to reactivate |
|---------------|----------------------|
| **Redis queue (Upstash, `arq`/`rq`)** | >5 concurrent jobs observed, or `BackgroundTasks` lose runs on deploy/restart in production |
| **Separate worker machine** (Fly process group) | Web requests start timing out due to worker CPU; or worker crashes take down API |
| **R2/S3 for report storage** | Average `report.json` + evidence > 1 MB, or users request public report sharing links |
| **Stripe billing + tiered plans** | Closed beta validates retention ≥ 30% week-2; until then, manual invoicing for paid users |
| **Tiered scenario caps (Free/Starter/Pro)** | Stripe is live; before that, single hardcoded global cap |
| **BYOK (user's Anthropic key)** | First paying user explicitly asks, or LLM cost > 50% of revenue |
| **Auth into *target products*** (form login, OAuth, 2FA, KMS vault — Phase 3) | ≥ 30% of beta users request testing of authenticated pages; or first paying customer makes it a deal-breaker |
| **Retry logic + flaky-test badging** (Phase 4) | False-fail rate in production > 5%, measured over ≥ 100 runs |
| **Browserbase Stealth Mode** (`proxies: true` + fingerprint) | First user reports consistent anti-bot blocks (Cloudflare, reCAPTCHA) preventing analyst/executor from accessing their site; or >10% of runs fail due to challenges. Current mitigation: `QA_SCENARIO_DELAY=3` between sessions reduces rate-based detection. |
| **Self-hosted Playwright on Modal** | Browserbase spend > $1k/month |
| **Multi-region deploy (EU)** | First EU customer with data residency requirement, or > 20% of users from EU |
| **SAML SSO / SCIM / SOC2** (Phase 5) | First enterprise prospect blocks deal on it; until then, $0 spent |
| **UI polish: dark mode, mobile, animations** | Beta feedback explicitly cites UI as a blocker (not vague "looks rough") |
| **Spec versioning & migration tooling** | First breaking change to Gherkin schema with existing user specs in production |
| **`fix-agent` integration / downstream consumers** | qa-agent itself is stable and 2+ users have asked for it |

**Discipline rule:** if a deferred item is being discussed but its trigger has not fired, the answer is "not yet" — not "let's add it just in case". Premature scope is the failure mode for this kind of product.

### Phase 3 — Auth foundation + extensions (4 weeks, after MVP validates demand)

**Goal:** Support testing of authenticated apps. Without this, the tool can only test public marketing pages. Triggered when first MVP users request it.

| Task | Coverage |
|------|----------|
| Extend `config.yaml` schema with `auth:` block | Form-based + API key types |
| Implement form-based login flow (helper in `agent.py`) | Pre-test login using credentials from `auth.credentials_ref` |
| Session persistence across scenarios | Save `storage_state.json` after login |
| Encrypted credential storage (envelope encryption with KMS) | Postgres column with KMS-encrypted blobs |
| Pre-auth health check | Verify login works before running full suite |
| Magic link auth (email integration via Resend/Postmark) | ~15% of products |
| OAuth providers: Google, GitHub, Microsoft | ~25% of products |
| 2FA TOTP support (shared secret in vault) | ~30% of products (overlap) |

**Success criteria:** ~80% of B2B SaaS products can be tested without manual workarounds.

### Phase 4 — Hardening (2 weeks)

**Goal:** Production-quality reliability and security.

| Task | Why |
|------|-----|
| Rate limiting per user/tenant | Prevent abuse, cap LLM spend |
| Retry logic for transient failures | LLM timeouts, browser flakiness |
| BYOK (Bring Your Own Key) for Anthropic / Together | Removes our LLM cost for power users |
| Audit log for credential access | Security/compliance requirement |
| Session expiry handling + re-auth | Long-running runs that outlive auth session |
| Pen test ($5–10K) | Pre-launch security validation |
| Update analyst prompt based on production feedback | Spec quality drifts as sites evolve |

### Phase 5 — Enterprise (4+ weeks, after first paying customers)

| Task | Why |
|------|-----|
| SAML SSO + SCIM provisioning | Enterprise procurement requirement |
| Dedicated vault (HashiCorp Vault or AWS Secrets Manager) | Stronger credential isolation per tenant |
| On-prem deployment option (Docker Compose) | For customers who can't send credentials to cloud |
| SOC2 Type 1 audit ($15–25K, 6 months) | Required for mid-market and enterprise sales |
| Custom SLA + dedicated support | Enterprise tier offering |

---

## Multi-provider LLM strategy

### Recommended tier mapping (post-2026-05-11 validation)

| Tier | LLM Provider | Model | Cost/run | Margin at price |
|------|--------------|-------|----------|-----------------|
| Free (3 runs/mo, max 25 scenarios) | Anthropic | Haiku 4.5 | ~$0.30 | -$0.90/user (acquisition) |
| Starter ($49/mo, 25 runs, 30 scenarios cap) | Anthropic | Haiku 4.5 | ~$0.30/run → ~$7.50 | $41/user (~84% gross) |
| Pro ($99/mo, 100 runs, 75 scenarios cap) | Anthropic | Haiku 4.5 | ~$0.78/run → ~$78 | $21/user (~21% gross) |
| Enterprise (custom) | Anthropic | Sonnet 4.6 | ~$2/run | negotiated |
| BYOK (any tier) | User's API key | Any | $0 LLM cost | platform fee only |

**Rationale:**
- **Haiku is now the default executor** for all tiers (BD-001). Reliability matches Sonnet on optimized pipeline; cost is 4× lower.
- **Anthropic-only by default** simplifies operations. Together.ai available as opt-in escape hatch.
- **Scenario caps per tier** are critical — analyst quality improvements push scenario counts up (42 → 73 typical). Without caps, Pro tier margin erodes.
- **Pro tier margin is thin (~21%)** at $99/100 runs. Margin improves with sustained cross-scenario caching. **Sensitivity analysis pending** — re-test with scenario cap=30 to confirm cost scales linearly.

### Together.ai as alternative provider (opt-in)

- Available via `QA_EXECUTOR_PROVIDER=together_ai`
- `meta-llama/Llama-3.3-70B-Instruct-Turbo`: estimated ~$0.50/run, 100% tool call format, no chain-of-thought self-recovery
- Use cases: BYOK users wanting cheaper inference; hedge against Anthropic pricing changes
- Not recommended as default; documented as escape hatch
- LiteLLM abstraction enables switching within hours if needed

### Verdict architecture (D2 — Closed 2026-05-06)

**Hybrid implementation in production:**
- **Then-only scenarios** (~70% of typical suite): single-shot LLM call with only `report_result` available and `tool_choice="required"`. Tool's enum schema (`["pass", "fail"]`) guarantees structured output. No multi-turn snapshot accumulation.
- **When-action scenarios:** full tool loop. When-action guardrail blocks `status=pass` if required action verbs weren't executed.
- **Both flows share `_bootstrap()` helper** for first-turn navigation+snapshot.
- **Verdict extraction fallback:** if executor exhausts turn budget without `report_result`, a pruned-history LLM call extracts a verdict before hard-failing.

This combines benefits of Level 1 (forced retry on Anthropic) and Level 2 (two-phase with structured output) from the original analysis.

### Determinism

All LLM calls use `temperature=0` by default, making runs reproducible. Exception: `claude-opus-4-7` (Anthropic deprecated temperature for this model). Override: `QA_TEMPERATURE=0.7` for stochastic behaviour, `QA_SEED=123` for a different seed (Ollama only).

---

## Cost model

### Per-run cost breakdown (cloud, measured 2026-05-11)

```
Anthropic Haiku 4.5 (executor):     $0.78  (measured on 73-scenario alconind v2)
Browserbase (10 min/run avg):         $0.50  (UNTESTED — estimate)
Compute orchestration (Modal/Fly):    $0.05
Database, storage, CDN:               $0.02
─────────────────────────────────────────────
Total marginal cost per run:         ~$1.35  (with Browserbase)
                                     ~$0.85  (with self-hosted Playwright)
```

### Pricing model (post-2026-05-11 revision)

| Tier | Price | Runs/month | Scenarios cap | Cost to us | Gross margin |
|------|-------|------------|---------------|-----------|--------------|
| Free | $0 | 3 | 25 | ~$1 | -$1/user (acquisition cost) |
| Starter | $49/mo | 25 | 30 | ~$10 | $39/user (~80% gross) |
| Pro | $99/mo | 100 | 75 | ~$80 | $19/user (~20% gross, with Browserbase) |
| Enterprise | $499+/mo | unlimited (reasonable use) | unlimited | varies | 60–70% gross |
| BYOK | $9/run flat fee | n/a | unlimited | $0.55 (compute+browser) | $8.45/run (~94% gross) |

**Note:** Pro tier is thinner than originally planned. Drivers:
- Scenario count grew (42 → 73 typical) as analyst quality improved
- Per-scenario cost still ~$0.01–0.02 (Haiku, with caching)

**Sensitivity analysis pending:** re-test at scenario-cap=30 (Free baseline) to confirm per-run cost ~$0.30 holds. If actual cost scales sub-linearly (cache hits across scenarios), margins improve materially.

### Break-even analysis

Self-hosted GPU only makes sense beyond ~3,000 runs/month, which corresponds to ~30 Pro users running 100 runs/month each. Until then, inference APIs (Anthropic + Together.ai) are cheaper.

---

## Open decisions

These need to be made before / during the next phases. Each comes with a default recommendation but should be confirmed by the user.

| # | Decision | Status | Resolution |
|---|----------|--------|------------|
| **D1** | Primary LLM provider | **Closed 2026-05-04** (BD-001) | Anthropic default + Together.ai opt-in/BYOK |
| **D2** | Verdict architecture | **Closed 2026-05-06** | Hybrid: single-shot for Then-only + full loop for When-action |
| **D3** | Credential vault | Postponed — Phase 3 | Postgres + KMS at MVP, migrate to HashiCorp Vault at enterprise |
| **D4** | Auth tier scope | Postponed — Phase 3 | Free = public only, paid = auth |
| **D5** | Worker model | Open | Both (platform-managed + BYO worker for self-host) |
| **D6** | Browser provider | Open — Phase 1 | Browserbase test pending; fallback self-hosted Playwright on Modal |
| **D7** | Hosting platform | Open | Vercel + Railway recommended for early stage |
| **D8** | Compliance roadmap | Open | Defer SOC2 until enterprise demand |
| **D9** | Geographic regions | Open | US first, EU within 12 months |
| **D10** | OAuth at MVP | **Postponed — Phase 3** | Form + API key only at Phase 3 launch |
| **D11** | Pricing model | Open | Subscription + overage |
| **D12** | Free tier policy on auth | Open | No auth on free (mitigates security risk) |
| **D13** | Scenario cap policy | **Open — Phase 2 prereq** | Hard cap per tier at MVP; predictable cost; clear UX |

---

## Risk register

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Credential breach (stored user passwords leaked) | Low | Catastrophic | KMS encryption, rotation, audit logs, pen test, cyber insurance (Phase 3+) |
| LLM provider price changes (Anthropic raises rates 2×) | Medium | High | Multi-provider via LiteLLM; can switch to Together.ai within hours |
| Together.ai or similar shutters | Low | Medium | Multiple open-model providers; LiteLLM abstracts |
| Anti-bot detection blocks our crawls (Cloudflare, reCAPTCHA) | Medium | Medium | Browserbase has stealth mode; offer BYO worker for bypass |
| 2FA-required products can't be tested | High | Medium | Phase 3+ TOTP support; document workarounds |
| Scaling browser worker pool gets expensive | Medium | Medium | Self-host Playwright on Modal at >$1k/mo Browserbase spend |
| Customer credential rotation breaks runs silently | High | Low | Health check before each run; email alerts on auth failure |
| Spec format changes break existing user specs | Medium | High | Versioned spec schema with migration path |
| Free tier abuse (users running thousands of free runs) | High | Medium | Strict rate limit + IP-based throttling on free tier + scenario cap |
| Browser automation flakiness causes false fails | High | Medium | Retry transient failures; show "flaky" badge in UI |
| LLM hallucinates verdict (says PASS when actually FAIL) | Low (Anthropic), Medium (open) | High | Sample audit; use Sonnet+ on enterprise tier; track historical accuracy |
| **Analyst invents features not on the site** | ~~High~~ Mitigated (2026-05-06) | Medium | Evidence-only prompt with explicit "do not invent" rules + failure mode table |
| **Spec strictness drift (overly literal Then assertions)** | High | Medium | Tune analyst prompt to prefer "contains X" over exact strings; spec linter (future) |
| **Per-scenario LLM timeout on dense snapshots** | Medium | Low | Per-model timeout overrides (`QA_LLM_TIMEOUT`); depth cap |
| **Cost growth as analyst quality improves (more scenarios)** | High | Medium | Hard scenario caps per tier; cost meter visible in UI |
| **Pipeline doesn't generalize beyond alconind.ro** | Unknown | High | "Validate on 2nd site" task in Phase 1 prerequisites |

---

## Implications for existing code

The current architecture is largely SaaS-ready. Specific changes needed by phase:

### Phase 1 (cloud-readiness)
- `src/qa_agent/llm/router.py` — Together.ai entry already added (BD-001). No further changes needed.
- `src/qa_agent/agent.py` — `_make_server_params()` already configurable via `QA_BROWSER`; extend to support remote MCP endpoints (`QA_MCP_ENDPOINT` env var) for Browserbase
- New file: `src/qa_agent/api.py` — FastAPI wrapper exposing `POST /runs`, `GET /runs/{id}`, etc.
- New file: `Dockerfile` — multi-stage build, copy specs, install Playwright, run as non-root
- `pyproject.toml` — add `fastapi`, `uvicorn` to deps

### Phase 2 (web MVP, public sites only)
- New repo: `qa-agent-web/` (Next.js, separate from Python core)
- Python service exposes API; web app calls it
- Database schema — new file `src/qa_agent/db/schema.sql` or use Supabase migration tools
- Spec editor UI (Monaco/CodeMirror)
- Cost meter UI component (reads from telemetry.json or API)

### Phase 3 (auth foundation + extensions, postponed from old Phase 1.5/2.5)
- `src/qa_agent/specs/schema.py` — extend Pydantic schema with `Auth` model
- New file: `src/qa_agent/auth/form.py` — form-based login helper
- New file: `src/qa_agent/auth/vault.py` — abstraction over credential storage
- `src/qa_agent/agent.py` — pre-auth step, `storage_state.json` plumbing, drop `--isolated` when auth is configured
- `src/qa_agent/preflight.py` (new) — separate preflight module since it grows with auth health checks
- `src/qa_agent/auth/oauth.py` — OAuth provider integrations
- `src/qa_agent/auth/totp.py` — 2FA TOTP support
- `src/qa_agent/auth/magic_link.py` — email integration

---

## Recommended sequence

1. **This week:** Validate pipeline on a 2nd site (~$5, generalization check). If pipeline doesn't generalize, fix analyst prompt before investing in MVP.
2. **Weeks 1–2:** Phase 1 cloud-readiness — Browserbase test + FastAPI wrapper + Docker image
3. **Weeks 3–6:** Phase 2 MVP web app (public sites only) — Stripe + Postgres + spec editor + cost meter
4. **Weeks 7–8:** Phase 4 hardening + pen test
5. **Public launch (public sites only):** ~2 months from start of Phase 1
6. **Weeks 9–12:** Phase 3 auth foundation + extensions (after user demand validates need)
7. **Months 4+:** Phase 5 enterprise (SAML/SOC2 when first enterprise customers ask)

After launch:
- Monitor cost per run, conversion rate, churn
- Phase 5 (enterprise) starts only after first 3–5 customers ask for SAML/SOC2

---

## Open questions for the user

Before scaling Phase 2, the following need owner input:

1. **Target customer profile** — small dev teams (10 devs), mid-market SaaS (50–500 employees), agencies, or enterprise? Drives pricing and feature priorities.
2. **Geographic launch** — US-first, EU-first, or both?
3. **Branding decision** — "Powered by Claude" prominent (Anthropic-only positioning), or "AI-agnostic" (multi-provider positioning)?
4. **Open-source posture** — keep CLI fully open-source, hosted version proprietary? Both proprietary? Both open?
5. **Funding runway** — bootstrapping (need positive unit economics from week 1) or VC-funded (loss-leader free tier OK)?
6. **Scenario cap per tier (D13)** — confirm Free=25 / Starter=30 / Pro=75, or adjust based on target customer's typical product complexity?

These shape decisions D8, D9, D11, D13 above.
