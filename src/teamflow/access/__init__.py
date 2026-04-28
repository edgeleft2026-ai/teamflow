"""Access layer: event parsing, message routing, command dispatch."""

from .dispatcher import DispatchResult, EventDispatcher, EventHandler
from .parser import FeishuEvent, extract_chat_id, extract_message_text, extract_open_id, is_bot_message
from .watcher import EventFileWatcher

__all__ = [
    "DispatchResult",
    "EventDispatcher",
    "EventHandler",
    "EventFileWatcher",
    "FeishuEvent",
    "extract_chat_id",
    "extract_message_text",
    "extract_open_id",
    "is_bot_message",
]
