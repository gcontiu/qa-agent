## Cloud LLM provider compatibility (`llm/router.py`, `agent.py`)

Empirical results for cloud-hosted models tested against alconind.ro (industrial B2B marketing site, dense DOM). All runs use `specs/alconind-smoke` (3 scenarios: AC-001 homepage, AC-003 click navigation, AC-100 product categories).

---

### Anthropic

Anthropic models are the reliability gold standard. All emit proper `tool_calls` format, produce chain-of-thought reasoning alongside tool calls (`CALL` + `TEXT`), and self-recover from navigation loops via COT.

**Behaviour patterns:**
- All tool calls are proper `CALL` (not ghost JSON) — no fallback chain ever needed
- TEXT narration between turns provides reasoning visibility
- Self-recovery: when loop guard fires, model reads the message and navigates directly to the target URL
- Rate limit: Tier-1 API = 30K input tokens/minute. Back-to-back scenarios exhaust this; rate-limit retry (`QA_RATE_LIMIT_RETRIES=2`) handles it automatically

| Model | Smoke (3/3) | Cost/run | Speed | Notes |
|-------|------------|----------|-------|-------|
| `claude-sonnet-4-6` | ✓ | ~$0.21 | ~13s/scenario | Pro/Starter tier default. Best reasoning quality |
| `claude-haiku-4-5-20251001` | ✓ | ~$0.056 | ~12s/scenario | Free tier default. Same reliability as Sonnet, slightly more turns on navigation scenarios |

**Known quirk — double-click on navigation links:**
Both Sonnet and Haiku occasionally click a navigation link twice: after the first click navigates to `/produse`, the nav menu still shows "Produse" with the same `[ref=eXX]`. The model sees the ref and tries to click again. Sonnet self-recovers via COT ("the ref seems to be expiring, let me navigate directly"). The loop guard in `agent.py` blocks the second click before it executes and injects a fresh snapshot.

---

### Together.ai

Together.ai hosts open-weight models via an OpenAI-compatible API. **Critical constraint:** the `tools` parameter (function calling) is only supported for a subset of hosted models. Most 7B–14B models throw `UnsupportedParamsError` when `tools` is passed.

#### Models with `tools` support confirmed

| Model | Smoke (3/3) | Cost/run | Tool call format | Self-recovery | Notes |
|-------|------------|----------|------------------|---------------|-------|
| `meta-llama/Llama-3.3-70B-Instruct-Turbo` | ✓ | ~$0.05 | 100% CALL | ✗ | No COT — click loops until loop guard fires; no ability to self-navigate |
| `Qwen/Qwen2.5-7B-Instruct-Turbo` | 2/3 | ~$0.04 | Mixed (CALL + confused TEXT) | ✗ | See detailed analysis below |

#### Models rejected — `UnsupportedParamsError` on `tools`

These models are hosted on Together.ai but do not support the OpenAI `tools` parameter. They cannot be used with qa-agent without dropping tool definitions entirely (which would break all tool-calling behaviour):

| Model | Error |
|-------|-------|
| `Qwen/Qwen2.5-14B-Instruct-Turbo` | `UnsupportedParamsError: does not support parameters: ['tools']` |
| `NousResearch/Hermes-3-Llama-3.1-8B` | `UnsupportedParamsError: does not support parameters: ['tools']` |
| `meta-llama/Llama-3.1-8B-Instruct-Turbo` | `UnsupportedParamsError: does not support parameters: ['tools']` |

#### Detailed analysis: Llama 3.3 70B

**Behaviour:** 100% proper `CALL` tool calls — best tool-use format among all non-Anthropic models tested. No ghost fallbacks. No TEXT narration between calls (model goes straight to action without explaining reasoning). Very fast: 8–9s per simple scenario.

**Failure mode on AC-003 (navigation):** same double-click loop as Anthropic models, but **without self-recovery**. Without chain-of-thought, the model cannot reason about state between calls. When the loop guard fires and injects a snapshot + corrective message, the model reads it and correctly calls `report_result` directly.

**Loop guard interaction (after fix):**
```
click [ref=e18]         ← executes, navigates to /produse
browser_snapshot({})    ← model takes snapshot, still sees [ref=e18] in nav
click [ref=e18]         ← BLOCKED by loop guard, fresh snapshot injected
report_result(pass)     ← model sees /produse snapshot, calls report_result
```

**Verdict quality:** minimal reasoning — `"actual": "Page title is X and at least one category is visible"`. Correct but terse. No subcategory enumeration.

**Cost note:** ~$0.05/run is comparable to Anthropic Haiku (~$0.056/run) but with less reliability and no self-recovery. Not recommended for production tiers.

#### Detailed analysis: Qwen 2.5 7B Turbo

**Behaviour:** mixed — some proper `CALL` tool calls (navigate, snapshot, click) but **never calls `report_result` as a proper tool call**. Verdicts always go through `_extract_verdict` fallback.

**Key failure patterns observed:**

1. **Hallucinated tool response format:** model generates `user <tool_response>` markers and Playwright-specific code (`await page.screenshot(...)`) that don't exist in qa-agent's stack. The model confuses qa-agent's tool-use framework with a different testing framework from its training data:
   ```
   TEXT  user <tool_response> ### Ran Playwright code
         ```js await page.screenshot({ path: 'page-2023-05-04T15-42-54-775Z.png' }); ```
   ```
   This is noise — the CALL tool calls still execute correctly, but the TEXT narration is meaningless and confusing.

2. **Never calls `report_result` directly:** after seeing a snapshot, the model writes a verdict in plain text (e.g. `"Since both conditions are met, I can conclude..."`) and stops. Matched by no Ghost fallback pattern. Falls to `_extract_verdict`.

3. **AC-003 false positive (caught by When-action guardrail):** model called `report_result(pass)` after seeing the homepage snapshot, claiming "products page is accessible and at least one category is visible" without having clicked the Produse link. Guardrail blocked it, forced the click.

4. **After guardrail — ref confusion:** model tried `browser_click({"target":"[ref=e18]"})` but reported the ref "not available in the current snapshot". Model could not complete the scenario.

**Assessment:** suitable for Free tier with acceptance that:
- All verdicts go through extractor (adds latency, small cost)
- Complex navigation scenarios (When actions) are fragile
- False positive risk exists without the When-action guardrail

However, Anthropic Haiku at $0.016/run more is significantly more reliable. Decision: use Haiku for Free tier (see BD-001).

---

### Provider selection summary

| Use case | Provider | Model |
|----------|----------|-------|
| SaaS Free tier | Anthropic | `claude-haiku-4-5-20251001` |
| SaaS Starter/Pro | Anthropic | `claude-sonnet-4-6` |
| BYOK (user's key) | Any | User's choice |
| Local development | Ollama | `mistral-small:22b` (see `docs/local-llms.md`) |
| Together.ai BYOK | Together.ai | `meta-llama/Llama-3.3-70B-Instruct-Turbo` (only reliable option) |

### Configuration

```bash
# Anthropic (default)
uv run qa-agent run specs/alconind-smoke

# Anthropic Haiku (Free tier config)
QA_EXECUTOR_MODEL=claude-haiku-4-5-20251001 \
uv run qa-agent run specs/alconind-smoke

# Together.ai Llama 70B
QA_EXECUTOR_PROVIDER=together_ai \
QA_EXECUTOR_MODEL=meta-llama/Llama-3.3-70B-Instruct-Turbo \
TOGETHER_API_KEY=<key> \
uv run qa-agent run specs/alconind-smoke

# Together.ai Qwen 7B (fragile, Free tier fallback)
QA_EXECUTOR_PROVIDER=together_ai \
QA_EXECUTOR_MODEL=Qwen/Qwen2.5-7B-Instruct-Turbo \
TOGETHER_API_KEY=<key> \
uv run qa-agent run specs/alconind-smoke
```
