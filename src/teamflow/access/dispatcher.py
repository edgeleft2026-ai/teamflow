from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass
from typing import Callable

from teamflow.access.parser import FeishuEvent, parse_ndjson_line

logger = logging.getLogger(__name__)

# Type for event handler callbacks.
EventHandler = Callable[[FeishuEvent], None]


@dataclass
class DispatchResult:
    """Result of dispatching an event."""

    handled: bool
    handler_name: str = ""
    skipped_reason: str = ""


class EventDispatcher:
    """Route parsed events to registered handlers by event type."""

    def __init__(self) -> None:
        self._handlers: dict[str, list[EventHandler]] = defaultdict(list)
        self._global_handlers: list[EventHandler] = []
        self._seen_event_ids: set[str] = set()
        self._dedup_max_size: int = 10000

    def on(self, event_type: str, handler: EventHandler) -> None:
        """Register a handler for a specific event type."""
        self._handlers[event_type].append(handler)

    def on_any(self, handler: EventHandler) -> None:
        """Register a handler that receives all events."""
        self._global_handlers.append(handler)

    def dispatch_raw(self, ndjson_line: str) -> DispatchResult:
        """Parse and dispatch a raw NDJSON line.

        Handles dedup and bot message filtering.
        """
        event = parse_ndjson_line(ndjson_line)
        if event is None:
            return DispatchResult(handled=False, skipped_reason="parse_failed")

        return self.dispatch(event)

    def dispatch(self, event: FeishuEvent) -> DispatchResult:
        """Dispatch a parsed event to registered handlers."""
        # Dedup by event_id
        if event.event_id:
            if event.event_id in self._seen_event_ids:
                return DispatchResult(handled=False, skipped_reason="duplicate")
            self._seen_event_ids.add(event.event_id)
            if len(self._seen_event_ids) > self._dedup_max_size:
                # Evict oldest entries (approximate: clear half)
                to_remove = list(self._seen_event_ids)[: self._dedup_max_size // 2]
                self._seen_event_ids -= set(to_remove)

        # Call type-specific handlers
        handlers = self._handlers.get(event.event_type, [])
        for handler in handlers:
            try:
                handler(event)
            except Exception:
                logger.exception("Error in handler for %s", event.event_type)

        # Call global handlers
        for handler in self._global_handlers:
            try:
                handler(event)
            except Exception:
                logger.exception("Error in global handler")

        handled = len(handlers) > 0 or len(self._global_handlers) > 0
        return DispatchResult(
            handled=handled,
            handler_name=event.event_type,
        )
