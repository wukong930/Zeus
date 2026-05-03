from __future__ import annotations

from typing import Any

import httpx

from app.services.llm.types import (
    LLMCompletionOptions,
    LLMCompletionResult,
    LLMProviderConfig,
    LLMProviderError,
    LLMUsage,
)


class DeepSeekProvider:
    name = "deepseek"

    def __init__(
        self,
        config: LLMProviderConfig,
        *,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.config = config
        self.base_url = (config.base_url or "https://api.deepseek.com/v1").rstrip("/")
        self.client = client or httpx.AsyncClient()

    async def complete(self, options: LLMCompletionOptions) -> LLMCompletionResult:
        body: dict[str, Any] = {
            "model": self.config.model,
            "messages": [
                {"role": message.role, "content": message.content}
                for message in options.messages
            ],
            "max_tokens": options.max_tokens or 2048,
        }
        if options.temperature is not None:
            body["temperature"] = options.temperature
        if options.json_schema is not None or options.json_mode:
            body["response_format"] = {"type": "json_object"}

        response = await self.client.post(
            f"{self.base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {self.config.api_key}",
                "Content-Type": "application/json",
            },
            json=body,
            timeout=self.config.timeout_seconds,
        )
        if response.status_code >= 400:
            raise LLMProviderError(f"DeepSeek API error {response.status_code}: {response.text}")

        data = response.json()
        return LLMCompletionResult(
            content=_extract_choice_content(data),
            usage=_extract_usage(data),
            model=str(data.get("model") or self.config.model),
            raw=data,
        )


def _extract_choice_content(data: dict[str, Any]) -> str:
    choices = data.get("choices")
    if not isinstance(choices, list) or not choices:
        return ""
    choice = choices[0]
    if not isinstance(choice, dict):
        return ""
    message = choice.get("message")
    if not isinstance(message, dict):
        return ""
    content = message.get("content")
    return content if isinstance(content, str) else ""


def _extract_usage(data: dict[str, Any]) -> LLMUsage | None:
    usage = data.get("usage")
    if not isinstance(usage, dict):
        return None
    return LLMUsage(
        input_tokens=usage.get("prompt_tokens") or usage.get("input_tokens"),
        output_tokens=usage.get("completion_tokens") or usage.get("output_tokens"),
    )
