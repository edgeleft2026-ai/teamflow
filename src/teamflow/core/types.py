"""Shared types used across access, orchestration, and AI layers.

All layers may import from core/types to avoid circular dependencies.
No layer should import from another layer directly.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class FeishuEvent:
    """Parsed Feishu event from lark-cli NDJSON output."""

    event_id: str
    event_type: str
    body: dict
    raw: dict = field(default_factory=dict, repr=False)


@dataclass
class CardActionData:
    """Parsed data from a card.action.trigger event."""

    open_id: str
    chat_id: str
    open_message_id: str
    action_tag: str
    action_value: dict
    form_values: dict
    token: str


@dataclass
class ChatMemberEventData:
    """Parsed data from im.chat.member.user.* events."""

    chat_id: str
    open_ids: list[str]


@dataclass
class CardActionHandleResult:
    """Result of handling a card action — used by card callbacks."""

    toast_type: str = "info"
    toast_text: str = ""
    card: dict | None = None
