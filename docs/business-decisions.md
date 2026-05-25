# Business Decisions — qa-agent

Strategic decisions with rationale, alternatives considered, and expected outcomes. Updated as decisions are made or revisited.

---

## BD-001 — LLM provider strategy for SaaS tiers

**Date:** 2026-05-04
**Status:** Closed — validated and implemented

### Context

qa-agent currently supports two providers: Anthropic (production default) and Ollama (local development). The SaaS roadmap requires a cost-effective cloud provider for Free and Starter tiers, where Anthropic's ~$0.21/run makes unit economics unviable.

### Decision

Integrate Together.ai as a third provider, targeting:

| Role | Model | Estimated cost/run |
|------|-------|-------------------|
| Free executor | `Qwen/Qwen2.5-7B-Instruct-Turbo` | ~$0.04 |
| Starter executor | `meta-llama/Llama-3.3-70B-Instruct-Turbo` | ~$0.37 |
| Extractor (any tier) | `Qwen/Qwen2.5-7B-Instruct-Turbo` | ~$0.002 |

### Rationale

**Why Together.ai:**
- OpenAI-compatible API — LiteLLM supports it with a single prefix (`together_ai/<model>`)
- Hosts the exact open-weight models targeted in the roadmap (Llama 3.3 70B, Qwen 2.5)
- Pay-per-token pricing — no surprise rate-limit throttling for early users
- Significantly higher rate limits than Anthropic free tier (30K TPM)

**Why Llama 3.3 70B for Starter:**
Meta's latest instruction model, explicitly trained for tool use. Expected to emit proper CALL format (unlike local llama3.1:8b which requires ghost fallbacks). Comparable reasoning to Anthropic Haiku on structured tasks.

**Why Qwen 2.5 7B Turbo for Free/Extractor:**
Cost-optimized for simple tasks. High token throughput. Trade-off: may fall back to Ghost-B on dense pages — acceptable on free tier.

**Why Anthropic stays on Pro and Starter:**
Empirical data shows 100% pass rate on complex marketing sites. Anthropic Sonnet at ~$0.21/run is also cheaper per run than Together.ai Llama 70B (~$0.37/run), making it the better choice on both quality AND cost for paid tiers.

**Revised tier mapping (updated 2026-05-04):**

| Tier | Provider | Model | Cost/run | Revenue | Gross margin |
|------|----------|-------|----------|---------|--------------|
| Free (5 runs/mo) | Together.ai | Qwen 2.5 7B Turbo | ~$0.04 | $0 | -$0.20 (acquisition) |
| Starter ($19/mo, 50 runs) | **Anthropic** | claude-sonnet-4-6 | ~$0.21 | $19 | ~$8.50 |
| Pro ($49/mo, 200 runs) | Anthropic | claude-sonnet-4-6 | ~$0.21 | $49 | ~$7 |

### Validation findings (2026-05-04)

**Together.ai implementation:** done — `together_ai` provider added to `router.py`.

**Critical discovery:** Together.ai's `tools` parameter (OpenAI function calling) is only supported on a subset of hosted models. Confirmed working: `Llama-3.3-70B-Instruct-Turbo`, `Qwen2.5-7B-Instruct-Turbo`. Rejected with `UnsupportedParamsError`: `Qwen2.5-14B-Instruct-Turbo`, `Llama-3.1-8B-Instruct-Turbo`, `Hermes-3-Llama-3.1-8B`. This eliminates the mid-size cheap model tier.

**Model quality matrix (empirical, alconind.ro smoke suite):**

| Model | Provider | Cost/run | 3/3 PASS | Tool call format | Self-recovery |
|-------|----------|----------|----------|------------------|---------------|
| claude-sonnet-4-6 | Anthropic | ~$0.21 | ✓ | 100% CALL | ✓ |
| claude-haiku-4-5-20251001 | Anthropic | ~$0.056 | ✓ | 100% CALL | ✓ |
| Llama-3.3-70B-Instruct-Turbo | Together.ai | ~$0.05 | ✓ | 100% CALL | ✗ (no COT) |
| Qwen2.5-7B-Instruct-Turbo | Together.ai | ~$0.04 | 2/3 | Mixed (CALL + confused TEXT) | ✗ |

**Final decision — Anthropic-only architecture:**

| Tier | Model | Cost/run | Cost 5 runs/mo | Revenue | Gross margin |
|------|-------|----------|----------------|---------|--------------|
| Free (5 runs/mo) | claude-haiku-4-5-20251001 | ~$0.056 | ~$0.28/user | $0 | -$0.28 (acquisition) |
| Starter ($19/mo, 50 runs) | claude-sonnet-4-6 | ~$0.21 | ~$10.50 | $19 | ~$8.50 |
| Pro ($49/mo, 200 runs) | claude-sonnet-4-6 | ~$0.21 | ~$42 | $49 | ~$7 |

**Why Haiku over Together.ai Qwen 7B for Free tier:**
- Cost difference: $0.056 vs $0.04 = $0.08/month/user (negligible at early stage)
- Quality: 3/3 PASS vs 2/3, no hallucinations, no extractor fallback needed
- Reliability: same API infrastructure as paid tiers, no provider switching logic
- Free users who see broken test results churn immediately; quality matters even on free

**Together.ai role going forward:**
- Implemented and available as opt-in via `QA_EXECUTOR_PROVIDER=together_ai`
- Primary use case: BYOK (Bring Your Own Key) for enterprise users who want cost control
- Secondary: hedging against Anthropic pricing changes (LiteLLM abstraction enables switch within hours)
- Not used in default tier configuration

**Architecture simplification:** single provider (Anthropic) for all SaaS tiers reduces operational complexity, eliminates provider-specific failure modes in production, and centralises reliability guarantees. See `docs/architecture.md` §LLM Provider Architecture.

---

## BD-002 — Anthropic as Pro tier default (confirmed)

**Date:** 2026-04-28, confirmed 2026-05-04
**Status:** Confirmed

claude-sonnet-4-6 is the only provider achieving 100% pass rate on complex real-world sites (alconind.ro, 42-scenario suite, ~$0.21/run). All local and open-weight models have failure modes unsuitable for paid reliability guarantees. Together.ai 70B may narrow this gap — revisit after BD-001 validation.

---

## BD-003 — mistral-small:22b as recommended local model (confirmed)

**Date:** 2026-05-01, confirmed 2026-05-04
**Status:** Confirmed — documented in `docs/local-llms.md`

After testing all available local models, `mistral-small:22b` is the only one that:
1. Emits proper `CALL` tool call format (not ghost JSON)
2. Achieves 3/3 smoke at `QA_BOOTSTRAP_DEPTH=6`
3. Self-recovers from navigation confusion
4. Has no safety refusals on benign automation tasks

`qwen2.5-coder:14b` explicitly disqualified (safety refusals). All other models downgraded to "not recommended for production." Local Ollama use is scoped to development-time testing.

---

## BD-004 — Freemium tier structure and pricing

**Date:** 2026-05-19
**Status:** Closed — supersedes tier tables in BD-001 and `docs/roadmap.md`

### Context

BD-001 established Anthropic-only provider architecture. This decision defines the tier structure, limits, and unit economics for the SaaS freemium model, informed by:
- Measured costs: Haiku ~$0.0107/scenario, Opus analyst ~$1.40/run (73 scenarios, alconind.ro)
- Estimated Sonnet cost: ~$0.0274/scenario (not yet measured on v2 suite)
- The principle: **limit repetition, not the first experience** — the free tier must allow one complete analyst → executor → report cycle so users reach the "aha moment" before hitting any paywall

### Decisions

#### Tier limits

| | Free | Starter | Pro |
|---|---|---|---|
| **Price** | $0 | $29/mo | $99/mo |
| **Products** | 1 | 1 | 3 |
| **Analyst runs/month** | 2 (max 20 pages) | 5 (max 50 pages) | 10 (max 200 pages) |
| **Executor runs/month** | 5* | 20 | 50 |
| **Scenarios/run** | 15 (user selects which) | 30 | 75 |
| **Models** | Haiku + 1 Sonnet/mo teaser | Haiku + Sonnet | Haiku + Sonnet + Opus |
| **Issue detection** | Unlimited | Unlimited | Unlimited |

*Environmental failures (maintenance pages, anti-bot blocks, server errors) do not count against the executor run quota.

#### Issue detection is always unlimited

The deterministic scanner (JS errors, 4xx/5xx, broken links) has zero LLM cost. It runs during every analyst crawl and surfaces real site problems before any scenario executes. Capping it would remove the strongest free value hook. Issue detection is never gated by tier.

#### Scenario selection on capped tiers

When a product has more analyzed scenarios than the tier allows per run, the user explicitly selects which scenarios to include via checkboxes in the spec viewer (counter shows "X/15 selected"). This is preferable to arbitrary selection (first N alphabetically, random) because it preserves user trust and makes the cap visible without being punitive.

#### Sonnet teaser on free (1 run/month)

One Sonnet executor run per month on the free tier costs ~$0.41 (15 scenarios). This is acceptable as an acquisition cost and allows free users to experience the quality difference vs Haiku — the primary upgrade trigger for users on sites where Haiku produces ambiguous results.

#### Starter tier rationale ($29)

The $0 → $99 gap is too large for solopreneurs and small agencies. A Starter tier at $29 captures this segment. At full usage it still yields ~50% gross margin (see below).

### Unit economics

Cost assumptions:
- Analyst (Opus, ~73 scenarios): $1.40/run measured. With 20-page cap: ~$0.70 estimated (unvalidated — re-measure on smaller site)
- Executor Haiku: $0.0107/scenario measured (alconind.ro v2, 73 scenarios, 46% cache hit)
- Executor Sonnet: $0.0274/scenario estimated (not measured on v2)
- Compute (Fly.io): negligible at early stage

#### Free tier

| Item | Quantity | Unit cost | Monthly cost |
|------|----------|-----------|-------------|
| Analyst runs | 2 | $1.40 | $2.80 |
| Haiku executor runs | 4 × 15 scenarios | $0.0107/sc | $0.64 |
| Sonnet teaser run | 1 × 15 scenarios | $0.0274/sc | $0.41 |
| **Total cost/active user** | | | **~$3.85** |
| Revenue | | | $0 |
| **Acquisition cost** | | | **~$3.85/user** |

#### Starter tier ($29/mo)

At full usage (5 analyst + 20 executor runs, mix 15 Haiku / 5 Sonnet):

| Item | Quantity | Unit cost | Monthly cost |
|------|----------|-----------|-------------|
| Analyst runs | 5 | $1.40 | $7.00 |
| Haiku executor runs | 15 × 30 scenarios | $0.0107/sc | $4.85 |
| Sonnet executor runs | 5 × 30 scenarios | $0.0274/sc | $4.11 |
| **Total cost** | | | **~$15.96** |
| Revenue | | | $29 |
| **Gross margin** | | | **~45%** |

Margin range: 45–55% depending on Sonnet vs Haiku mix and analyst usage. Thin but acceptable for a bridging tier.

#### Pro tier ($99/mo)

At full usage (10 analyst + 50 executor runs):

| Model mix | LLM cost | Gross margin |
|-----------|----------|--------------|
| All Haiku (50 runs × 75 sc) | $14 + $40.13 = **$54.13** | **~45%** |
| Mixed (35 Haiku / 15 Sonnet) | $14 + $28.09 + $30.83 = **$72.92** | **~26%** |
| All Sonnet (50 runs × 75 sc) | $14 + $102.75 = **$116.75** | **-18% (loss)** |

**Implication:** Pro tier must not default to Sonnet. Haiku must remain the default model, with Sonnet as an explicit user choice. If Sonnet becomes the dominant choice on Pro, the tier is loss-making. Monitor model selection distribution from day 1 of beta.

**Sensitivity note:** Pro margins improve materially with sustained cross-scenario prompt caching (cache hit rate currently 46% on alconind.ro — if this holds on other sites, effective Haiku cost drops toward $0.006/scenario). Re-measure on second validated site before adjusting pricing.

### BYOK (Bring Your Own Key)

**Implementation trigger:** first paying user explicitly asks, or LLM cost exceeds 50% of revenue. Do not build before the trigger fires.

#### Design

BYOK is a **modifier on paid tiers**, not a separate tier. It decouples what you can do (run count, scenario cap — unchanged) from who pays for LLM inference (user, not us).

| Plan | Price | Runs/scenarios | LLM cost owner | Our cost | Gross margin |
|------|-------|---------------|----------------|----------|--------------|
| Starter managed | $29/mo | 20 runs / 30 sc | Us | ~$15.96 | ~45% |
| Starter + BYOK | $29/mo | 20 runs / 30 sc | User | ~$2.00 (compute only) | ~93% |
| Pro managed | $99/mo | 50 runs / 75 sc | Us | $54–73 | 26–45% |
| Pro + BYOK | $79/mo | 50 runs / 75 sc | User | ~$5.00 (compute only) | ~94% |
| Free | $0 | 5 runs / 15 sc | Us | ~$3.85 | n/a |

**Free tier has no BYOK.** If a free user could bring their own key, our cost drops to ~$0.10/month — meaning they could use the platform indefinitely with zero pressure to upgrade. The run-count limit is the conversion lever; removing the LLM cost from free removes the acquisition justification without replacing the upgrade trigger.

**Pro + BYOK at $79 (not $99):** the $20 discount is a concrete incentive for power users already paying Anthropic directly. Our margin at $79 is ~94% vs 26–45% on managed Pro — strongly in our favour.

**Starter + BYOK at same price ($29):** no discount needed because the value exchange is already in our favour (margin improves from 45% to 93%). The incentive for the user is model freedom, not price.

#### What BYOK unlocks

| | Managed | BYOK |
|--|---------|------|
| Model access | Gated per tier (Haiku / Sonnet / Opus) | Any valid LiteLLM model string |
| Rate limits | Shared pool (our account) | User's own Anthropic rate limits |
| Analyst model | Opus (we pay) | Any (they pay) |
| Cost visibility | Opaque to user | 100% visible in their Anthropic console |

Model freedom is the primary upgrade incentive for BYOK: a Starter user who wants Opus or the latest Claude release can get it by bringing their own key, without upgrading to Pro.

#### Implementation notes (when trigger fires)

- User's API key stored encrypted in Supabase (same KMS envelope encryption as Phase 3 auth credentials — implement together, not separately)
- LiteLLM receives the user's key via `api_key=` parameter per-call; never logged, never stored in run artifacts
- `executor_model` and `analyst_model` fields in the run request are fully unlocked (any model string accepted, validated against LiteLLM's provider list)
- Billing: Stripe subscription at BYOK price; LLM charges go to user's Anthropic account directly
- If user's key is invalid or over quota: run fails immediately with a clear error ("Your API key returned 401 — check your Anthropic account"), does not count against run quota

---

## BD-005 — Closed beta access model and tier constraints

**Date:** 2026-05-21, amended 2026-05-25 (added "Pre-invite acquisition cost")
**Status:** Closed — implemented

### Context

Before inviting the first 5-10 hand-picked beta users, we needed to define: what limits apply to them, how they discover those limits, and how we prevent runaway LLM costs without degrading the experience enough to lose feedback signal.

### Decisions

#### Beta tier limits

Beta users get the "beta" tier (`tier = 'beta'` in `public.users`), set manually via SQL when an invite is sent. Limits:

| Dimension | Beta | Free | Rationale |
|-----------|------|------|-----------|
| Executor runs/month | 10 | 5 | Enough to test 3-4 flows iteratively |
| Analyst scans/month | 3 | 2 | 1 initial + 2 follow-ups after fixes |
| Scenarios/run | 20 | 15 | Covers a realistic flow end-to-end |
| Models | Haiku + Sonnet | Haiku only | Sonnet exposes quality difference → upgrade trigger |
| Opus | Blocked | Blocked | Biggest cost risk; not needed to demonstrate value |

#### Why not Free tier limits for beta users

Free tier limits are designed for conversion pressure (upgrade after 2 runs), not for feedback gathering. Beta users need to complete a full cycle — analyst → review specs → run tests → fix → re-run — at least twice to give meaningful feedback. Free limits would cut them off mid-cycle.

#### Why not Starter tier limits

At full Starter usage (5 scans × $1.40 + 20 runs × $1.50), one active beta user can cost $37/month. With 10 users: $370/month before any revenue. Beta is a learning investment, not revenue, so cost must be bounded. Beta limits keep worst-case cost at ~$20/user/month = $200/month for 10 users.

#### Opus is blocked for all non-Pro users

Opus costs ~10× more than Haiku per run. A single 75-scenario Opus run costs ~$2-3 in executor tokens alone. Blocking it for free and beta removes the main cost runaway vector. Beta users can use Sonnet (good quality, ~$0.41 for 15 scenarios) which is sufficient to validate the product.

#### Issue detection is never quota-gated

The deterministic scanner (JS errors, 4xx/5xx, broken links) has zero LLM cost. Every analyst scan runs it automatically. Capping it would remove the strongest free value hook without any cost benefit.

#### Quota UX: show limits, don't hide them

When a user hits their limit:
1. API returns 429 with structured body (`code: quota_exceeded`, type, used, limit, tier)
2. Frontend shows a `QuotaLimitModal` — not a generic error toast
3. Modal copy: explains the limit, links to "talk to founder" email
4. On first monthly block: email sent to user (warm, relationship-focused) + email to admin (hot lead alert)
5. Subsequent blocks in same month: no additional emails (anti-spam)

Beta modal CTA links to `mailto:anghel@steadra.dev` — human conversation, not a checkout page. There is no Stripe yet; the goal is feedback and relationship, not revenue.

#### Tier visible in sidebar

The sidebar shows a tier badge (color-coded: cyan for beta, blue for starter, purple for pro) and live counters: `7/10 runs · 2/3 scans` (turns red when at limit). Users know their limits before hitting them.

#### Pre-invite acquisition cost (mini-scan)  *(added 2026-05-25)*

When a visitor submits their email on the landing page (`POST /waitlist`) along with the URL of their site, an automatic mini-scan runs on that URL and a short report is emailed to them. This is the primary activation lever for the beta funnel — see `docs/sales-and-marketing.md` § "Beta user flow", step 2.

This introduces a cost layer that the rest of BD-005 did not account for: cost is incurred **before** the user has accepted an invite and gained `tier=beta`. There is no `user_id` yet, and therefore no per-user quota to enforce.

**Model choice — Opus analyst (interim).**

The mini-scan reuses the same Opus-driven analyst path as the post-invite beta scan, with tight scope caps:

- `pages=[root_url]` — exactly one page, no crawl
- Bootstrap depth at default (5)
- Wall-time cap: 60 seconds
- Estimated cost per mini-scan: **~$0.15–0.20**

Haiku as the analyst model was considered and explicitly rejected for now — quality on the analyst role is not validated (see BD-001 model matrix: Haiku is only validated as an *executor*). Switching to Haiku is the planned fallback if Opus volume cost exceeds budget. See triggers below.

**Cost controls.**

Three mechanisms bound the worst-case monthly cost from runaway waitlist signups:

1. **Hard daily cap on mini-scans.** Global limit of 20 mini-scans/day. Beyond the cap, submissions are still accepted (email saved to waitlist) but no mini-scan runs; user gets a confirmation email saying their scan is queued for the next day. This caps Opus mini-scan cost at ~$120/month worst case.
2. **Rate-limit per IP.** Max 3 waitlist submissions per IP per hour. Blocks rapid-fire bot signups before they touch the scan queue.
3. **Bot / junk filtering at submit time** — explicitly *not* double opt-in email verification:
   - Server-side email syntax + MX record check (free, instant)
   - Block known disposable email domains (Mailinator, TempMail, Guerrilla Mail, etc.)
   - Cloudflare Turnstile (invisible captcha) on the waitlist form

**Why not double opt-in email verification.**

A "confirm your email before we run the scan" step was considered and rejected. Empirical evidence across SaaS landing pages shows a 20–30% conversion drop when users must leave the site, find the confirmation email, and click a link before continuing the funnel. The filters above catch ~95% of junk submissions with effectively zero conversion impact.

If junk volume becomes a problem despite these filters, the fallback is **not** double opt-in — it is switching to manual report review (per the Haiku migration trigger), which acts as a human filter at the send step.

**Updated cost envelope (BD-005 cap raised from $200/mo to ~$340/mo worst case).**

| Item | Volume assumption | Unit cost | Monthly |
|------|---|-----------|---------|
| Mini-scans on waitlist (Opus) — realistic | ~100 submits/mo | $0.20 | $20 |
| Mini-scans on waitlist (Opus) — worst case at daily cap | ~600 submits/mo | $0.20 | $120 |
| Beta tier usage (unchanged) | 10 users | $20 | $200 |
| Resend / Postmark drip emails (flat) | — | — | $20 |
| Cloudflare Turnstile, MX validation, disposable blocklist | — | $0 | $0 |
| **Total realistic** | | | **~$240** |
| **Total worst case (full daily cap)** | | | **~$340** |

Realistic landing at ~$240/mo is 20% above the original BD-005 cap of $200/mo. The full worst case ($340/mo) would only occur with sustained 20 submits/day for a full month — at which point waitlist volume itself signals enough demand to justify the cost.

**Triggers to revisit (for this section specifically).**

| Question | Trigger |
|----------|---------|
| Migrate mini-scan analyst to Haiku | Monthly Opus mini-scan cost > $50 sustained for 2+ months |
| Add manual report review before send | Quality issues reported by ≥2 beta users on the mini-scan output they received, OR Haiku migration triggered (review becomes the human filter for Haiku output quality) |
| Lower daily cap below 20 | Junk/bot volume exceeds 50% of submissions despite filters |
| Raise daily cap above 20 | All of: (a) signup demand exceeds cap consistently, (b) cost-per-paid-conversion stays favorable, (c) cumulative monthly mini-scan cost < $150 |

### Expected outcome

- Beta users experience the full product value (issue detection + scenario testing + iteration)
- Cost stays under $200/month for 10 users
- Users who hit limits reach out → warm conversion conversations
- We observe which limits are hit first (runs vs scans) → informs tier design for launch

### Triggers to revisit

| Question | Trigger |
|----------|---------|
| Are beta limits too tight? | ≥3 users hit limit in week 1 and report incomplete feedback |
| Are beta limits too generous? | Monthly cost > $300 before any revenue |
| Should Sonnet be default on beta? | ≥50% of beta runs use Sonnet explicitly; Haiku quality deemed insufficient |

### Open questions

| Question | Trigger to revisit |
|----------|--------------------|
| Does the 20-page analyst cap reduce cost proportionally? | Measure analyst cost on a site with ≤20 pages |
| Is 15 scenarios enough for a meaningful free aha moment? | First 5 beta users — do they understand value? |
| Is $29 Starter converting, or do users jump straight to Pro? | After 30 days of closed beta |
| Does Sonnet become dominant on Pro and erode margin? | Monitor model selection distribution from beta launch |
| Should Starter + BYOK get a small discount to incentivize adoption? | If Starter → Pro conversion rate is low after 60 days |
