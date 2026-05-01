from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)


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


def parse_ndjson_line(line: str) -> FeishuEvent | None:
    """Parse a single NDJSON line into a FeishuEvent.

    lark-cli event +subscribe outputs compact NDJSON with one event per line.
    Each line contains at minimum: header.event_id, header.event_type, and the
    event body under the event type key.
    """
    line = line.strip()
    if not line:
        return None

    try:
        data = json.loads(line)
    except json.JSONDecodeError:
        logger.warning("NDJSON 行解析失败: %s", line[:200])
        return None

    if not isinstance(data, dict):
        return None

    # lark-cli --compact mode flattens the event into a single object.
    # Standard SDK event format has header + event body.
    header = data.get("header", {})
    event_id = header.get("event_id", "") or data.get("event_id", "") or data.get("id", "")
    event_type = header.get("event_type", "") or data.get("event_type", "") or data.get("type", "")

    if not event_type:
        return None

    # The body is everything except the header.
    body = {k: v for k, v in data.items() if k != "header"}
    # If there's a nested event key matching the event type, prefer that.
    if event_type in body:
        inner = body[event_type]
        if isinstance(inner, dict):
            body = inner

    return FeishuEvent(event_id=event_id, event_type=event_type, body=body, raw=data)


def parse_ndjson_file(path: Path) -> list[FeishuEvent]:
    """Parse all events from an NDJSON file."""
    events: list[FeishuEvent] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        event = parse_ndjson_line(line)
        if event:
            events.append(event)
    return events


def is_bot_message(event: FeishuEvent, bot_app_id: str) -> bool:
    """Check if an event was sent by the bot itself."""
    sender = event.body.get("sender", {})
    sender_id = sender.get("sender_id", {})
    sender_type = sender.get("sender_type", "")
    # Bot messages have sender_type "app", "bot", or the sender_id.app_id matches.
    if sender_type in ("app", "bot"):
        return True
    if sender_id.get("app_id") == bot_app_id:
        return True
    return False


def extract_open_id(event: FeishuEvent) -> str | None:
    """Extract user open_id from a message event."""
    sender = event.body.get("sender", {})
    sender_id = sender.get("sender_id", {})
    # Compact format: sender_id is a flat string at top level
    if isinstance(sender_id, str):
        return sender_id
    flat_sender_id = event.body.get("sender_id")
    if isinstance(flat_sender_id, str):
        return flat_sender_id
    return sender_id.get("open_id") or sender_id.get("user_id")


def extract_chat_id(event: FeishuEvent) -> str | None:
    """Extract chat_id from a message event."""
    message = event.body.get("message", {})
    return message.get("chat_id") or event.body.get("chat_id")


def extract_message_text(event: FeishuEvent) -> str | None:
    """Extract text content from a message event."""
    message = event.body.get("message", {})
    content_str = message.get("content", "") or event.body.get("content", "")
    if not content_str:
        return None
    # Compact format: content is plain text
    if event.body.get("message_type") == "text" and not content_str.startswith("{"):
        return content_str
    try:
        content = json.loads(content_str)
        return content.get("text", "")
    except json.JSONDecodeError:
        return content_str


def extract_card_action_data(event: FeishuEvent) -> CardActionData | None:
    """Extract all relevant data from a card.action.trigger event.

    Handles both the standard nested SDK format (event.*) and
    lark-cli --compact flat format.
    """
    body = event.body

    # Try nested SDK format first: body.event.context / body.event.operator
    ev = body.get("event") if isinstance(body.get("event"), dict) else body
    if not isinstance(ev, dict):
        return None

    # lark-cli compact format: body.context / body.operator / body.action
    #   context can be at top level or under "event"
    context = ev.get("context", {}) or body.get("context", {})
    if not isinstance(context, dict):
        context = {}
    chat_id = context.get("open_chat_id")
    open_message_id = context.get("open_message_id", "")

    operator = ev.get("operator", {}) or body.get("operator", {})
    if not isinstance(operator, dict):
        operator = {}
    open_id = operator.get("open_id")

    if not chat_id or not open_id:
        return None

    # lark-cli compact format: body.action.tag / body.action.value / body.action.form_value
    action = ev.get("action", {}) or body.get("action", {})
    if not isinstance(action, dict):
        action = {}
    action_tag = action.get("tag", "")
    action_value = action.get("value", {})
    form_values = action.get("form_value", {}) or ev.get("form_value", {}) or {}

    token = body.get("token", "") or ev.get("token", "") or ""

    return CardActionData(
        open_id=open_id,
        chat_id=chat_id,
        open_message_id=open_message_id,
        action_tag=action_tag,
        action_value=action_value if isinstance(action_value, dict) else {},
        form_values=form_values if isinstance(form_values, dict) else {},
        token=token,
    )
