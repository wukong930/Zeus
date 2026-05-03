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


class OpenAIProvider:
    name = "openai"

    def __init__(
        self,
        config: LLMProviderConfig,
        *,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.config = config
        self.base_url = (config.base_url or "https://api.openai.com/v1").rstrip("/")
        self.client = client or httpx.AsyncClient()

    async def complete(self, options: LLMCompletionOptions) -> LLMCompletionResult:
        body: dict[str, Any] = {
            "model": self.config.model,
            "input": _to_responses_input(options.messages),
            "max_output_tokens": options.max_tokens or 2048,
            "store": False,
        }

        instructions = _system_instructions(options.messages)
        if instructions:
            body["instructions"] = instructions
        if options.temperature is not None:
            body["temperature"] = options.temperature
        if options.json_schema is not None:
            body["text"] = {
                "format": {
                    "type": "json_schema",
                    "name": "zeus_response",
                    "strict": True,
                    "schema": options.json_schema,
                }
            }
        elif options.json_mode:
            body["text"] = {"format": {"type": "json_object"}}

        response = await self.client.post(
            f"{self.base_url}/responses",
            headers={
                "Authorization": f"Bearer {self.config.api_key}",
                "Content-Type": "application/json",
            },
            json=body,
            timeout=self.config.timeout_seconds,
        )
        if response.status_code >= 400:
            raise LLMProviderError(f"OpenAI API error {response.status_code}: {response.text}")

        data = response.json()
        return LLMCompletionResult(
            content=_extract_output_text(data),
            usage=_extract_usage(data),
            model=str(data.get("model") or self.config.model),
            raw=data,
        )


def _system_instructions(messages: Sequence[LLMMessage]) -> str | None:
    instructions = [message.content for message in messages if message.role == "system"]
    return "\n\n".join(instructions) or None


def _to_responses_input(messages: Sequence[LLMMessage]) -> list[dict[str, str]]:
    return [
        {"role": message.role, "content": message.content}
        for message in messages
        if message.role != "system"
    ]


def _extract_output_text(data: dict[str, Any]) -> str:
    if isinstance(data.get("output_text"), str):
        return data["output_text"]

    parts: list[str] = []
    for item in data.get("output") or []:
        if not isinstance(item, dict) or item.get("type") != "message":
            continue
        for block in item.get("content") or []:
            if not isinstance(block, dict):
                continue
            if isinstance(block.get("text"), str):
                parts.append(block["text"])
            elif isinstance(block.get("refusal"), str):
                parts.append(block["refusal"])
    return "".join(parts)


def _extract_usage(data: dict[str, Any]) -> LLMUsage | None:
    usage = data.get("usage")
    if not isinstance(usage, dict):
        return None
    return LLMUsage(
        input_tokens=usage.get("input_tokens") or usage.get("prompt_tokens"),
        output_tokens=usage.get("output_tokens") or usage.get("completion_tokens"),
    )
