"""Abstract base for provider transports.

A transport owns the data path for one api_mode:
  convert_messages → convert_tools → build_kwargs → normalize_response

It does NOT own: client construction, streaming, credential refresh,
or retry logic. Those stay in the agent layer.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from teamflow.ai.transports.types import NormalizedResponse


class ProviderTransport(ABC):
    """Base class for provider-specific format conversion and normalization."""

    @property
    @abstractmethod
    def api_mode(self) -> str:
        """The api_mode string this transport handles (e.g. 'chat_completions')."""
        ...

    def convert_messages(self, messages: list[dict[str, Any]], **kwargs) -> Any:
        """Convert internal messages to provider-native format.

        Returns provider-specific structure. Default: identity for OpenAI format.
        """
        return messages

    def convert_tools(self, tools: list[dict[str, Any]]) -> Any:
        """Convert internal tool schemas to provider-native format.

        Default: identity for OpenAI format.
        """
        return tools

    @abstractmethod
    def build_kwargs(
        self,
        model: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        **params,
    ) -> dict[str, Any]:
        """Build the complete API call kwargs dict.

        Returns a dict ready to be passed to the provider's SDK client.
        """
        ...

    @abstractmethod
    def normalize_response(self, response: Any, **kwargs) -> NormalizedResponse:
        """Normalize a raw provider response to NormalizedResponse."""
        ...

    def validate_response(self, response: Any) -> bool:
        """Check if the raw response is structurally valid.

        Returns True if valid. Default always returns True.
        """
        return True

    def extract_cache_stats(self, response: Any) -> dict[str, int] | None:
        """Extract provider-specific cache hit/creation stats.

        Returns dict with 'cached_tokens' and 'creation_tokens', or None.
        """
        return None
