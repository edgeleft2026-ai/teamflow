"""Access layer: event parsing, message routing, command dispatch."""

from .callback import start_callback_client, start_callback_thread
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
