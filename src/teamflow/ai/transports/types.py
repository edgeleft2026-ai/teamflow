"""Shared types for normalized provider responses.

These dataclasses define the canonical shape that all provider transports
normalize to. Provider-specific state goes in ``provider_data`` dicts.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolCall:
    """A normalized tool call from any provider.

    ``id`` is the protocol's canonical tool-call identifier.
    ``name`` is the tool name (e.g. "im.v1.chat.create").
    ``arguments`` is the JSON-encoded arguments string.
    """

    id: str | None
    name: str
    arguments: str  # JSON string

    @property
    def type(self) -> str:
        return "function"

    @property
    def function(self) -> ToolCall:
        """Return self so tc.function.name / tc.function.arguments work."""
        return self


@dataclass
class Usage:
    """Token usage from an API response."""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cached_tokens: int = 0


@dataclass
class NormalizedResponse:
    """Normalized API response from any provider.

    Fields that every downstream consumer relies on.  Protocol-specific
    state lives in ``provider_data``.
    """

    content: str | None
    tool_calls: list[ToolCall] | None
    finish_reason: str  # "stop", "tool_calls", "length", "content_filter"
    reasoning: str | None = None
    reasoning_content: str | None = None
    usage: Usage | None = None
    provider_data: dict[str, Any] | None = field(default=None, repr=False)


def build_tool_call(
    tool_id: str | None,
    name: str,
    arguments: Any,
) -> ToolCall:
    """Build a ToolCall, auto-serialising arguments if it's a dict."""
    args_str = json.dumps(arguments) if isinstance(arguments, dict) else str(arguments)
    return ToolCall(id=tool_id, name=name, arguments=args_str)


def map_finish_reason(reason: str | None, mapping: dict[str, str]) -> str:
    """Translate a provider-specific stop reason to the normalised set."""
    if reason is None:
        return "stop"
    return mapping.get(reason, "stop")
