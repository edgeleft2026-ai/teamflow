from __future__ import annotations

import json
import logging
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from threading import Lock

from teamflow.access.parser import FeishuEvent, parse_ndjson_line

logger = logging.getLogger(__name__)

# Type for event handler callbacks.
EventHandler = Callable[[FeishuEvent], None]

# Feishu clients may split long messages at ~4096 characters.
# When a chunk is near this limit, a continuation is likely.
_MSG_SPLIT_THRESHOLD = 4000

# Default path for persisting seen event IDs between restarts.
_DEFAULT_DEDUP_PATH = Path("tmp/teamflow/seen_event_ids.json")


@dataclass
class DispatchResult:
    """Result of dispatching an event."""

    handled: bool
    handler_name: str = ""
    skipped_reason: str = ""


class EventDispatcher:
    """Route parsed events to registered handlers by event type.

    Handles event dedup (in-memory + persistent), bot message filtering,
    and message shard detection.
    """

    def __init__(self, dedup_path: Path | None = None) -> None:
        self._handlers: dict[str, list[EventHandler]] = defaultdict(list)
        self._global_handlers: list[EventHandler] = []
        self._seen_event_ids: set[str] = set()
        self._dedup_max_size: int = 10000
        self._dedup_path = dedup_path or _DEFAULT_DEDUP_PATH
        self._dedup_lock = Lock()
        self._flush_counter = 0
        self._pending_shard: dict[str, str] = {}  # chat_id → partial text
        self._load_seen_ids()

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
            # Persist periodically (every 100 new events)
            self._flush_counter += 1
            if self._flush_counter % 100 == 0:
                self._save_seen_ids()

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

    def flush_seen_ids(self) -> None:
        """Persist seen event IDs to disk immediately."""
        self._save_seen_ids()

    def _load_seen_ids(self) -> None:
        """Load persisted seen event IDs from disk."""
        try:
            if self._dedup_path.exists():
                with open(self._dedup_path, encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, list):
                    self._seen_event_ids = set(data[-self._dedup_max_size:])
                    logger.info(
                        "Loaded %d seen event IDs from %s",
                        len(self._seen_event_ids), self._dedup_path,
                    )
        except Exception:
            logger.warning("Failed to load seen event IDs, starting fresh")

    def _save_seen_ids(self) -> None:
        """Save current seen event IDs to disk."""
        try:
            self._dedup_path.parent.mkdir(parents=True, exist_ok=True)
            ids = list(self._seen_event_ids)
            with self._dedup_lock:
                with open(self._dedup_path, "w", encoding="utf-8") as f:
                    json.dump(ids, f)
        except Exception:
            logger.warning("Failed to persist seen event IDs")

