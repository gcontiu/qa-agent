"""
LLM abstraction layer via LiteLLM.
All providers (Anthropic, Ollama, vLLM, …) are called with OpenAI-compatible
format. LiteLLM converts to the target provider's format transparently.
"""
import os
import shutil
import subprocess
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
    "executor": {
        "anthropic": "claude-sonnet-4-6",
        "ollama":    "qwen2.5:7b",
    },
    "reporter": {
        "anthropic": "claude-haiku-4-5-20251001",
        "ollama":    "qwen2.5:7b",
    },
    "planner": {
        "anthropic": "claude-opus-4-7",
        "ollama":    "qwen2.5:32b",
    },
}


_LLM_TIMEOUT_DEFAULTS = {"ollama": 120, "anthropic": 30}


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
        default_timeout = _LLM_TIMEOUT_DEFAULTS.get(provider, 30)
        llm_timeout = int(os.getenv("QA_LLM_TIMEOUT", default_timeout))
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
            return {"api_base": self.base_url}
        return {}


def complete(
    config: LLMConfig,
    messages: list[dict],
    tools: list[dict] | None = None,
    max_tokens: int = 2048,
):
    """
    Unified LLM call. Returns a LiteLLM ModelResponse (OpenAI-compatible).
    messages must be in OpenAI format (role/content, tool role for results).
    tools must be in OpenAI function format.
    """
    kwargs: dict = dict(
        model=config.litellm_model(),
        messages=messages,
        max_tokens=max_tokens,
        timeout=config.llm_timeout,
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

    return litellm.completion(**kwargs)
