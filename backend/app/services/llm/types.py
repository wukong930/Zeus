from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Protocol, Sequence

LLMProviderName = Literal["openai", "anthropic", "deepseek"]
LLMRole = Literal["system", "user", "assistant"]

DEFAULT_MODELS: dict[LLMProviderName, tuple[str, ...]] = {
    "openai": ("gpt-4o", "gpt-4o-mini", "o3", "o3-mini", "o1", "o1-mini"),
    "anthropic": (
        "claude-opus-4-20250918",
        "claude-sonnet-4-20250514",
        "claude-haiku-4-5-20251001",
    ),
    "deepseek": ("deepseek-chat", "deepseek-reasoner"),
}


class LLMProviderError(RuntimeError):
    """Raised when a provider request fails or returns an invalid response."""


class LLMConfigurationError(RuntimeError):
    """Raised when no usable LLM provider config can be resolved."""


@dataclass(frozen=True, slots=True)
class LLMMessage:
    role: LLMRole
    content: str


@dataclass(frozen=True, slots=True)
class LLMUsage:
    input_tokens: int | None = None
    output_tokens: int | None = None


@dataclass(frozen=True, slots=True)
class LLMCompletionOptions:
    messages: Sequence[LLMMessage]
    temperature: float | None = None
    max_tokens: int | None = None
    json_mode: bool = False
    json_schema: dict[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class LLMCompletionResult:
    content: str
    model: str
    usage: LLMUsage | None = None
    raw: dict[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class LLMProviderConfig:
    provider: LLMProviderName
    api_key: str
    model: str
    enabled: bool = True
    base_url: str | None = None
    timeout_seconds: float = 120.0


class LLMProvider(Protocol):
    name: LLMProviderName

    async def complete(self, options: LLMCompletionOptions) -> LLMCompletionResult:
        """Generate one completion using this provider."""
