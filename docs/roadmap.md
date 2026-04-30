# qa-agent — SaaS Roadmap

Strategic plan for transitioning qa-agent from a local CLI tool to a hosted SaaS where users authenticate, configure their products (including auth), and run automated test suites. Captures phased deliverables, open decisions, cost projections, and risk register.

> **Status:** Planning — no code written for SaaS yet. CLI is fully functional.
>
> **Last updated:** 2026-04-30

---

## Executive summary

The end goal is a multi-tenant SaaS at `qa-agent.io` (or similar) where:

1. Users sign up, add their product (URL + description + **auth config**)
2. Analyst auto-generates Gherkin specs by crawling the authenticated app
3. Users edit/approve specs, then run tests on demand or on schedule
4. Reports are stored, viewable, and consumable by downstream agents (fix-agent)

The biggest design pressures are:

- **Cost** — keep marginal cost per run low enough to support a generous free tier without bleeding cash
- **Reliability** — verdicts must be consistent; "ghost JSON" failures from local LLMs are unacceptable in a paid product
- **Security** — handling user credentials at scale is a serious responsibility; non-negotiable from day 1
- **Multi-provider flexibility** — LiteLLM already gives us this; preserve it

The key strategic insight: **don't self-host LLMs**. Inference APIs (Together.ai, Fireworks) host the same open-weight models we use locally, at API prices that are competitive with or cheaper than Anthropic for many tasks. Self-hosted GPUs only make sense at >3000 runs/month or for on-prem enterprise deployments.

---

## Current state (CLI)

### What works today

- Provider-agnostic via LiteLLM: Anthropic + Ollama tested
- Three roles implemented: Analyst (auto-generates specs from URL), Executor (runs scenarios), Reporter (transforms results)
- Playwright MCP for browser automation
- Spec format: Gherkin `.feature` files + `config.yaml`
- Local development on macOS (M4 Pro)

### Empirical limits

- **Anthropic Sonnet 4.6:** ~$0.21/run on 42-scenario alconind.ro suite, 100% reliable
- **Local Ollama:** qwen2.5:7b stable on simple sites; qwen2.5:14b and mistral-small:22b fail on dense pages (reasoning saturation — extract data correctly but don't synthesize verdict)
- **No auth support yet** — only public/marketing pages can be tested

---

## Strategic phases

### Phase 1 — Cloud-readiness (1–2 weeks)

**Goal:** Prove qa-agent runs on cloud infrastructure with hosted LLM and browser providers, not just locally.

| Task | Deliverable |
|------|-------------|
| Add Together.ai provider in `router.py` | New entry in `_LOCAL_PROVIDERS` registry; env var `QA_PROVIDER=together` works |
| Test Together.ai with Llama 3.3 70B + qwen2.5-72b on alconind.ro | Pass rate vs. Sonnet baseline; cost per run measured |
| Test Browserbase as drop-in for `npx @playwright/mcp` | Verify session persistence works; latency acceptable |
| Wrap CLI in FastAPI endpoint (`POST /api/runs`) | Single endpoint that accepts spec_dir + config, returns run_id |
| Containerize qa-agent (Docker image) | Multi-stage Dockerfile; runs in any cloud |

**Success criteria:** A run can be triggered via HTTP from any cloud machine, using cloud LLM + cloud browser, no local dependencies.

### Phase 1.5 — Auth foundation (2 weeks) ⚠️ CRITICAL

**Goal:** Support testing of authenticated apps. Without this, the tool can only test public marketing pages.

| Task | Deliverable |
|------|-------------|
| Extend `config.yaml` schema with `auth:` block | Form-based + API key types supported |
| Implement form-based login flow (helper in `agent.py`) | Pre-test login step using credentials from `auth.credentials_ref` |
| Session persistence across scenarios | Save `storage_state.json` after login; reuse for all scenarios in a run |
| Encrypted credential storage (envelope encryption with KMS) | Postgres column with KMS-encrypted blobs; never log plaintext |
| Pre-auth health check (preflight extension) | Verify login works before running 42 scenarios |
| Test on real authenticated app (staging Acme or similar) | End-to-end: 1 login + 5 authenticated scenarios passing |

**Success criteria:** Can run a test suite against an authenticated SaaS dashboard, with one login per run (not per scenario), credentials encrypted at rest.

### Phase 2 — MVP web app (2–4 weeks)

**Goal:** Public-facing web app where users sign up, add a product, and run tests.

| Task | Deliverable |
|------|-------------|
| Frontend Next.js scaffold (Vercel) | Landing page + dashboard layout |
| Auth: Clerk or Supabase Auth | Email/password + Google OAuth for users |
| "Add product" flow | URL + description + auth wizard (form-based + API key in MVP) |
| Spec viewer/editor (Monaco or CodeMirror) | View Analyst-generated specs, edit Gherkin inline |
| Run trigger + status page | Trigger run, show live progress, display report when done |
| Job queue (Inngest or Trigger.dev) | Async run execution; users don't wait for HTTP response |
| Stripe billing | Subscription tiers + per-run overage |
| Postgres schema (Supabase) | users, products, specs, runs, reports, credentials (encrypted) |

**Success criteria:** A new user can sign up, add a product with auth, generate specs, run tests, view a report — all via the web UI.

### Phase 2.5 — Auth extensions (3 weeks)

**Goal:** Cover broader auth landscape so most B2B SaaS apps are testable.

| Task | Coverage |
|------|----------|
| Magic link auth (email integration via Resend/Postmark) | ~15% of products |
| OAuth providers: Google, GitHub, Microsoft | ~25% of products |
| 2FA TOTP support (shared secret in vault) | ~30% of products (overlap) |
| Test account documentation + UX | Recommend dedicated test accounts everywhere |

**Success criteria:** ~80% of B2B SaaS products can be tested without manual workarounds.

### Phase 3 — Hardening (2 weeks)

**Goal:** Production-quality reliability and security.

| Task | Why |
|------|-----|
| Rate limiting per user/tenant | Prevent abuse, cap LLM spend |
| Retry logic for transient failures | LLM timeouts, browser flakiness |
| BYOK (Bring Your Own Key) for Anthropic / Together | Enterprise option, removes our LLM cost for power users |
| Audit log for credential access | Security/compliance requirement |
| Session expiry handling + re-auth | Long-running runs that outlive auth session |
| Pen test ($5–10K) | Pre-launch security validation |

### Phase 4 — Enterprise (4+ weeks, after first paying customers)

| Task | Why |
|------|-----|
| SAML SSO + SCIM provisioning | Enterprise procurement requirement |
| Dedicated vault (HashiCorp Vault or AWS Secrets Manager) | Stronger credential isolation per tenant |
| On-prem deployment option (Docker Compose) | For customers who can't send credentials to cloud |
| SOC2 Type 1 audit ($15–25K, 6 months) | Required for mid-market and enterprise sales |
| Custom SLA + dedicated support | Enterprise tier offering |

---

## Multi-provider LLM strategy

### Recommended tier mapping

| Tier | LLM Provider | Model | Cost/run | Margin at price |
|------|--------------|-------|----------|-----------------|
| Free (5 runs/mo) | Together.ai | Qwen 2.5 7B Turbo | ~$0.04 | n/a (loss leader) |
| Starter ($19/mo, 50 runs) | Together.ai | Llama 3.3 70B | ~$0.37 | ~50% gross |
| Pro ($49/mo, 200 runs) | Anthropic | Sonnet 4.6 | ~$0.21 | ~60% gross |
| Enterprise (custom) | Anthropic | Opus 4.7 | ~$0.80 | negotiated |
| BYOK (any tier) | User's API key | Any | $0 LLM cost | infrastructure-only fee |

**Rationale:** Anthropic remains the reliability gold standard for paying tiers. Together.ai serves free + cost-sensitive tiers. BYOK lets power users bring their own keys, removing LLM cost entirely from our P&L.

### Architectural decision: Level 1 vs Level 2 verdict

We discussed two approaches to fix the "model doesn't call `report_result`" issue with local/open models:

- **Level 1 (forced `tool_choice` retry):** Single-phase, Python forces `tool_choice={"function": {"name": "report_result"}}` if the LLM stops without calling it. Works only with Anthropic and possibly larger Together.ai-hosted models (70B+).
- **Level 2 (two-phase):** Phase A explores with browser tools only (no `report_result` tool); Phase B is a single LLM call with structured output enforcing JSON schema for the verdict.

**Recommendation for SaaS:** Default to **Level 1** with Anthropic on paid tiers. Level 2 becomes attractive only if we want to optimize the free tier (qwen 7B for Phase A + Haiku for Phase B = ~$0.10/run with structured output guarantee). Defer Level 2 implementation until free tier volume justifies the engineering cost (~30 lines of code, but new failure modes to test).

---

## Cost model

### Per-run cost breakdown (cloud)

```
Anthropic Sonnet 4.6 (executor):     $0.21
Browserbase (10 min/run avg):         $0.50
Compute orchestration (Modal/Fly):    $0.05
Database, storage, CDN:               $0.02
─────────────────────────────────────────────
Total marginal cost per run:         ~$0.78
```

### Pricing model

| Tier | Price | Runs/month | Cost to us | Gross margin |
|------|-------|------------|-----------|--------------|
| Free | $0 | 5 | ~$2 | -$2/user (acquisition cost) |
| Starter | $19/mo | 50 | ~$25 (Together.ai) | -$6/user (loss leader) |
| Pro | $49/mo | 200 | ~$24 (Anthropic) | $25/user (~50% gross) |
| Enterprise | $500+/mo | unlimited (with reasonable use) | varies | 50–70% gross |
| BYOK | $5/run flat fee | n/a | $0.55 | $4.45/run (~90% gross) |

**Note:** Starter tier is intentionally a slight loss leader to drive conversions to Pro. Pro is the breadwinner. Enterprise + BYOK are pure margin businesses once acquired.

### Break-even analysis

Self-hosted GPU only makes sense beyond ~3,000 runs/month, which corresponds to ~600 Pro users running 5 runs/month each. Until then, inference APIs (Anthropic + Together.ai) are cheaper.

---

## Open decisions

These need to be made before / during Phase 1. Each comes with a default recommendation but should be confirmed by the user.

| # | Decision | Options | Recommendation | Why |
|---|----------|---------|----------------|-----|
| **D1** | Primary LLM provider | (a) Anthropic-only (b) Together.ai-only (c) Multi-provider via LiteLLM | (c) Multi-provider | Already supported; enables tier mapping above |
| **D2** | Verdict architecture | (a) Level 0 current (b) Level 1 forced retry (c) Level 2 two-phase | (b) Level 1 | Reliable on Anthropic; Level 2 deferred until needed |
| **D3** | Credential vault | (a) Postgres + KMS (b) Doppler (c) HashiCorp Vault (d) AWS Secrets Manager | (a) Postgres + KMS at MVP, migrate to (c) at enterprise | Cheap, sufficient for early stage |
| **D4** | Auth tier scope | (a) All tiers same (b) Free = public only, paid = auth | (b) Free = public only | Reduces our security blast radius for free users |
| **D5** | Worker model | (a) Platform-managed only (b) BYO worker (CLI mode) (c) Both | (c) Both | Platform for UX, BYOK/self-host for security-conscious users |
| **D6** | Browser provider | (a) Browserbase (b) Self-hosted Playwright on Modal/Fly (c) Both | (a) Browserbase at MVP | Faster to ship; revisit cost at >$1k/mo browser spend |
| **D7** | Hosting platform | (a) Vercel + Railway (b) Modal end-to-end (c) Fly.io for everything | (a) Vercel + Railway | Best DX for early stage; migrate workers to Modal later |
| **D8** | Compliance roadmap | (a) Start SOC2 from day 1 (b) Defer until enterprise demand | (b) Defer | Premature for early stage; commit when first enterprise asks |
| **D9** | Geographic regions | (a) US only (b) US + EU | (a) US only at launch, EU within 12 months | Most early customers will be US/EU SMBs comfortable with US hosting; EU when GDPR-strict customers ask |
| **D10** | OAuth scope at MVP | (a) Form + API key only (b) Form + API key + Google OAuth | (a) Form + API key only at MVP | OAuth has anti-bot challenges; defer to Phase 2.5 |
| **D11** | Pricing model | (a) Subscription only (b) Subscription + overage (c) Pay-per-run | (b) Subscription + overage | Predictable revenue + flexibility for spiky usage |
| **D12** | Free tier policy on auth | (a) No auth on free (b) Form auth allowed on free | (a) No auth on free | Mitigates security risk + keeps free cheap |

---

## Risk register

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Credential breach (stored user passwords leaked) | Low | Catastrophic | KMS encryption, rotation, audit logs, pen test, cyber insurance |
| LLM provider price changes (Anthropic raises rates 2×) | Medium | High | Multi-provider via LiteLLM; can switch within hours |
| Together.ai or similar shutters | Low | Medium | Multiple open-model providers; LiteLLM abstracts |
| Anti-bot detection blocks our crawls (Cloudflare, reCAPTCHA) | Medium | Medium | Browserbase has stealth mode; offer BYO worker for bypass |
| 2FA-required products can't be tested | High | Medium | Document workarounds (TOTP shared secret, email forwarding); acknowledge limitation |
| Scaling browser worker pool gets expensive | Medium | Medium | Self-host Playwright on Modal at >$1k/mo Browserbase spend |
| Customer credential rotation breaks runs silently | High | Low | Health check before each run; email alerts on auth failure |
| Spec format changes break existing user specs | Medium | High | Versioned spec schema with migration path |
| Free tier abuse (users running thousands of free runs) | High | Medium | Strict rate limit + IP-based throttling on free tier |
| Browser automation flakiness causes false fails | High | Medium | Retry transient failures; show "flaky" badge in UI |
| LLM hallucinates verdict (says PASS when actually FAIL) | Low (Anthropic), Medium (open) | High | Sample audit; use Sonnet+ on paid tiers; track historical accuracy |

---

## Implications for existing code

The current architecture is largely SaaS-ready. Specific changes needed by phase:

### Phase 1 (cloud-readiness)
- `src/qa_agent/llm/router.py` — add Together.ai entry to `_LOCAL_PROVIDERS` (no, actually it's a remote provider — add to `_DEFAULTS` with new role mappings)
- `src/qa_agent/agent.py` — `_make_server_params()` already configurable via `QA_BROWSER`; extend to support remote MCP endpoints (`QA_MCP_ENDPOINT` env var) for Browserbase
- New file: `src/qa_agent/api.py` — FastAPI wrapper exposing `POST /runs`, `GET /runs/{id}`, etc.
- New file: `Dockerfile` — multi-stage build, copy specs, install Playwright, run as non-root
- `pyproject.toml` — add `fastapi`, `uvicorn` to deps

### Phase 1.5 (auth foundation)
- `src/qa_agent/specs/schema.py` — extend Pydantic schema with `Auth` model
- New file: `src/qa_agent/auth/form.py` — form-based login helper
- New file: `src/qa_agent/auth/vault.py` — abstraction over credential storage
- `src/qa_agent/agent.py` — pre-auth step, `storage_state.json` plumbing, drop `--isolated` when auth is configured
- `src/qa_agent/preflight.py` (new) — separate preflight module since it grows with auth health checks

### Phase 2 (web MVP)
- New repo: `qa-agent-web/` (Next.js, separate from Python core)
- Python service exposes API; web app calls it
- Database schema — new file `src/qa_agent/db/schema.sql` or use Supabase migration tools

### Phase 2.5 (auth extensions)
- `src/qa_agent/auth/oauth.py` — OAuth provider integrations
- `src/qa_agent/auth/totp.py` — 2FA TOTP support
- `src/qa_agent/auth/magic_link.py` — email integration

---

## Recommended sequence

1. **This week:** Make decisions D1, D2, D3, D6 (LLM provider strategy, verdict architecture, vault, browser provider). These unblock Phase 1.
2. **Next 2 weeks:** Phase 1 (cloud-readiness) + start Phase 1.5 design (auth schema spike)
3. **Weeks 3–4:** Complete Phase 1.5 (auth foundation), test end-to-end on a real authenticated app
4. **Weeks 5–8:** Phase 2 (MVP web app) — focus on Pro tier user experience
5. **Weeks 9–11:** Phase 2.5 (auth extensions)
6. **Weeks 12–13:** Phase 3 (hardening) + pen test
7. **Public launch target:** ~3 months from start of Phase 1

After launch:
- Monitor cost per run, conversion rate, churn
- Phase 4 (enterprise) starts only after first 3–5 customers ask for SAML/SOC2

---

## Open questions for the user

Before kicking off Phase 1, the following need owner input:

1. **Target customer profile** — small dev teams (10 devs), mid-market SaaS (50–500 employees), agencies, or enterprise? Drives pricing and feature priorities.
2. **Geographic launch** — US-first, EU-first, or both?
3. **Branding decision** — "Powered by Claude" prominent (Anthropic-only positioning), or "AI-agnostic" (multi-provider positioning)?
4. **Open-source posture** — keep CLI fully open-source, hosted version proprietary? Both proprietary? Both open?
5. **Funding runway** — bootstrapping (need positive unit economics from week 1) or VC-funded (loss-leader free tier OK)?

These shape decisions D1, D8, D9, D11 above.
