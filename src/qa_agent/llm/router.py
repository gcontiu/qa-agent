"""
LLM abstraction layer via LiteLLM.
All providers (Anthropic, Ollama, vLLM, …) are called with OpenAI-compatible
format. LiteLLM converts to the target provider's format transparently.
"""
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field

import litellm

# Silence LiteLLM's verbose logging
litellm.suppress_debug_info = True
os.environ.setdefault("LITELLM_LOG", "ERROR")

# ---------------------------------------------------------------------------
# Local-provider auto-start registry
# Each entry describes how to health-check and launch a locally-hosted LLM.
# Remote APIs (anthropic, openai, …) are NOT listed here — nothing to start.
# ---------------------------------------------------------------------------

_LOCAL_PROVIDERS: dict[str, dict] = {
    # Ollama: `ollama serve` listens on base_url (default :11434)
    "ollama": {
        "cmd_candidates": [
            "ollama",                                               # PATH
            "/usr/local/bin/ollama",                               # manual install
            "/opt/homebrew/bin/ollama",                            # Homebrew
            "/Applications/Ollama.app/Contents/Resources/ollama",  # macOS app bundle
        ],
        "start_args": ["serve"],
        "health_path": "",          # GET base_url/ → "Ollama is running"
        "ready_timeout": 20,
    },
    # vLLM: `vllm serve <model>` exposes OpenAI-compat API on base_url
    "vllm": {
        "cmd_candidates": ["vllm", "/usr/local/bin/vllm"],
        "start_args": ["serve"],
        "health_path": "/health",
        "ready_timeout": 60,
    },
    # LM Studio server mode
    "lmstudio": {
        "cmd_candidates": [
            "lmstudio",
            "/usr/local/bin/lmstudio",
            "/Applications/LM Studio.app/Contents/MacOS/LM Studio",
        ],
        "start_args": ["server", "start"],
        "health_path": "/v1/models",
        "ready_timeout": 30,
    },
}


def _resolve_executable(candidates: list[str]) -> str | None:
    """Return the first candidate that exists and is executable."""
    for c in candidates:
        resolved = shutil.which(c)
        if resolved:
            return resolved
        if os.path.isfile(c) and os.access(c, os.X_OK):
            return c
    return None


def _reachable(url: str) -> bool:
    try:
        urllib.request.urlopen(url, timeout=2)
        return True
    except Exception:
        return False


def ensure_provider_running(config: "LLMConfig") -> None:
    """Start the configured local LLM provider if it is not already reachable.

    No-op for remote API providers (anthropic, openai, …).
    Raises RuntimeError if the provider cannot be found or fails to start.
    """
    spec = _LOCAL_PROVIDERS.get(config.provider)
    if not spec:
        return  # remote API — nothing to start

    health_url = config.base_url.rstrip("/") + spec["health_path"]
    if _reachable(health_url):
        return

    exe = _resolve_executable(spec["cmd_candidates"])
    if not exe:
        raise RuntimeError(
            f"Cannot find {config.provider} executable. "
            f"Tried: {spec['cmd_candidates']}"
        )

    cmd = [exe] + spec["start_args"]
    print(f"[qa-agent] {config.provider} not running — starting '{' '.join(cmd)}'…")
    subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    deadline = time.monotonic() + spec["ready_timeout"]
    while time.monotonic() < deadline:
        if _reachable(health_url):
            print(f"[qa-agent] {config.provider} is ready.")
            return
        time.sleep(0.5)

    raise RuntimeError(
        f"{config.provider} did not become reachable at {health_url} "
        f"within {spec['ready_timeout']}s"
    )


# ---------------------------------------------------------------------------
# Pricing (USD per million tokens) — Anthropic models as of 2026-05
# ---------------------------------------------------------------------------

_PRICING: dict[str, tuple[float, float, float, float]] = {
    # model: (input, output, cache_write, cache_read)
    "claude-haiku-4-5-20251001": (0.80,  4.00,  1.00, 0.08),
    "claude-sonnet-4-6":         (3.00,  15.00, 3.75, 0.30),
    "claude-opus-4-7":           (15.00, 75.00, 18.75, 1.50),
}


def estimate_cost(model: str, usage: dict) -> float | None:
    """Return estimated USD cost from a usage accumulator dict, or None if unknown model."""
    p = _PRICING.get(model)
    if not p:
        return None
    inp, out, cw, cr = p
    # Billed input = regular input (not cached) = total input - cache writes - cache reads
    regular_input = (
        usage.get("input_tokens", 0)
        - usage.get("cache_write_tokens", 0)
        - usage.get("cache_read_tokens", 0)
    )
    return (
        max(regular_input, 0) * inp / 1_000_000
        + usage.get("output_tokens", 0) * out / 1_000_000
        + usage.get("cache_write_tokens", 0) * cw / 1_000_000
        + usage.get("cache_read_tokens", 0) * cr / 1_000_000
    )


# ---------------------------------------------------------------------------
# Default models per role
# ---------------------------------------------------------------------------

_DEFAULTS = {
    "analyst": {
        "anthropic":   "claude-opus-4-7",
        "ollama":      "qwen2.5:14b",             # not recommended; reasoning saturation on dense pages
        "together_ai": "meta-llama/Llama-3.3-70B-Instruct-Turbo",
    },
    "executor": {
        "anthropic":   "claude-sonnet-4-6",
        "ollama":      "qwen2.5:7b",
        "together_ai": "meta-llama/Llama-3.3-70B-Instruct-Turbo",  # Starter tier
    },
    "extractor": {
        # Verdict extraction: simple classification task, cheapest capable model per provider.
        # Defaults to the same provider as executor (via QA_PROVIDER fallback), so a purely
        # local run stays local and a purely remote run stays remote.
        # Override with QA_EXTRACTOR_PROVIDER / QA_EXTRACTOR_MODEL to decouple.
        "anthropic":   "claude-haiku-4-5-20251001",
        "ollama":      "qwen2.5:7b",
        "together_ai": "Qwen/Qwen2.5-7B-Instruct-Turbo",           # cheap + fast for classification
    },
}


# Per-model timeout defaults. Ollama entries are keyed by model name;
# "__default__" covers any model not explicitly listed.
_LLM_TIMEOUT_DEFAULTS: dict = {
    "anthropic": {
        "claude-opus-4-7": 120,  # Opus needs more time on long analyst conversations
        "__default__": 30,
    },
    "together_ai": {
        "meta-llama/Llama-3.3-70B-Instruct-Turbo": 60,  # cloud GPU, ~5-10s/turn
        "__default__": 30,                               # smaller models even faster
    },
    "ollama": {
        "qwen2.5:14b":       90,   # ~23s/turn on M4 Pro GPU
        "qwen2.5:32b":      150,   # larger model, longer inference on M4 Pro
        "mistral-small:22b": 300,  # 12GB + large KV cache saturates M4 Pro bandwidth
        "__default__":       120,  # qwen2.5:7b, llama3.1:8b, CPU inference
    },
}

_TEST_TIMEOUT_DEFAULTS: dict = {
    "anthropic":   None,
    "together_ai": None,  # cloud inference — no per-test cap needed
    "ollama": {
        "qwen2.5:14b": 180,  # 23s/turn × ~8 turns max on M4 Pro
        "qwen2.5:32b": 600,  # larger model, slower inference
        "__default__": 360,  # qwen2.5:7b on CPU: ~60s/turn × 6 turns
    },
}


# Rate-limit retry defaults (provider-agnostic: Anthropic, Together.ai, etc.)
# Override: QA_RATE_LIMIT_RETRIES, QA_RATE_LIMIT_WAIT
_RATE_LIMIT_MAX_RETRIES = 2   # attempts after the first failure
_RATE_LIMIT_WAIT_BASE   = 60  # seconds before retry 1; doubles for retry 2


def _resolve_timeout(defaults: dict, provider: str, model: str) -> int | None:
    """Resolve a timeout from a provider/model-keyed defaults dict."""
    val = defaults.get(provider)
    if isinstance(val, dict):
        return val.get(model, val.get("__default__", 30))
    return val


@dataclass
class LLMConfig:
    provider: str = "anthropic"      # anthropic | ollama | openai | …
    model: str | None = None         # overrides the default for the role
    base_url: str = "http://localhost:11434"  # Ollama default
    role: str = "executor"
    llm_timeout: int = 30            # per-call HTTP timeout in seconds (QA_LLM_TIMEOUT)
    force_slim: bool | None = None   # True=slim mode, False=full tools, None=auto (QA_FORCE_SLIM)

    @classmethod
    def from_env(cls, role: str = "executor") -> "LLMConfig":
        """Build config from QA_<ROLE>_PROVIDER / QA_<ROLE>_MODEL env vars."""
        prefix = f"QA_{role.upper()}_"
        provider = os.getenv(f"{prefix}PROVIDER", os.getenv("QA_PROVIDER", "anthropic"))
        model = os.getenv(f"{prefix}MODEL", os.getenv("QA_MODEL"))
        base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        resolved_model = model or _DEFAULTS.get(role, {}).get(provider, "")
        default_llm_timeout = _resolve_timeout(_LLM_TIMEOUT_DEFAULTS, provider, resolved_model) or 30
        llm_timeout = int(os.getenv("QA_LLM_TIMEOUT", default_llm_timeout))
        # force_slim: None=auto (based on provider), True=always slim, False=always full
        force_slim_str = os.getenv("QA_FORCE_SLIM", "").lower()
        force_slim = {"true": True, "false": False}.get(force_slim_str, None)
        return cls(
            provider=provider,
            model=model,
            base_url=base_url,
            role=role,
            llm_timeout=llm_timeout,
            force_slim=force_slim,
        )

    def resolved_model(self) -> str:
        if self.model:
            return self.model
        return _DEFAULTS.get(self.role, {}).get(self.provider, "claude-sonnet-4-6")

    def litellm_model(self) -> str:
        m = self.resolved_model()
        if self.provider == "anthropic":
            return m if m.startswith("claude") else f"anthropic/{m}"
        if self.provider == "ollama":
            return f"ollama/{m}"
        if self.provider == "together_ai":
            return f"together_ai/{m}"
        return m

    def extra_kwargs(self) -> dict:
        if self.provider == "ollama":
            # Ollama defaults to 4096 num_ctx which is far too small for browser snapshots
            # + system prompt + tool definitions. Pass explicitly; override via QA_NUM_CTX.
            # temperature/seed/top_k make runs deterministic; override via QA_TEMPERATURE / QA_SEED.
            num_ctx = int(os.getenv("QA_NUM_CTX", 8192))
            seed = int(os.getenv("QA_SEED", 42))
            return {
                "api_base": self.base_url,
                "extra_body": {"options": {
                    "num_ctx": num_ctx,
                    "temperature": 0,
                    "top_p": 1,
                    "top_k": 1,
                    "seed": seed,
                }},
            }
        return {}


def _verbose_log(config: "LLMConfig", response) -> None:
    """Log each LLM turn to stderr when QA_VERBOSE_LLM=true."""
    import sys
    label = f"[{config.resolved_model()}:{config.role}]"
    msg = response.choices[0].message
    if msg.tool_calls:
        for tc in msg.tool_calls:
            args = tc.function.arguments.replace("\n", " ")[:200]
            print(f"{label} CALL  {tc.function.name}({args})", file=sys.stderr, flush=True)
    if msg.content:
        content = str(msg.content).replace("\n", " ")[:400]
        print(f"{label} TEXT  {content}", file=sys.stderr, flush=True)


def _apply_anthropic_cache_control(
    messages: list[dict], tools: list[dict] | None
) -> tuple[list[dict], list[dict] | None]:
    """Mark the system prompt and tool definitions as Anthropic cache breakpoints.

    Cache writes cost 1.25× input; cache reads cost 0.1×. For a 4-turn scenario
    the static 9K (system + 23 tools) drops from ~36K re-billed inputs to ~12K.
    Across back-to-back scenarios within the 5-min TTL it improves further.

    Returns new lists — does not mutate caller data.
    """
    messages = list(messages)

    # First system message: convert plain string to content-array with cache marker.
    for i, msg in enumerate(messages):
        if msg.get("role") == "system":
            content = msg.get("content", "")
            if isinstance(content, str):
                messages[i] = {
                    **msg,
                    "content": [{"type": "text", "text": content,
                                 "cache_control": {"type": "ephemeral"}}],
                }
            elif isinstance(content, list) and content:
                # Already an array; add cache marker to last block if missing.
                if "cache_control" not in content[-1]:
                    content = list(content)
                    content[-1] = {**content[-1], "cache_control": {"type": "ephemeral"}}
                    messages[i] = {**msg, "content": content}
            break

    # Last tool definition: marks the end of the tool-list cache block.
    if tools:
        tools = list(tools)
        last = dict(tools[-1])
        last["cache_control"] = {"type": "ephemeral"}
        tools[-1] = last

    return messages, tools


def complete(
    config: LLMConfig,
    messages: list[dict],
    tools: list[dict] | None = None,
    max_tokens: int = 2048,
    response_format: dict | None = None,
    tool_choice: str | dict | None = None,
    _usage: dict | None = None,
):
    """
    Unified LLM call. Returns a LiteLLM ModelResponse (OpenAI-compatible).
    messages must be in OpenAI format (role/content, tool role for results).
    tools must be in OpenAI function format.
    response_format: optional structured output spec, e.g. {"type": "json_object"}.
      LiteLLM translates to the target provider's native format transparently:
      - Anthropic → structured output / tool with schema
      - Ollama    → {"format": "json"} in the request body
      - OpenAI / Together.ai → passed through as-is
    """
    if config.provider == "anthropic":
        messages, tools = _apply_anthropic_cache_control(messages, tools)

    # These Anthropic models have deprecated the temperature parameter entirely.
    # All other models (including haiku, sonnet) still accept it for determinism.
    _TEMPERATURE_DEPRECATED = {"claude-opus-4-7"}

    _temp_env = os.getenv("QA_TEMPERATURE")
    _skip_temp = (
        config.provider == "anthropic"
        and config.resolved_model() in _TEMPERATURE_DEPRECATED
        and _temp_env is None  # honour explicit override even on deprecated models
    )
    kwargs: dict = dict(
        model=config.litellm_model(),
        messages=messages,
        max_tokens=max_tokens,
        timeout=config.llm_timeout,
        **config.extra_kwargs(),
    )
    if not _skip_temp:
        kwargs["temperature"] = float(_temp_env or "0")
    if tools:
        kwargs["tools"] = tools
        # Per-call override takes precedence over the QA_TOOL_CHOICE env var.
        # tool_choice="required" forces the model to call one of the provided tools —
        # used by single-shot verdict to guarantee a structured report_result call.
        if tool_choice is not None:
            kwargs["tool_choice"] = tool_choice
        else:
            # QA_TOOL_CHOICE=required helps models that output test plans instead of
            # tool calls (e.g. llama3.1:8b). Not default: qwen2.5:7b loops forever with it.
            tc = os.getenv("QA_TOOL_CHOICE", "").lower()
            if tc == "required":
                kwargs["tool_choice"] = "required"

    if response_format:
        kwargs["response_format"] = response_format

    max_retries = int(os.getenv("QA_RATE_LIMIT_RETRIES", _RATE_LIMIT_MAX_RETRIES))
    wait_base   = int(os.getenv("QA_RATE_LIMIT_WAIT",    _RATE_LIMIT_WAIT_BASE))

    for attempt in range(max_retries + 1):
        try:
            response = litellm.completion(**kwargs)
            if os.getenv("QA_VERBOSE_LLM", "").lower() in ("1", "true"):
                _verbose_log(config, response)
            if _usage is not None and hasattr(response, "usage") and response.usage:
                u = response.usage
                _usage["input_tokens"] = (
                    _usage.get("input_tokens", 0) + getattr(u, "prompt_tokens", 0)
                )
                _usage["output_tokens"] = (
                    _usage.get("output_tokens", 0) + getattr(u, "completion_tokens", 0)
                )
                _usage["cache_write_tokens"] = (
                    _usage.get("cache_write_tokens", 0)
                    + getattr(u, "cache_creation_input_tokens", 0)
                )
                _usage["cache_read_tokens"] = (
                    _usage.get("cache_read_tokens", 0)
                    + getattr(u, "cache_read_input_tokens", 0)
                )
            return response
        except litellm.RateLimitError:
            if attempt >= max_retries:
                raise
            wait = wait_base * (attempt + 1)
            print(
                f"[qa-agent] RateLimitError — waiting {wait}s before retry "
                f"{attempt + 1}/{max_retries} ({config.provider}/{config.resolved_model()})...",
                file=sys.stderr, flush=True,
            )
            time.sleep(wait)
