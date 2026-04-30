"""Access layer: event parsing, message routing, command dispatch."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .dispatcher import DispatchResult, EventDispatcher, EventHandler
from .parser import (
    CardActionData,
    FeishuEvent,
    extract_card_action_data,
    extract_chat_id,
    extract_message_text,
    extract_open_id,
    is_bot_message,
)
from .watcher import EventFileWatcher

if TYPE_CHECKING:
    from .callback import start_callback_client, start_callback_thread

__all__ = [
    "DispatchResult",
    "EventDispatcher",
    "EventHandler",
    "EventFileWatcher",
    "CardActionData",
    "FeishuEvent",
    "extract_card_action_data",
    "extract_chat_id",
    "extract_message_text",
    "extract_open_id",
    "is_bot_message",
    "start_callback_client",
    "start_callback_thread",
]


def __getattr__(name: str) -> Any:
    """按需加载回调客户端，避免包级循环导入。"""
    if name in {"start_callback_client", "start_callback_thread"}:
        from .callback import start_callback_client, start_callback_thread

        exports = {
            "start_callback_client": start_callback_client,
            "start_callback_thread": start_callback_thread,
        }
        return exports[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
