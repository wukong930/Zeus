from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import httpx

from app.services.llm.types import (
    LLMCompletionOptions,
    LLMCompletionResult,
    LLMMessage,
    LLMProviderConfig,
    LLMProviderError,
    LLMUsage,
)


class AnthropicProvider:
    name = "anthropic"

    def __init__(
        self,
        config: LLMProviderConfig,
        *,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.config = config
        self.base_url = (config.base_url or "https://api.anthropic.com").rstrip("/")
        self.client = client or httpx.AsyncClient()

    async def complete(self, options: LLMCompletionOptions) -> LLMCompletionResult:
        body: dict[str, Any] = {
            "model": self.config.model,
            "max_tokens": options.max_tokens or 2048,
            "messages": [
                {"role": message.role, "content": message.content}
                for message in options.messages
                if message.role != "system"
            ],
        }

        system_prompt = _system_prompt(options.messages, json_mode=options.json_mode)
        if system_prompt:
            body["system"] = system_prompt
        if options.temperature is not None:
            body["temperature"] = options.temperature

        response = await self.client.post(
            f"{self.base_url}/v1/messages",
            headers={
                "Content-Type": "application/json",
                "x-api-key": self.config.api_key,
                "anthropic-version": "2023-06-01",
            },
            json=body,
            timeout=self.config.timeout_seconds,
        )
        if response.status_code >= 400:
            raise LLMProviderError(f"Anthropic API error {response.status_code}: {response.text}")

        data = response.json()
        return LLMCompletionResult(
            content=_extract_text_content(data),
            usage=_extract_usage(data),
            model=str(data.get("model") or self.config.model),
            raw=data,
        )


def _system_prompt(messages: Sequence[LLMMessage], *, json_mode: bool) -> str | None:
    prompts = [message.content for message in messages if message.role == "system"]
    if json_mode:
        prompts.append("Return valid JSON only.")
    return "\n\n".join(prompts) or None


def _extract_text_content(data: dict[str, Any]) -> str:
    parts: list[str] = []
    for block in data.get("content") or []:
        if isinstance(block, dict) and block.get("type") == "text" and isinstance(block.get("text"), str):
            parts.append(block["text"])
    return "".join(parts)


def _extract_usage(data: dict[str, Any]) -> LLMUsage | None:
    usage = data.get("usage")
    if not isinstance(usage, dict):
        return None
    return LLMUsage(
        input_tokens=usage.get("input_tokens"),
        output_tokens=usage.get("output_tokens"),
    )
