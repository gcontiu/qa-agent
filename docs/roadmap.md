# qa-agent — SaaS Roadmap

Strategic plan for transitioning qa-agent from a local CLI tool to a hosted SaaS where users authenticate, configure their products (including auth), and run automated test suites. Captures phased deliverables, open decisions, cost projections, and risk register.

> **Status:** Closed beta in progress. Steps 1–11 + tier enforcement + landing page done. steadra.dev is live with waitlist capture. Beta users can be invited via Supabase invite + `UPDATE users SET tier='beta'`. Next: onboard 5-10 users, collect feedback, then Stripe + public launch.
>
> **Last updated:** 2026-05-21

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
| Validation on a 2nd site | ⚠ Partial — analyst confirmed on diy.com (B&Q); executor ran 1 scenario but hit anti-bot soft-block. Pipeline mechanics confirmed; full suite validation deferred (see anti-bot strategy notes). |

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
| 8 | **React+Vite dashboard — foundation** (Step 7a): scaffold + React Router + Tailwind + shadcn/ui + TanStack Query + Supabase client + sidebar layout + auth migration from static HTML | Establishes the component and routing foundation. Same-domain served by FastAPI — no CORS, no second deploy. See **Frontend stack note** below. |
| 9 | **Products & Analyst UI** (Step 7b): products list + create, product detail, "Analyze" trigger + polling | Exposes analyst in UI for the first time. |
| 10 | **Spec viewer/editor** (Step 7c): spec list per product, Monaco editor (lazy-loaded), Save + Approve | Mandatory human-in-the-loop gate. Without approve step, analyst hallucinations reach executor unchecked. Monaco lazy-loaded (~2MB, only on this page). |
| 11 | **Runs, statistics, report viewer** (Step 7d): run list + status badges, run detail (summary stats + per-scenario results + evidence viewer), cost meter from `telemetry.json` | Wraps existing `GET /runs`, `GET /runs/{id}`, `GET /runs/{id}/report`. Cost meter surfaces existing `cost_usd`. |

> **Frontend stack note (decision 2026-05-15):** The dashboard uses **React + Vite** (not Next.js), served as static files from FastAPI on the same domain. Next.js was rejected because: the dashboard is fully auth-gated (no SEO benefit from SSR), all data comes from FastAPI (no need for Next.js API routes), and running Next.js as a Node server on Fly.io adds a second process with no benefit at this stage. **Marketing/landing site** (when needed) will be a separate sub-project (Next.js or Astro on Vercel/Cloudflare Pages) — the dashboard does not need to be rebuilt for that. **Migration cost React+Vite → Next.js:** ~1 day (components are 1:1 React; only routing structure changes).

> **React stack:** React 18 + TypeScript, Vite, React Router v6, TanStack Query (polling + caching), shadcn/ui + Tailwind CSS, react-hook-form + zod, Monaco Editor (lazy), `@supabase/supabase-js`.

| 12 | **Landing page** (steadra.dev) | Public `/` with hero, pricing, waitlist email capture → `POST /waitlist`. www redirect. TLS via Fly + Let's Encrypt. |
| 13 | **Tier enforcement + quota UX** | `tier` column on `public.users`, `quota_events` table, `GET /me/quota`, enforcement on `POST /runs` + `POST /products/{id}/analyze`, TierBadge in sidebar, `QuotaLimitModal` on 429, Resend email on first monthly block. Beta tier: 10 runs / 3 scans / 20 scenarios / Haiku+Sonnet. Opus blocked for free/beta. |

**Stop here for closed beta.** Onboard 5–10 hand-picked users. Validate demand. Stripe + tiered scenario caps come *after* this stage answers "do people want this?".

#### Phase 2 — Deferred from MVP

Each item is deferred against a specific trigger. When the trigger fires, move it into the active scope; not before.

| Deferred item | Trigger to reactivate |
|---------------|----------------------|
| **Redis queue (Upstash, `arq`/`rq`)** | >5 concurrent jobs observed, or `BackgroundTasks` lose runs on deploy/restart in production |
| **Separate worker machine** (Fly process group) | Web requests start timing out due to worker CPU; or worker crashes take down API |
| **R2/S3 for report storage** | Average `report.json` + evidence > 1 MB, or users request public report sharing links |
| **`.specs/` temp dir cleanup + volume reduction** | Before Phase 2 public launch. See note below. |
| **Stripe billing + tiered plans** | Closed beta validates retention ≥ 30% week-2; until then, manual invoicing for paid users |
| **Tiered scenario caps (Free/Starter/Pro) via Stripe** | Stripe webhook sets `tier` column; beta enforces limits manually. Full per-tier enforcement already in `TIER_LIMITS` dict in `api.py` — only Stripe webhook integration is missing. |
| **Product count limit per tier** (Free=1, Starter=1, Pro=3) | Defined in BD-004 but not yet enforced in `POST /products`. Trigger: Stripe live (tier becomes meaningful boundary). Until then, product count is unlimited — scans/runs limits provide sufficient cost control. |
| **BYOK (user's Anthropic key)** | First paying user explicitly asks, or LLM cost > 50% of revenue. Design finalized in BD-004 — Starter+BYOK=$29, Pro+BYOK=$79, Free has no BYOK. Implementation shares KMS encryption with Phase 3 auth credentials; build together, not separately. |
| **Auth into *target products*** (form login, OAuth, 2FA, KMS vault — Phase 3) | ≥ 30% of beta users request testing of authenticated pages; or first paying customer makes it a deal-breaker |
| **Executor runs only approved specs** (`get_files_dict` filters `approved = true`) | First beta user complains that unapproved/draft specs reached the executor and produced misleading results; or approval workflow is confirmed as mandatory UX gate before launch |
| **CI / deploy-triggered scans** (per-user API keys + GitHub Action + `target_url` override; Vercel/Netlify webhook later) | First beta user asks to run scans automatically on deploy/CI, or retention data shows manual re-runs are the drop-off point. Design in `architecture.md` § CI / Deploy-Triggered Scans. |
| **Retry logic + flaky-test badging** (Phase 4) | False-fail rate in production > 5%, measured over ≥ 100 runs |
| **Browserbase Stealth Mode** (`proxies: true` + fingerprint) | First user reports consistent anti-bot blocks (Cloudflare, reCAPTCHA) preventing analyst/executor from accessing their site; or >10% of runs fail due to challenges. Current mitigation: `QA_SCENARIO_DELAY=3` between sessions reduces rate-based detection. |
| **Self-hosted Playwright on Modal** | Browserbase spend > $1k/month |
| **Multi-region deploy (EU)** | First EU customer with data residency requirement, or > 20% of users from EU |
| **SAML SSO / SCIM / SOC2** (Phase 5) | First enterprise prospect blocks deal on it; until then, $0 spent |
| **UI polish: dark mode, mobile, animations** | Beta feedback explicitly cites UI as a blocker (not vague "looks rough") |
| **Spec versioning & migration tooling** | First breaking change to Gherkin schema with existing user specs in production |
| **`fix-agent` integration / downstream consumers** | qa-agent itself is stable and 2+ users have asked for it |

**Note — `.specs/` temp dir + volume strategy (discussed 2026-05-14):**

When a run is triggered with `product_id`, specs are materialized from Supabase to `reports/run-<id>/.specs/` so `load_spec(Path)` can read them. This temp dir is never deleted — it accumulates on the Fly.io persistent volume with every run.

**Immediate fix (pre-Phase-2):** call `shutil.rmtree(temp_dir)` immediately after `load_spec()` returns — the data is in memory from that point on and the directory serves no further purpose.

**Broader question:** with specs already in Supabase, is the Fly.io volume still needed? By layer:
- `.specs/` temp dir — no, should not survive past `load_spec()`
- `report.json` + `evidence/` (screenshots) — yes, until the R2/S3 trigger fires
- `run_status.json` — redundant with `jobs` table in Postgres, but kept as a restart-recovery fallback for `GET /runs` when the in-memory `_runs` dict is empty; can be removed once `GET /runs` reads from DB
- `runs.db` (SQLite) — still needed for flakiness tracking and `--only-failing`; no DB equivalent

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
| **Coverage gap analysis** (`POST /products/{id}/coverage-gaps`) | Analyst re-crawls the live app and compares against existing specs; returns a coverage matrix (page/flow → tested ✅ / partial ⚠️ / missing ❌) prioritized by business impact. Lets users catch spec drift when the product evolves without re-running a full analyst pass. Implementation: reuse Playwright MCP crawl + diff against `specs` table in DB. |

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

### Recommended tier mapping (finalized 2026-05-19 — BD-004)

> Full unit economics and rationale in `docs/business-decisions.md` BD-004. Summary below.

| Tier | Price | Executor runs/mo | Scenarios/run | Models available | Gross margin |
|------|-------|-----------------|---------------|------------------|--------------|
| Free | $0 | 5 (env failures free) | 15 (user selects) | Haiku + 1 Sonnet/mo teaser | −$3.85/user (acquisition) |
| Starter | $29/mo | 20 | 30 | Haiku + Sonnet | ~45% |
| Pro | $99/mo | 50 | 75 | Haiku + Sonnet + Opus | 26–45% (model-mix sensitive) |

**Analyst runs** (Opus, page-capped): Free = 2/mo (max 20 pages), Starter = 5/mo (max 50 pages), Pro = 10/mo (max 200 pages).

**Issue detection** is unlimited on all tiers — zero LLM cost, strongest free value hook.

**Key constraints:**
- Haiku must remain the default executor on all tiers. Pro tier turns loss-making if Sonnet becomes the dominant choice (~$116 cost vs $99 revenue at full Sonnet usage).
- Monitor model selection distribution from first day of beta.
- Environmental failures (anti-bot blocks, maintenance pages, server errors) do not count against executor run quota.
- Scenario selection on capped tiers: user explicitly picks which scenarios to include in spec viewer (checkbox per scenario, counter "X/15 selected").

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

### Pricing model (finalized 2026-05-19 — BD-004)

> Supersedes previous tier tables. Full breakdown in `docs/business-decisions.md` BD-004.

| Tier | Price | Executor runs/mo | Scenarios cap | Monthly cost to us (full usage) | Gross margin |
|------|-------|-----------------|---------------|---------------------------------|--------------|
| Free | $0 | 5 | 15 | ~$3.85 | −$3.85 (acquisition) |
| Starter | $29/mo | 20 | 30 | ~$15.96 | ~45% |
| Pro | $99/mo | 50 | 75 | $54–73 (model-mix dependent) | 26–45% |

**Critical margin note:** Pro margin ranges from 45% (all-Haiku) to 26% (mixed) to −18% (all-Sonnet). Haiku must be the default. Track model distribution from day 1 of beta.

**Not yet implemented** (trigger: Stripe live + beta validates retention):
- Per-tier enforcement in API
- Enterprise tier pricing

#### BYOK (Bring Your Own Key) — design finalized, implementation deferred

BYOK is a modifier on paid tiers, not a separate tier. Run counts and scenario caps are unchanged; only who pays for LLM inference changes.

| Plan | Price | Our margin |
|------|-------|------------|
| Starter managed | $29/mo | ~45% |
| Starter + BYOK | $29/mo | ~93% |
| Pro managed | $99/mo | 26–45% |
| Pro + BYOK | $79/mo | ~94% |
| Free | $0 | no BYOK |

Key rules:
- **Free has no BYOK** — removing LLM cost from free eliminates the upgrade pressure without replacing it with anything else
- **Pro + BYOK at $79** (not $99) — $20 discount incentivizes power users already paying Anthropic; our margin improves dramatically
- **Starter + BYOK at $29** (no discount) — value exchange already favours us; model freedom (any LiteLLM model, not tier-gated) is the incentive
- BYOK + invalid key → run fails immediately, does not count against quota
- Implementation requires KMS encryption (same as Phase 3 auth credentials) — build together, not separately

Full rationale and implementation notes: `docs/business-decisions.md` BD-004 § BYOK.

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
| **D7** | Frontend hosting | **Closed 2026-05-15** | React+Vite SPA served by FastAPI same-domain on Fly.io (Step 7); marketing site separate (Next.js or Astro on Vercel) when needed |
| **D8** | Compliance roadmap | Open | Defer SOC2 until enterprise demand |
| **D9** | Geographic regions | Open | US first, EU within 12 months |
| **D10** | OAuth at MVP | **Postponed — Phase 3** | Form + API key only at Phase 3 launch |
| **D11** | Pricing model | **Closed 2026-05-19 (BD-004)** | Free $0 / Starter $29 / Pro $99 subscription; no per-run overage at MVP |
| **D12** | Free tier policy on auth | Open | No auth on free (mitigates security risk) |
| **D13** | Scenario cap policy | **Closed 2026-05-19 (BD-004)** | Free=15 / Starter=30 / Pro=75; user selects which scenarios run; env failures excluded from quota |

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
- `frontend/` directory in same repo — React+Vite SPA (not Next.js; no second deploy)
- FastAPI serves built static files: `GET /` → `index.html`, `/assets/*` → static, `GET /*` → SPA fallback for React Router
- Dockerfile updated with Node multi-stage build: `npm ci && npm run build` → `dist/` → copied into Python image
- Database schema — `supabase/migrations/` (already using Supabase migration tooling)
- Spec editor UI (Monaco, lazy-loaded in Step 7c)
- Cost meter UI component (reads `cost_usd` from existing API responses)
- Marketing/landing site: separate sub-project (Next.js or Astro) when public SEO pages needed — not in this repo

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
6. ~~**Scenario cap per tier (D13)**~~ — closed 2026-05-19 (BD-004): Free=15 / Starter=30 / Pro=75.

These shape decisions D8, D9, D11, D13 above. D11 and D13 are now closed.
