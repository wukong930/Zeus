import json

import httpx
import pytest

from app.core.config import Settings
from app.services.llm.anthropic import AnthropicProvider
from app.services.llm.deepseek import DeepSeekProvider
from app.services.llm.openai import OpenAIProvider
from app.services.llm.registry import create_provider, get_env_llm_config
from app.services.llm.types import (
    LLMCompletionOptions,
    LLMConfigurationError,
    LLMMessage,
    LLMProviderConfig,
)


@pytest.mark.asyncio
async def test_openai_provider_uses_responses_api() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert request.url.path == "/v1/responses"
        assert request.headers["authorization"] == "Bearer sk-test"
        assert body["store"] is False
        assert body["instructions"] == "You are terse."
        assert body["input"] == [{"role": "user", "content": "Say hello"}]
        assert body["text"]["format"]["type"] == "json_object"
        return httpx.Response(
            200,
            json={
                "model": "gpt-test",
                "output_text": '{"ok":true}',
                "usage": {"input_tokens": 12, "output_tokens": 4},
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = OpenAIProvider(
            LLMProviderConfig(
                provider="openai",
                api_key="sk-test",
                model="gpt-test",
                base_url="https://api.openai.test/v1",
            ),
            client=client,
        )

        result = await provider.complete(
            LLMCompletionOptions(
                messages=[
                    LLMMessage(role="system", content="You are terse."),
                    LLMMessage(role="user", content="Say hello"),
                ],
                json_mode=True,
            )
        )

    assert result.content == '{"ok":true}'
    assert result.usage is not None
    assert result.usage.input_tokens == 12
    assert result.usage.output_tokens == 4


@pytest.mark.asyncio
async def test_openai_provider_extracts_text_from_output_items() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "model": "gpt-test",
                "output": [
                    {
                        "type": "message",
                        "content": [
                            {"type": "output_text", "text": "hello"},
                            {"type": "output_text", "text": " world"},
                        ],
                    }
                ],
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = OpenAIProvider(
            LLMProviderConfig(provider="openai", api_key="sk-test", model="gpt-test"),
            client=client,
        )
        result = await provider.complete(
            LLMCompletionOptions(messages=[LLMMessage(role="user", content="Hello")])
        )

    assert result.content == "hello world"


@pytest.mark.asyncio
async def test_anthropic_provider_splits_system_message() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert request.url.path == "/v1/messages"
        assert request.headers["x-api-key"] == "sk-ant"
        assert body["system"] == [
            {
                "type": "text",
                "text": "System prompt\n\nReturn valid JSON only.",
                "cache_control": {"type": "ephemeral"},
            }
        ]
        assert body["messages"] == [{"role": "user", "content": "Classify"}]
        return httpx.Response(
            200,
            json={
                "model": "claude-test",
                "content": [{"type": "text", "text": '{"classification":"ok"}'}],
                "usage": {"input_tokens": 10, "output_tokens": 5},
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = AnthropicProvider(
            LLMProviderConfig(provider="anthropic", api_key="sk-ant", model="claude-test"),
            client=client,
        )
        result = await provider.complete(
            LLMCompletionOptions(
                messages=[
                    LLMMessage(role="system", content="System prompt"),
                    LLMMessage(role="user", content="Classify"),
                ],
                json_mode=True,
            )
        )

    assert result.content == '{"classification":"ok"}'


@pytest.mark.asyncio
async def test_deepseek_provider_uses_chat_completions() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert request.url.path == "/v1/chat/completions"
        assert body["response_format"] == {"type": "json_object"}
        assert body["messages"] == [{"role": "user", "content": "Ping"}]
        return httpx.Response(
            200,
            json={
                "model": "deepseek-chat",
                "choices": [{"message": {"content": '{"pong":true}'}}],
                "usage": {"prompt_tokens": 8, "completion_tokens": 3},
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = DeepSeekProvider(
            LLMProviderConfig(provider="deepseek", api_key="sk-ds", model="deepseek-chat"),
            client=client,
        )
        result = await provider.complete(
            LLMCompletionOptions(
                messages=[LLMMessage(role="user", content="Ping")],
                json_mode=True,
            )
        )

    assert result.content == '{"pong":true}'
    assert result.usage is not None
    assert result.usage.input_tokens == 8
    assert result.usage.output_tokens == 3


def test_registry_prefers_env_provider_order() -> None:
    settings = Settings(
        openai_api_key="sk-openai",
        anthropic_api_key="sk-ant",
        llm_model="gpt-test",
        _env_file=None,
    )

    config = get_env_llm_config(settings)

    assert config is not None
    assert config.provider == "openai"
    assert config.model == "gpt-test"


def test_registry_rejects_missing_api_key() -> None:
    with pytest.raises(LLMConfigurationError):
        create_provider(
            LLMProviderConfig(provider="openai", api_key="", model="gpt-test"),
        )
