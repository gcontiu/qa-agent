"""
LLM abstraction layer via LiteLLM.
All providers (Anthropic, Ollama, vLLM, …) are called with OpenAI-compatible
format. LiteLLM converts to the target provider's format transparently.
"""
import os
from dataclasses import dataclass, field

import litellm

# Silence LiteLLM's verbose logging
litellm.suppress_debug_info = True
os.environ.setdefault("LITELLM_LOG", "ERROR")

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

    @classmethod
    def from_env(cls, role: str = "executor") -> "LLMConfig":
        """Build config from QA_<ROLE>_PROVIDER / QA_<ROLE>_MODEL env vars."""
        prefix = f"QA_{role.upper()}_"
        provider = os.getenv(f"{prefix}PROVIDER", os.getenv("QA_PROVIDER", "anthropic"))
        model = os.getenv(f"{prefix}MODEL", os.getenv("QA_MODEL"))
        base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        default_timeout = _LLM_TIMEOUT_DEFAULTS.get(provider, 30)
        llm_timeout = int(os.getenv("QA_LLM_TIMEOUT", default_timeout))
        return cls(provider=provider, model=model, base_url=base_url, role=role, llm_timeout=llm_timeout)

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

    return litellm.completion(**kwargs)
