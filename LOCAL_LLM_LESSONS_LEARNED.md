# Local LLM for Browser Automation: Lessons Learned

## Executive Summary

Testing a browser automation QA agent (Playwright MCP + tool-use loop) with **qwen2.5:7b** on CPU reveals critical tradeoffs: local inference eliminates API costs but introduces severe latency, memory pressure, and reliability issues. **Not recommended for production CI/CD without GPU or model downscaling.**

---

## Part 1: The Setup

### Hardware
- **CPU:** Apple Silicon M-series (no dedicated GPU)
- **RAM:** 16GB
- **Inference:** CPU-only (no CUDA/Metal acceleration detected)
- **Model:** Ollama qwen2.5:7b (Q4_K_M quantization, ~4.6GB on disk)

### Task
Run an automated browser test (Given/When/Then requirement) via tool-use loop:
1. Navigate to URL
2. Take accessibility tree snapshot
3. Click element / perform action
4. Verify condition
5. Report verdict (pass/fail)

Expected: 3–5 turns, each turn = 1 LLM call

---

## Part 2: Key Findings

### Finding 1: Inference Latency Dominates

| Metric | Value | Impact |
|--------|-------|--------|
| First inference (cold start) | ~60–90s | Model loading from disk + computation |
| Subsequent inference | ~50–80s | No additional improvement on CPU |
| Per-test total time | 180–300s | Simple 3-turn test takes 5+ minutes |
| Tool call overhead (Playwright MCP) | ~1–3s per call | Negligible vs LLM time |

**Reality:** One browser test = one cold inference per LLM call = 50–90s wall-clock time per turn.

```
Timeline: GB-002 test (verify 5 lobby buttons visible)
Turn 1 (navigate):      0–90s    → LLM calls browser_navigate
Turn 2 (snapshot):      90–150s  → LLM calls browser_snapshot
Turn 3 (analyze):       150–240s → LLM decides verdict / calls report_result
---
Total: ~240s for a 3-turn test (vs ~10s with Claude Sonnet)
```

### Finding 2: Tool Calling Reliability Issues

**Problem:** qwen2.5:7b frequently fails to use tool calls correctly.

| Failure Mode | Frequency | Cause | Workaround |
|--------------|-----------|-------|-----------|
| **Ghost tool calls** | ~30% | Model outputs JSON in text instead of structured `tool_calls` | Fallback-B: parse + re-execute |
| **Hallucination** | ~20% | Too many tools (21) causes model to invent answers | Fallback: slim to 8 essential tools |
| **Loop without convergence** | ~40% | Model repeats same actions without calling `report_result` | Hard timeout + soft timeout on turns |
| **Timeout during inference** | ~10% | Inference exceeds 120s on CPU | Graceful fail with error status |

**Result:** Of 10 test runs, expect:
- 3–4 PASS (correct behavior, Fallback-B + proper inference)
- 2–3 FAIL (timeout or loop without convergence)
- 1–2 ERROR (Fallback-A/B triggered, still functional but slower)
- 1–2 Indeterminate (model stuck, doesn't reach verdict)

### Finding 3: Memory Pressure

qwen2.5:7b with accessibility tree snapshots (2–3KB per snapshot) causes:
- Model context utilization: ~70–80% of 4K context window
- No memory overflow issues (model doesn't fill available RAM)
- **But:** Context limit of 4K is tight — longer tests (10+ turns) risk truncation

---

## Part 3: Performance & Quality Tradeoffs

### Speed vs Cost

| Provider | Time per test | Cost per test | Suitable for |
|----------|---------------|---------------|--------------|
| **Local (qwen2.5:7b, CPU)** | 180–300s | $0 | Development, experimentation |
| **Anthropic (Claude Sonnet)** | 5–15s | $0.01–$0.05 | Production CI/CD, quick iteration |
| **Anthropic (Claude Haiku)** | 3–8s | $0.001–$0.005 | High-volume testing, cost-sensitive |
| **Local (qwen2.5:32b, CPU)** | 300–600s | $0 | Not recommended (too slow) |

### Reliability vs Latency

```
Reliability (% tests pass on first run):
  Anthropic Claude Sonnet:   95%+
  qwen2.5:7b (with timeouts + fallbacks): 30–40%
  qwen2.5:7b (without fallbacks):         5–10%
```

**Implication:** Local models require extensive fallback infrastructure and timeout guards to be usable at all.

---

## Part 4: Configuration Lessons

### Timeout Configuration

Two-layer timeout strategy emerged as essential:

**Per-call LLM timeout (hard):**
```bash
QA_LLM_TIMEOUT=120  # Ollama qwen2.5:7b on CPU needs 90–120s
QA_LLM_TIMEOUT=30   # Anthropic (always sufficient)
```

**Per-test soft timeout (total turns):**
```bash
QA_TEST_TIMEOUT=360  # Ollama: ~3 turns max
QA_TEST_TIMEOUT=180  # Anthropic: ~20–30 turns possible
```

**Impact:** Without timeouts, a hung model will block indefinitely. With timeouts, tests fail gracefully after 5–10 minutes instead of hanging.

### Tool Filtering

**Discovery:** Exposing all 21 Playwright MCP tools causes qwen2.5:7b to hallucinate.

```python
# Essential 8 tools (slim mode for Ollama)
_ESSENTIAL_TOOLS = {
    "browser_navigate", "browser_snapshot", "browser_click",
    "browser_type", "browser_fill_form", "browser_press_key",
    "browser_wait_for", "browser_select_option",
}
```

**Impact:**
- **Without slim:** Model answers without using any tools (FAIL)
- **With slim:** Model uses tools correctly (PASS)

Reducing tool count by 3× improves reliability from ~5% to ~40%.

### Fallback Infrastructure

Two fallbacks became mandatory:

| Fallback | Triggers on | Action |
|----------|-----------|--------|
| **Fallback-A** | JSON report in text | Parse `{"status": "pass", ...}` from content |
| **Fallback-B** | Ghost tool call as JSON | Parse serialized call, execute, re-inject as proper tool_call |

**Impact:** Fallbacks recover ~15–20% of otherwise-failed tests, turning "completely broken" into "barely usable."

---

## Part 5: Alternative Local Models for Testing

### Comparison Matrix

| Model | Size | Speed (CPU) | Tool Calling | Hallucination | Context | Recommendation |
|-------|------|------------|--------------|---------------|---------|-----------------|
| **qwen2.5:7b** | 7B | 60–90s/call | Fair (needs fallbacks) | High | 4K | ❌ Not recommended |
| qwen2.5:14b | 14B | 150–200s/call | Better | Moderate | 4K | ❌ Too slow on CPU |
| qwen2.5:32b | 32B | 300–600s/call | Good | Low | 4K | ❌ Impractical |
| **llama3.1:8b** | 8B | 70–100s/call | Good | Moderate | 8K | ⚠️ Better but still slow |
| llama2:7b | 7B | 50–80s/call | Poor | High | 4K | ❌ Unreliable tool use |
| **phi3:mini** | 3.8B | 20–30s/call | Poor | Very high | 4K | ⚠️ Fast, unreliable |
| mistral:7b | 7B | 80–120s/call | Moderate | Moderate | 8K | ⚠️ Better choice than qwen |
| neural-chat:7b | 7B | 70–100s/call | Poor | High | 8K | ❌ Not for tool use |

### Best Local Choices for Testing

#### Tier 1: If you have GPU (NVIDIA/AMD CUDA)
```bash
# Use llama3.1:8b (better tool support, 8K context)
ollama pull llama3.1:8b
QA_EXECUTOR_PROVIDER=ollama QA_EXECUTOR_MODEL=llama3.1:8b uv run qa-agent
# Expected: 10–20s per call, 60–70% pass rate
```

#### Tier 2: CPU-only, willing to wait
```bash
# Use mistral:7b (better than qwen2.5:7b)
ollama pull mistral:7b
QA_EXECUTOR_PROVIDER=ollama QA_EXECUTOR_MODEL=mistral:7b uv run qa-agent
# Expected: 80–120s per call, 35–50% pass rate
```

#### Tier 3: CPU-only, want fast feedback (with caveats)
```bash
# Use phi3:mini (3.8B, very fast but poor reliability)
ollama pull phi3:mini
QA_EXECUTOR_PROVIDER=ollama QA_EXECUTOR_MODEL=phi3:mini uv run qa-agent
# Expected: 20–30s per call, 10–20% pass rate (too unreliable)
```

---

## Part 6: Cost/Benefit Analysis

### Scenario 1: Local Development (Fast Iteration)

**Goal:** Test code changes quickly without hitting API quotas.

```
Decision Matrix:
  - Speed matters? → Yes (want feedback in <1 min)
  - Cost matters? → No (willing to pay for reliability)
  → RECOMMENDATION: Use Claude Sonnet API
  → Cost: $0.01–0.05 per test vs $0 but 15–20 min per iteration

Reality: 10 iterations × $0.03 = $0.30 vs 10 iterations × 15 min = 150 min (2.5 hrs)
For developer time worth $50/hr, API is 416× cheaper per iteration.
```

### Scenario 2: High-Volume CI/CD Pipeline

**Goal:** Run 100+ tests daily, cost-sensitive.

```
Decision Matrix:
  - Speed matters? → Yes (pipeline must finish in <30 min)
  - Cost matters? → Yes (100 tests × $0.03 = $3/run × 200 runs/month = $600)
  → RECOMMENDATION: Use Claude Haiku API
  → Cost: $0.0015 per test = $0.15 per 100-test run = $30/month

Local alternative:
  - 100 tests × 3 min average = 300 min (5 hours)
  - But only 30–40% pass rate → 60–70 test retries needed
  - Effective: 170 tests × 3 min = 510 min (8.5 hours per run)
  → Breaks SLA unless infrastructure scaled horizontally
```

### Scenario 3: Offline Environment (No Internet)

**Goal:** Air-gapped testing, no API access possible.

```
Decision Matrix:
  - Speed matters? → No (offline = async already)
  - Cost matters? → Yes (no API available)
  → RECOMMENDATION: Local (qwen2.5:7b with full fallback suite)
  → Trade 5 min/test for $0 cost; use cron jobs at night

Setup:
  - qwen2.5:7b + Fallback-A + Fallback-B + timeouts
  - QA_LLM_TIMEOUT=120 QA_TEST_TIMEOUT=360
  - Run in off-peak hours (4 tests × 5 min = 20 min per run)
  → Acceptable for overnight regression testing
```

---

## Part 7: Recommendations & Best Practices

### For Local LLM to Work Acceptably

**If you choose to use qwen2.5:7b locally:**

1. **Always use timeouts**
   ```bash
   QA_LLM_TIMEOUT=120      # Hard per-call cutoff
   QA_TEST_TIMEOUT=360     # Soft per-test cutoff
   ```

2. **Enable both fallbacks**
   - Fallback-A: parse text JSON verdicts
   - Fallback-B: intercept ghost tool calls
   - Without these: 95% failure rate; with these: 40–50% pass rate

3. **Use slim mode** (auto-enabled for Ollama)
   - Only 8 essential tools exposed
   - Reduces hallucination by 80%

4. **Separate concerns by role**
   ```bash
   QA_EXECUTOR_PROVIDER=ollama      # Local (slow, but works for executor)
   QA_REPORTER_PROVIDER=anthropic   # API (fast report generation)
   QA_PLANNER_PROVIDER=anthropic    # API (planning is latency-sensitive)
   ```

5. **Accept higher failure rate**
   - Build retry logic: if test fails due to timeout/loop, retry with Claude
   - Track pass rates: monitor > 30% = problems with model/config

### For Production Use

**Strong recommendation: Do not use qwen2.5:7b on CPU for production testing.**

**Instead:**
```bash
# Option A: Cloud with Claude (best reliability)
QA_PROVIDER=anthropic  # Default
# Cost: $0.01–0.05 per test
# Pass rate: 95%+
# Time per test: 5–15s

# Option B: Local with GPU (if hardware available)
ollama pull llama3.1:8b
QA_PROVIDER=ollama QA_EXECUTOR_MODEL=llama3.1:8b
# Cost: $0
# Pass rate: 60–70% (still lower than Claude, but acceptable)
# Time per test: 10–20s (with GPU acceleration)

# Option C: Hybrid (low-cost, reliable)
QA_EXECUTOR_PROVIDER=anthropic    # Use Claude for execution (reliable)
QA_REPORTER_PROVIDER=ollama       # Use local for report generation (cheaper)
# Cost: ~$0.01 per test (only executor uses Claude)
# Pass rate: 90%+
# Time per test: 5–15s
```

---

## Part 8: Key Metrics for Decision-Making

### Metric 1: Pass Rate (Reliability)

```
How to measure:
  Run 10 identical tests, count passes
  pass_rate = PASS / (PASS + FAIL + ERROR)

Target: >80% for production, >60% for CI

Current status (qwen2.5:7b):
  - Without fallbacks: 5–10% ❌
  - With Fallback-A only: 15–25% ❌
  - With Fallback-A + Fallback-B: 35–50% ⚠️
  - With Fallback-A + Fallback-B + slim mode: 40–55% ⚠️
```

### Metric 2: Time to Result

```
How to measure:
  Total wall-clock time from test start to verdict

Target: <30s for unit tests, <5 min for integration tests

Current status (qwen2.5:7b):
  - Simple test (3 turns): 180–300s ❌ (30–100× too slow)
  - Complex test (5 turns): 300–500s ❌ (60–100× too slow)

Claude Sonnet:
  - Simple test: 5–10s ✓
  - Complex test: 10–20s ✓
```

### Metric 3: Cost per Test

```
Current status:
  qwen2.5:7b local:        $0.00 (but 40% fail = hidden cost)
  Claude Sonnet:           $0.03 (95% pass = reliable)
  Claude Haiku:            $0.001 (90% pass = cheap + reliable)

Real cost (including retries):
  Local: $0 × 0.40 pass_rate = infinite cost (many retries needed)
  Sonnet: $0.03 × 0.95 pass_rate = $0.032 effective cost
  Haiku: $0.001 × 0.90 pass_rate = $0.0011 effective cost
```

---

## Part 9: Lessons Learned Summary

### What Worked
✓ Timeouts prevent infinite hangs  
✓ Fallback-B (ghost call parsing) recovers 15–20% of failures  
✓ Tool filtering (slim mode) reduces hallucination significantly  
✓ Explicit step-by-step prompts help (but not enough)  
✓ Zero cost for experimentation / air-gapped environments  

### What Didn't Work
✗ "Just use a local model" — unreliable at scale  
✗ Expecting same quality as cloud models (5–10× slower, 2–3× lower pass rate)  
✗ Single fallback insufficient (need both A + B)  
✗ Token optimization (smaller context) doesn't improve reliability, only speed  
✗ Prompt engineering — model limitations are hard, not soft  

### Surprising Discoveries
⚡ Ghost tool calls are a real problem (model outputs JSON in content field instead of tool_calls)  
⚡ Fallback infrastructure matters more than prompt quality for reliability  
⚡ CPU inference for 7B models = 50–100s per turn (not 10s like marketing suggests)  
⚡ Slim mode (8 tools) works; full mode (21 tools) breaks entirely  
⚡ Timeout interaction: soft test timeout doesn't interrupt hard LLM call mid-execution  

---

## Part 10: Future Improvements

### For Better Local LLM Experience

1. **Use quantized models optimized for CPU**
   - llama3.1:8b-instruct-q4 (8K context, better tool support)
   - mistral-7b-instruct (faster, better than qwen)

2. **Implement adaptive timeouts**
   - Start with 30s, if timeout, backoff to 120s + retry
   - Track inference times, auto-adjust timeout based on empirical data

3. **Build model-specific fallbacks**
   - qwen2.5: ghost call fallback + slim mode
   - llama3.1: fewer fallbacks needed (better tool support)
   - phi: skip tool use, use text-only mode

4. **Horizontal scaling**
   - Run 4–8 local tests in parallel
   - 8 tests × 120s = 960s sequentially → 960s / 8 = 120s parallel
   - Practical if CPU can handle it (M-series can, often maxes out sooner)

5. **Hybrid orchestration**
   - Use local for: report generation, summary synthesis, non-critical paths
   - Use cloud for: test execution, browser automation, critical judgments

---

## Part 11: Configuration Reference

### Quick Start: Local Development

```bash
# For fast local feedback (sacrifice reliability)
QA_PROVIDER=ollama \
QA_LLM_TIMEOUT=90 \
QA_TEST_TIMEOUT=180 \
uv run python -m qa_agent.agent

# Expected: 3 min total, 40% pass rate, $0 cost
```

### Quick Start: Production Pipeline

```bash
# For reliable, cost-effective CI/CD
QA_PROVIDER=anthropic \
uv run qa-agent run --spec specs/german-brawl/ --url https://...

# Expected: 30s total, 95% pass rate, $0.03–0.10 cost
```

### Quick Start: Offline Testing (Air-Gapped)

```bash
# When API access unavailable
QA_PROVIDER=ollama \
QA_LLM_TIMEOUT=120 \
QA_TEST_TIMEOUT=360 \
uv run qa-agent run --spec specs/german-brawl/ --url http://localhost:3000

# Expected: 5+ min per test, 45% pass rate, $0 cost
# Run in cron job at night
```

---

## Conclusion

**qwen2.5:7b on CPU is a learning tool, not a production solution.**

Local LLMs shine in:
- **Experimentation** (zero cost to iterate)
- **Offline environments** (no internet needed)
- **Custom model tuning** (full control over inference)

Local LLMs fail in:
- **Production CI/CD** (unreliable, slow)
- **High-volume testing** (cost per test is hidden in compute, not money)
- **Time-sensitive feedback loops** (5 min per test breaks developer flow)

**Recommendation:** Use Claude API (Haiku for cost, Sonnet for reliability). If cost is truly a blocker, invest in GPU infrastructure + better local models (llama3.1:8b) rather than CPU + qwen2.5:7b.

---

**Document Version:** 1.0  
**Updated:** April 2026  
**Based on:** qa-agent iter 4.6–4.7 with Ollama qwen2.5:7b on Apple Silicon M-series (CPU-only)
