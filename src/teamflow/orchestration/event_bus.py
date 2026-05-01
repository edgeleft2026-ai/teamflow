from __future__ import annotations

import logging
from collections.abc import Callable

from sqlmodel import Session

from teamflow.storage.models import EventLog
from teamflow.storage.repository import EventLogRepo

logger = logging.getLogger(__name__)

EventHandler = Callable[[EventLog], None]


class EventBus:
    _global_handlers: dict[str, list[EventHandler]] = {}

    def __init__(self, session: Session) -> None:
        self.session = session
        self.repo = EventLogRepo(session)
        self._handlers: dict[str, list[EventHandler]] = {}

    def subscribe(self, event_type: str, handler: EventHandler) -> None:
        self._handlers.setdefault(event_type, []).append(handler)

    @classmethod
    def subscribe_global(cls, event_type: str, handler: EventHandler) -> None:
        cls._global_handlers.setdefault(event_type, []).append(handler)

    @classmethod
    def unsubscribe_global(cls, event_type: str, handler: EventHandler | None = None) -> None:
        """Remove global handler(s). If handler is None, remove all for event_type."""
        if event_type not in cls._global_handlers:
            return
        if handler is None:
            cls._global_handlers.pop(event_type, None)
        else:
            handlers = cls._global_handlers.get(event_type, [])
            if handler in handlers:
                handlers.remove(handler)

    def publish(
        self,
        event_type: str,
        idempotency_key: str,
        *,
        project_id: str | None = None,
        source: str = "teamflow",
        payload: dict | None = None,
    ) -> EventLog | None:
        if self.repo.exists_by_idempotency_key(idempotency_key):
            logger.info("事件已去重: %s (key=%s)", event_type, idempotency_key)
            return None

        event = self.repo.create(
            event_type=event_type,
            idempotency_key=idempotency_key,
            project_id=project_id,
            source=source,
            payload=payload,
        )
        logger.info("事件已发布: %s (id=%s)", event_type, event.id[:8])

        handlers = self._handlers.get(event_type, []) + self._global_handlers.get(
            event_type, []
        )
        for handler in handlers:
            try:
                handler(event)
            except Exception:
                logger.exception("事件处理器执行异常: %s", event_type)

        return event
