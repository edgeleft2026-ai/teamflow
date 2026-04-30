"""OpenAI Chat Completions transport.

Handles the default api_mode ('chat_completions') used by OpenAI-compatible
providers (OpenRouter, DeepSeek, Qwen, Ollama, Groq, etc.).

Messages and tools are already in OpenAI format — convert_messages and
convert_tools are near-identity. The complexity lives in build_kwargs with
provider-specific reasoning configuration.
"""

from __future__ import annotations

from typing import Any

from teamflow.ai.transports.base import ProviderTransport
from teamflow.ai.transports.types import NormalizedResponse, ToolCall, Usage


class ChatCompletionsTransport(ProviderTransport):
    """Transport for api_mode='chat_completions'. Default for OpenAI-compatible providers."""

    @property
    def api_mode(self) -> str:
        return "chat_completions"

    def convert_messages(
        self, messages: list[dict[str, Any]], **kwargs
    ) -> list[dict[str, Any]]:
        """Messages are already in OpenAI format — identity pass."""
        return messages

    def convert_tools(self, tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Tools already in OpenAI format — identity pass."""
        return tools

    def build_kwargs(
        self,
        model: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        **params,
    ) -> dict[str, Any]:
        """Build chat.completions.create() kwargs.

        params (all optional):
            max_tokens: int | None
            temperature: float | None
            reasoning_config: dict | None — {"enabled": True, "effort": "medium"}
            supports_reasoning: bool
            extra_body: dict | None — provider-specific extra_body entries
            timeout: float | None
            request_overrides: dict | None
            developer_role: bool — use "developer" role for GPT-5+ models
        """
        api_kwargs: dict[str, Any] = {
            "model": model,
            "messages": messages,
        }

        # Developer role swap for GPT-5 models
        if params.get("developer_role"):
            sanitized = list(messages)
            if sanitized and sanitized[0].get("role") == "system":
                sanitized[0] = {**sanitized[0], "role": "developer"}
            api_kwargs["messages"] = sanitized

        if tools:
            api_kwargs["tools"] = tools

        # max_tokens
        max_tokens = params.get("max_tokens")
        if max_tokens is not None:
            api_kwargs["max_tokens"] = max_tokens

        # Temperature
        temperature = params.get("temperature")
        if temperature is not None:
            api_kwargs["temperature"] = temperature

        # Reasoning / thinking configuration
        supports_reasoning = params.get("supports_reasoning", False)
        reasoning_config = params.get("reasoning_config")
        if supports_reasoning and reasoning_config is not None:
            extra_body = api_kwargs.setdefault("extra_body", {})
            extra_body["reasoning"] = dict(reasoning_config)

        # Merge provider-specific extra_body
        extra_body = params.get("extra_body")
        if extra_body:
            existing = api_kwargs.setdefault("extra_body", {})
            existing.update(extra_body)

        timeout = params.get("timeout")
        if timeout is not None:
            api_kwargs["timeout"] = timeout

        overrides = params.get("request_overrides")
        if overrides:
            api_kwargs.update(overrides)

        return api_kwargs

    def normalize_response(self, response: Any, **kwargs) -> NormalizedResponse:
        """Normalize OpenAI ChatCompletion to NormalizedResponse."""
        choice = response.choices[0]
        msg = choice.message
        finish_reason = choice.finish_reason or "stop"

        tool_calls = None
        if msg.tool_calls:
            tool_calls = []
            for tc in msg.tool_calls:
                tool_calls.append(
                    ToolCall(
                        id=tc.id,
                        name=tc.function.name,
                        arguments=tc.function.arguments,
                    )
                )

        usage = None
        if hasattr(response, "usage") and response.usage:
            u = response.usage
            usage = Usage(
                prompt_tokens=getattr(u, "prompt_tokens", 0) or 0,
                completion_tokens=getattr(u, "completion_tokens", 0) or 0,
                total_tokens=getattr(u, "total_tokens", 0) or 0,
            )

        provider_data: dict[str, Any] = {}
        rcontent = getattr(msg, "reasoning_content", None)
        if rcontent:
            provider_data["reasoning_content"] = rcontent

        return NormalizedResponse(
            content=msg.content,
            tool_calls=tool_calls,
            finish_reason=finish_reason,
            reasoning=getattr(msg, "reasoning", None),
            reasoning_content=rcontent,
            usage=usage,
            provider_data=provider_data or None,
        )

    def validate_response(self, response: Any) -> bool:
        """Check that response has valid choices."""
        if response is None:
            return False
        if not hasattr(response, "choices") or response.choices is None:
            return False
        if not response.choices:
            return False
        return True
