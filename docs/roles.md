# Agent Roles

qa-agent uses four distinct roles, each with a specific responsibility, input/output contract, and model requirement. Roles are configured independently via environment variables, so each can run on a different provider and model.

---

## Role overview

```
[URL + description]
        │
        ▼
  ┌─────────────┐
  │  1. Analyst │  crawls site → writes .feature files + config.yaml
  └──────┬──────┘
         │  specs/<target>/
         ▼
  ┌─────────────┐
  │  2. Loader  │  parses .feature files → structured requirements  (no LLM)
  └──────┬──────┘
         │  list[Requirement]
         ▼
  ┌──────────────┐
  │  3. Executor │  browser loop: navigate → observe → act → report_result
  └──────┬───────┘
         │  list[TestResult]
         ▼
  ┌─────────────┐
  │  4. Reporter│  transforms results → markdown + JSON report
  └─────────────┘
```

---

## 1. Analyst

**File:** `src/qa_agent/analyst.py`
**Prompt:** `src/qa_agent/prompts/analyst_system.md`

### What it does

Autonomously explores a product site and generates Gherkin `.feature` files and `config.yaml` for the target product. Replaces the manual step of writing specs.

### Input

- Root URL of the product
- One-line product description
- Scenario ID prefix (e.g. `AC` → `AC-001`, `AC-002`, …)
- Output directory path

### Output

- `specs/<target>/*.feature` — one file per page/section
- `specs/<target>/config.yaml` — product configuration for the executor

### Flow

1. Navigate to root URL, take snapshot
2. Discover navigation links (nav bar, header, footer)
3. Visit each distinct page: navigate → snapshot → extract elements
4. Call `write_feature_file(filename, content)` once per page
5. Call `finish_analysis(summary, file_count)` when done

### Custom tools (Python-handled, not MCP)

| Tool | Purpose |
|------|---------|
| `write_feature_file(filename, content)` | Stages a file to be written to disk |
| `finish_analysis(summary, file_count)` | Signals completion; triggers flush to disk |

### Model requirements

| Requirement | Why |
|-------------|-----|
| **Strong instruction following** | Must generate valid Gherkin with correct ID/priority tags |
| **Large context window** | Processes multiple page snapshots across 20–50 turns |
| **Structured output reliability** | Must call `write_feature_file` correctly — plain-text output is discarded |
| **Cross-page reasoning** | Must decide coverage strategy across many pages without repetition |

### Recommended models

| Provider | Model | Notes |
|----------|-------|-------|
| **Anthropic** ✅ | `claude-opus-4-7` | **Default.** Best spec quality, handles any site complexity. ~$0.30–$0.60/analysis |
| Anthropic | `claude-sonnet-4-6` | 30% cheaper, slightly lower spec quality |
| Ollama | `qwen2.5:14b` | **Not recommended.** Reasoning saturation on dense pages; may miss pages or write incomplete specs |

### Configuration

```bash
# Default: Opus 4.7 via Anthropic
qa-agent analyze https://example.com --description "B2B SaaS dashboard" --prefix EX

# Override model
QA_ANALYST_PROVIDER=anthropic QA_ANALYST_MODEL=claude-sonnet-4-6 \
  qa-agent analyze https://example.com --description "..." --prefix EX

# Custom output directory
qa-agent analyze https://example.com -d "..." -p EX --output specs/my-product
```

### When to run

- **Once per new product** — output is committed to version control and reused
- **On major site redesign** — re-run to update specs when site structure changes significantly
- **Not in CI/CD** — analyst output is a one-time artifact, not a per-run operation

---

## 2. Loader (no LLM)

**File:** `src/qa_agent/specs/loader.py`

### What it does

Parses `.feature` files (Gherkin) and `config.yaml` from a spec directory into structured Python objects. No LLM involved — pure parsing.

### Input

`specs/<target>/` directory containing:
- One or more `.feature` files
- `config.yaml`

### Output

`SpecBundle` with:
- `config` — product name, URL per environment
- `requirements` — list of `Requirement` objects with id, title, given/when/then, priority

### Notes

- Gherkin is parsed for LLM interpretation, **not** for step-definition binding (no behave/pytest-bdd)
- IDs come from `@id:` tags; missing IDs get auto-generated slugs
- Files without `@id:` are still loaded; the executor gets the full scenario text

---

## 3. Executor

**File:** `src/qa_agent/agent.py`
**Prompt:** `src/qa_agent/prompts/executor_system.md`

### What it does

Runs a single test requirement via a browser tool-use loop. Navigates the target URL, observes the page via accessibility tree, performs actions (click, type, navigate), and emits a pass/fail verdict via `report_result`.

### Input

- Single `Requirement` (id, title, given, when, then, priority)
- Target URL
- `LLMConfig` for executor role

### Output

`TestResult` dict with:
- `status` — `"pass"` | `"fail"` | `"error"`
- `actual` — what was observed
- `reasoning` — explanation of verdict
- `actions_log` — sequence of tool calls made
- `duration_s`, `turns`, `provider`, `model`

### Flow

1. (Ollama only) Bootstrap: pre-navigate + pre-snapshot injected into message history
2. Tool-use loop (up to `MAX_TURNS=25`):
   - LLM calls browser tools (`browser_navigate`, `browser_snapshot`, `browser_click`, etc.)
   - When verdict is ready: LLM calls `report_result(status, actual, reasoning)`
3. Ghost fallback chain (A–G) catches tool calls emitted as plain JSON text

### Ghost fallbacks

Small models sometimes emit tool calls as JSON text in `message.content` instead of structured `tool_calls`. Seven fallback patterns (A–G) handle all observed variants:

| Fallback | Format | Observed in |
|----------|--------|-------------|
| A | `{"status":"…","actual":"…"}` | Any model |
| B | `{"type":"function","function":{"name":"…"}}` | qwen2.5:7b, 14b, llama3.1:8b |
| C | `{"function":"<name>","parameters":{…}}` | llama3.1:8b (`tool_choice=required`) |
| D | `{"type":"function","name":"<name>","parameters":{…}}` | llama3.1:8b |
| E | `{"<tool_name>":{…}}` | llama3.1:8b |
| F | `{"tool_calls":[{…}]}` | qwen2.5:14b |
| G | `{"name":"<tool>","args":{…}}` | qwen2.5:14b (turn exhaustion) |

### Model requirements

| Requirement | Why |
|-------------|-----|
| **Tool-calling reliability** | Must call `browser_*` tools and `report_result` — plain text is unacceptable |
| **Reasoning on accessibility trees** | Must synthesize a verdict from 50–200 node accessibility trees |
| **Low hallucination** | Must not invent element refs; must only act on what it sees in snapshots |
| **Follows step sequence** | Given → When → Then with no skipped steps |

### Recommended models

| Provider | Model | Site complexity | Notes |
|----------|-------|-----------------|-------|
| **Anthropic** ✅ | `claude-sonnet-4-6` | **Any** | **Default.** Handles all observed site complexities reliably |
| Anthropic | `claude-haiku-4-5` | Simple/medium | 5× cheaper; untested on dense pages — A/B test before adopting |
| Anthropic | `claude-opus-4-7` | Any | 3.5× more expensive than Sonnet; for mission-critical runs |
| Ollama | `qwen2.5:14b` | Simple only | Fails on dense pages (100+ nodes) — reasoning saturation |
| Ollama | `qwen2.5:7b` | Simple only | Stable with slim tools + bootstrap; limited reasoning |
| Ollama | `qwen2.5:32b` | ✗ | Not viable on M4 Pro — memory-bandwidth bottleneck |
| Ollama | `llama3.1:8b` | Simple only | Needs `QA_TOOL_CHOICE=required` + `QA_FORCE_SLIM=false` |

### Key configuration

```bash
# Default (Anthropic Sonnet)
qa-agent run specs/alconind

# Ollama local (simple sites only)
QA_EXECUTOR_PROVIDER=ollama QA_EXECUTOR_MODEL=qwen2.5:14b qa-agent run specs/alconind

# Slim tools (auto for Ollama, override with):
QA_FORCE_SLIM=true   # Force 8/21 tools
QA_FORCE_SLIM=false  # Force all 21 tools

# Bootstrap snapshot depth (Ollama only, default 5)
QA_BOOTSTRAP_DEPTH=3  # Reduce for very dense pages

# Per-call LLM timeout (seconds)
QA_LLM_TIMEOUT=60

# Soft timeout per test scenario (seconds, None = unbounded)
QA_TEST_TIMEOUT=180

# Debug turn-by-turn output
QA_DEBUG=1
```

---

## 4. Reporter

**File:** `src/qa_agent/reporter/report.py`
**Prompt:** `src/qa_agent/prompts/reporter_system.md`

### What it does

Transforms a list of `TestResult` dicts into a human-readable Markdown report and a machine-readable `report.json`. The Markdown is structured for easy consumption by a downstream fix-agent.

### Input

- `list[TestResult]` from the executor
- `SpecBundle` metadata (product name, URL, environment)
- Run directory path

### Output

- `reports/run-<ID>/report.md` — human-readable Markdown with summary table + per-result details
- `reports/run-<ID>/report.json` — structured JSON with same data

### Model requirements

| Requirement | Why |
|-------------|-----|
| **Instruction following** | Must format output per the template without hallucinating extra sections |
| **Low hallucination** | Must not invent reasoning or actions not present in the input JSON |
| **Conciseness** | PASS results need one line; FAIL results need structured detail |

**Reasoning ability is NOT required** — the reporter does template-driven text generation, not analysis.

### Recommended models

| Provider | Model | Notes |
|----------|-------|-------|
| Ollama ✅ | `qwen2.5:7b` | **Default.** Sufficient for templating. Runs locally at $0 cost |
| Anthropic | `claude-haiku-4-5` | Marginally better formatting; not worth the cost for this role |
| Anthropic | `claude-sonnet-4-6` | Overkill — avoid |

### Configuration

```bash
# Default: qwen2.5:7b via Ollama
# Override:
QA_REPORTER_PROVIDER=anthropic QA_REPORTER_MODEL=claude-haiku-4-5-20251001 qa-agent run specs/alconind
```

---

## Recommended setups

### Production (reliability-first)

```bash
# Analyst: Opus (once, on new product)
qa-agent analyze https://product.com -d "..." -p PR

# Run: Sonnet executor + Haiku planner (not yet a separate role) + qwen7b reporter
QA_EXECUTOR_PROVIDER=anthropic  QA_EXECUTOR_MODEL=claude-sonnet-4-6 \
QA_REPORTER_PROVIDER=ollama     QA_REPORTER_MODEL=qwen2.5:7b \
qa-agent run specs/product
```

**Cost:** ~$0.21/run (42 scenarios)

### Cost-optimized (validate before adopting)

```bash
QA_EXECUTOR_PROVIDER=anthropic  QA_EXECUTOR_MODEL=claude-haiku-4-5-20251001 \
QA_REPORTER_PROVIDER=ollama     QA_REPORTER_MODEL=qwen2.5:7b \
qa-agent run specs/product
```

**Cost:** ~$0.04/run — run A/B test against Sonnet on 5 scenarios before committing.

### Local-only (simple sites, zero API cost)

```bash
QA_EXECUTOR_PROVIDER=ollama QA_EXECUTOR_MODEL=qwen2.5:14b \
QA_REPORTER_PROVIDER=ollama QA_REPORTER_MODEL=qwen2.5:7b \
QA_BOOTSTRAP_DEPTH=3 \
qa-agent run specs/simple-site
```

**Viable for:** sites with <50 accessibility-tree nodes per page.
**Not viable for:** production marketing sites (alconind.ro class).

---

## Env var reference

| Variable | Roles | Default | Description |
|----------|-------|---------|-------------|
| `QA_PROVIDER` | all | `anthropic` | Fallback provider for all roles |
| `QA_ANALYST_PROVIDER` | analyst | `QA_PROVIDER` | Provider for analyst role |
| `QA_ANALYST_MODEL` | analyst | `claude-opus-4-7` | Model for analyst role |
| `QA_EXECUTOR_PROVIDER` | executor | `QA_PROVIDER` | Provider for executor role |
| `QA_EXECUTOR_MODEL` | executor | `claude-sonnet-4-6` | Model for executor role |
| `QA_REPORTER_PROVIDER` | reporter | `QA_PROVIDER` | Provider for reporter role |
| `QA_REPORTER_MODEL` | reporter | `claude-haiku-4-5` / `qwen2.5:7b` | Model for reporter role |
| `QA_LLM_TIMEOUT` | all | per-model | Per-call HTTP timeout (seconds) |
| `QA_TEST_TIMEOUT` | executor | per-model | Soft timeout per test scenario |
| `QA_FORCE_SLIM` | executor | auto | `true`=8 tools, `false`=21 tools, unset=auto |
| `QA_BOOTSTRAP_DEPTH` | executor | `5` | Accessibility tree depth for Ollama bootstrap |
| `QA_NO_BOOTSTRAP` | executor | unset | Set to `true` to disable bootstrap snapshot |
| `QA_TOOL_CHOICE` | executor | unset | Set to `required` for models that output test plans |
| `QA_DEBUG` | executor | unset | Set to `1` for turn-by-turn debug output |
| `OLLAMA_BASE_URL` | ollama roles | `http://localhost:11434` | Ollama server base URL |
