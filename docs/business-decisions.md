# Business Decisions — qa-agent

Strategic decisions with rationale, alternatives considered, and expected outcomes. Updated as decisions are made or revisited.

---

## BD-001 — Together.ai as second LLM provider

**Date:** 2026-05-04
**Status:** Planned — implementation starting

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

**Key correction from original roadmap:** Llama 3.3 70B on Together.ai (~$0.37/run) is more expensive than Anthropic Sonnet (~$0.21/run) and less reliable (no self-recovery from navigation loops). There is no economic or quality argument for using it on paid tiers. Together.ai remains relevant only for the Free tier (Qwen 7B Turbo at ~$0.04/run) and as a BYOK option.

### Implementation plan

**Phase A — Code (~1-2h):**

1. `src/qa_agent/llm/router.py`:
   - Add `together_ai` defaults per role in `_DEFAULTS`
   - Add `litellm_model()` branch: `return f"together_ai/{m}"`
   - Add timeout defaults: Llama 70B ~60s, Qwen 7B ~15s
   - No `extra_kwargs()` changes — `TOGETHER_API_KEY` is auto-read by LiteLLM

2. `README.md` — add Together.ai to providers table and example runs

3. `docs/cloud-llms.md` (new) — model selection guide, cost estimates, quality matrix

**Phase B — Validation (~30 min):**

```bash
# Starter tier candidate
QA_EXECUTOR_PROVIDER=together_ai \
QA_EXECUTOR_MODEL=meta-llama/Llama-3.3-70B-Instruct-Turbo \
uv run qa-agent run specs/alconind-smoke --output reports/alconind-smoke-together-70b

# Free tier candidate
QA_EXECUTOR_PROVIDER=together_ai \
QA_EXECUTOR_MODEL=Qwen/Qwen2.5-7B-Instruct-Turbo \
uv run qa-agent run specs/alconind-smoke --output reports/alconind-smoke-together-7b
```

**Key questions validation answers:**
1. Does Llama 3.3 70B emit proper `CALL` tool calls?
2. Pass rate vs Anthropic baseline (3/3 smoke = green light for Starter tier)
3. Actual cost per run (validate estimates)
4. Speed: turns/second on Together.ai infrastructure

**Phase C — Decision gates:**

| Outcome | Decision |
|---------|----------|
| Llama 70B: 3/3 PASS + proper CALLs | Confirm Starter tier. Begin Phase 1.5 (auth foundation). |
| Llama 70B: 2/3 PASS or ghost fallbacks | Evaluate Anthropic Haiku for Starter. Revisit tier pricing. |
| Qwen 7B: 3/3 PASS + proper CALLs | Confirm Free tier as-is. |
| Qwen 7B: fails on complex scenarios | Free tier = public-pages-only restriction (already in roadmap D4). |

### Risks

| Risk | Likelihood | Mitigation |
|------|-----------|------------|
| Llama 3.3 70B quality below Anthropic | Medium | Ghost fallback chain handles it; extractor as last resort |
| Together.ai pricing changes | Low | LiteLLM abstraction allows switch to Fireworks/Groq within hours |

### Alternatives considered

- **Anthropic Haiku for Starter** — $0.08/run, higher quality but 2× cost. Keep as fallback.
- **Groq** — very fast but limited model selection and stricter rate limits.
- **Fireworks.ai** — comparable pricing, less established ecosystem.
- **Self-hosted vLLM on Modal** — viable at >3,000 runs/month; premature now.

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
