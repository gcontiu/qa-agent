# Playwright MCP tools — catalogue

All 21 tools exposed by `@playwright/mcp` over the MCP protocol.
`agent.py` calls them via `session.call_tool(name, args)`. The LLM never calls
them directly — it outputs a tool name + arguments (structured `tool_calls` or
a ghost JSON), and `agent.py` executes them.

Tools are grouped by how critical they are for automated QA testing.

---

## Tier 1 — Essentials (slim mode, always loaded)

These 8 tools cover ~90% of web testing scenarios. Active by default for all
Ollama models (`_ESSENTIAL_TOOLS` in `agent.py`). Loading more tools than this
causes hallucination and invented tool names in small/medium models.

| Tool | Params | What it does |
|------|--------|--------------|
| `browser_navigate` | `url` | Open a URL in headless Chromium. Starting point for every test. |
| `browser_snapshot` | `filename`, `depth` | Return the page accessibility tree as structured text with element refs (`e32`, `e77`, …). The primary way the LLM "sees" the page — cheaper and more useful than screenshots. |
| `browser_click` | `element`, `ref`, `doubleClick`, `button`, `modifiers` | Click an element by ref. `doubleClick` for double-click; `button` for right/middle; `modifiers` for Ctrl+click etc. |
| `browser_type` | `element`, `ref`, `text`, `submit`, `slowly` | Type text into a focused input. `submit=true` presses Enter after. `slowly=true` types character by character (useful for autocomplete triggers). |
| `browser_fill_form` | `fields` | Fill multiple form fields in one call. More efficient than multiple `browser_type` calls. |
| `browser_press_key` | `key` | Send a keyboard event (`Enter`, `Escape`, `Tab`, arrow keys, etc.). |
| `browser_wait_for` | `time`, `text`, `textGone` | Wait for a text string to appear, disappear, or a fixed duration (ms). Essential for async state changes (loading spinners, queue screens). |
| `browser_select_option` | `element`, `ref`, `values` | Select one or more options in a `<select>` dropdown. |

---

## Tier 2 — Important (add for specific scenarios)

Not in slim mode by default. Add individually to `_ESSENTIAL_TOOLS` when a
spec requires them — do not enable full mode (21 tools).

| Tool | Params | What it does | When you need it |
|------|--------|--------------|-----------------|
| `browser_hover` | `element`, `ref` | Hover over an element without clicking. | Tooltips, dropdown menus that open on hover, CSS `:hover` states. |
| `browser_handle_dialog` | `accept`, `promptText` | Accept or dismiss a browser-native dialog (`alert`, `confirm`, `prompt`). | Any flow that triggers JS dialogs (delete confirmations, logout warnings). |
| `browser_navigate_back` | — | Navigate to the previous page (browser Back). | Multi-step flows where the test needs to return to a previous state. |
| `browser_file_upload` | `paths` | Upload one or more files via a file input. | File upload forms, avatar pickers, document upload flows. |
| `browser_drag` | `startElement`, `startRef`, `endElement`, `endRef` | Drag one element and drop it onto another. | Kanban boards, sortable lists, canvas interactions. |

---

## Tier 3 — Diagnostic (debugging and evidence collection)

Useful for understanding failures but not for test execution logic.
Models should not call these as part of the happy path.

| Tool | Params | What it does | When you need it |
|------|--------|--------------|-----------------|
| `browser_console_messages` | `level`, `all`, `filename` | Return all JS console messages (errors, warnings, logs). | Detecting JS errors that don't surface in the UI; verifying analytics events. |
| `browser_network_requests` | `static`, `requestBody`, `requestHeaders`, `filter`, `filename` | Return all HTTP requests made since page load. | API contract testing; verifying the right endpoint was called with the right payload. |
| `browser_take_screenshot` | `type`, `filename`, `element`, `ref`, `fullPage` | Capture a visual screenshot. **Cannot be used for element refs** — use `browser_snapshot` for actions. | Human-readable evidence in reports; visual regression comparison. |

---

## Tier 4 — Power tools (advanced / escape hatch)

Powerful but dangerous — can produce non-deterministic behaviour if misused.
Use only when Tier 1–3 tools are insufficient.

| Tool | Params | What it does | When you need it |
|------|--------|--------------|-----------------|
| `browser_evaluate` | `function`, `element`, `ref`, `filename` | Execute an arbitrary JavaScript expression on the page or on a specific element. Returns the result. | Reading values not exposed in the accessibility tree; triggering JS-only state changes; injecting test data. |
| `browser_run_code` | `code`, `filename` | Execute a full Playwright code snippet (multi-step, async). | Complex interactions that require Playwright's full API; flows that need precise timing control. |
| `browser_tabs` | `action`, `index` | List, create, close, or switch between browser tabs. | Flows that open new tabs (OAuth popups, PDF previews, external links). |

---

## Tier 5 — Utility (rarely needed)

| Tool | Params | What it does |
|------|--------|--------------|
| `browser_resize` | `width`, `height` | Resize the browser window. Useful for responsive layout tests. |
| `browser_close` | — | Explicitly close the current page. Rarely needed — Playwright MCP closes the session automatically. |

---

## How to add a tool to slim mode

Edit `_ESSENTIAL_TOOLS` in `src/qa_agent/agent.py`:

```python
_ESSENTIAL_TOOLS = {
    "browser_navigate", "browser_snapshot", "browser_click",
    "browser_type", "browser_fill_form", "browser_press_key",
    "browser_wait_for", "browser_select_option",
    "browser_hover",        # ← add here if your spec needs hover
    "browser_handle_dialog", # ← add here if your spec has JS dialogs
}
```

**Rule:** add the minimum set needed for the spec being tested. Never enable
full mode (`QA_FORCE_SLIM=false`) for Ollama — tested models (qwen2.5:7b,
qwen2.5:14b) hallucinate tool names when exposed to all 21 tools.
