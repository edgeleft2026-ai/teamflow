"""Transport layer — provider-specific format conversion and normalization.

Usage:
    from teamflow.ai.transports import get_transport
    transport = get_transport("chat_completions")
    kwargs = transport.build_kwargs(model, messages, tools)
    result = transport.normalize_response(response)
"""

from __future__ import annotations

from teamflow.ai.transports.base import ProviderTransport
from teamflow.ai.transports.chat_completions import ChatCompletionsTransport
from teamflow.ai.transports.types import (
    NormalizedResponse,
    ToolCall,
    Usage,
    build_tool_call,
    map_finish_reason,
)

_registry: dict[str, type] = {
    "chat_completions": ChatCompletionsTransport,
}


def register_transport(api_mode: str, transport_cls: type) -> None:
    """Register a transport class for an api_mode string."""
    _registry[api_mode] = transport_cls


def get_transport(api_mode: str) -> ProviderTransport:
    """Get a transport instance for the given api_mode.

    Returns a ChatCompletionsTransport as fallback if the api_mode is unknown.
    """
    cls = _registry.get(api_mode, ChatCompletionsTransport)
    return cls()


__all__ = [
    "ChatCompletionsTransport",
    "NormalizedResponse",
    "ProviderTransport",
    "ToolCall",
    "Usage",
    "build_tool_call",
    "get_transport",
    "map_finish_reason",
    "register_transport",
]
