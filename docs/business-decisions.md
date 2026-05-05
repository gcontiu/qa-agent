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
