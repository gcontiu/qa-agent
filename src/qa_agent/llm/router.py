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
# Default models per role
# ---------------------------------------------------------------------------

_DEFAULTS = {
    "analyst": {
        "anthropic": "claude-opus-4-7",        # needs strong reasoning to synthesize spec structure
        "ollama":    "qwen2.5:14b",            # not recommended; reasoning saturation on dense pages
    },
    "executor": {
        "anthropic": "claude-sonnet-4-6",
        "ollama":    "qwen2.5:7b",
    },
    "extractor": {
        # Verdict extraction: simple classification task, cheapest capable model per provider.
        # Defaults to the same provider as executor (via QA_PROVIDER fallback), so a purely
        # local run stays local and a purely Anthropic run stays Anthropic.
        # Override with QA_EXTRACTOR_PROVIDER / QA_EXTRACTOR_MODEL to decouple.
        "anthropic": "claude-haiku-4-5-20251001",
        "ollama":    "qwen2.5:7b",
    },
}


# Per-model timeout defaults. Ollama entries are keyed by model name;
# "__default__" covers any model not explicitly listed.
_LLM_TIMEOUT_DEFAULTS: dict = {
    "anthropic": 30,
    "ollama": {
        "qwen2.5:14b":      90,   # ~23s/turn on M4 Pro GPU
        "qwen2.5:32b":      150,  # larger model, longer inference on M4 Pro
        "mistral-small:22b": 300, # 12GB + large KV cache saturates M4 Pro bandwidth; first post-snapshot call is slow
        "__default__":      120,  # qwen2.5:7b, llama3.1:8b, CPU inference
    },
}

_TEST_TIMEOUT_DEFAULTS: dict = {
    "anthropic": None,
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


def complete(
    config: LLMConfig,
    messages: list[dict],
    tools: list[dict] | None = None,
    max_tokens: int = 2048,
    response_format: dict | None = None,
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
    kwargs: dict = dict(
        model=config.litellm_model(),
        messages=messages,
        max_tokens=max_tokens,
        timeout=config.llm_timeout,
        temperature=float(os.getenv("QA_TEMPERATURE", "0")),
        **config.extra_kwargs(),
    )
    if tools:
        kwargs["tools"] = tools
        # tool_choice is opt-in via QA_TOOL_CHOICE=required.
        # "required" helps models that output test plans instead of tool calls (e.g. llama3.1:8b).
        # Do NOT enable by default: qwen2.5:7b regresses (loops on browser_snapshot forever).
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
