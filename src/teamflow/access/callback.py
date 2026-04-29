"""Feishu card callback handler using lark-oapi WebSocket long connection."""

from __future__ import annotations

import logging
import threading

import lark_oapi as lark
from lark_oapi.event.callback.model.p2_card_action_trigger import (
    CallBackToast,
    P2CardActionTrigger,
    P2CardActionTriggerResponse,
)

from teamflow.access.parser import CardActionData
from teamflow.orchestration.command_router import CommandRouter

logger = logging.getLogger(__name__)


def _build_card_action_data(data: P2CardActionTrigger) -> CardActionData | None:
    """Extract CardActionData from lark-oapi P2CardActionTrigger event data."""
    event = data.event
    if not event:
        return None

    context = event.context
    operator = event.operator
    action = event.action

    chat_id = context.open_chat_id if context else ""
    open_id = operator.open_id if operator else ""
    if not chat_id or not open_id:
        return None

    return CardActionData(
        open_id=open_id,
        chat_id=chat_id,
        action_tag=action.tag or "" if action else "",
        action_value=action.value or {} if action else {},
        form_values=action.form_value or {} if action else {},
        token=event.token or "",
    )


def start_callback_client(
    app_id: str,
    app_secret: str,
    brand: str,
    router: CommandRouter,
) -> lark.ws.Client:
    """Create and return a lark-oapi WebSocket client for card callbacks.

    The caller should run `client.start()` in a daemon thread.
    """

    def on_card_action(data: P2CardActionTrigger) -> P2CardActionTriggerResponse:
        card_data = _build_card_action_data(data)
        if card_data is None:
            logger.warning("Incomplete card callback data, skipping")
            return P2CardActionTriggerResponse()

        logger.info(
            "Card callback: chat=%s user=%s tag=%s",
            card_data.chat_id, card_data.open_id, card_data.action_tag,
        )

        try:
            router.handle_card_action(card_data)
        except Exception:
            logger.exception("Card callback handler error")

        resp = P2CardActionTriggerResponse()
        resp.toast = CallBackToast()
        resp.toast.type = "info"
        resp.toast.content = "提交成功"
        return resp

    event_handler = (
        lark.EventDispatcherHandler.builder("", "")
        .register_p2_card_action_trigger(on_card_action)
        .build()
    )

    domain = "https://open.feishu.cn" if brand == "feishu" else "https://open.larksuite.com"
    client = lark.ws.Client(
        app_id,
        app_secret,
        event_handler=event_handler,
        domain=domain,
        log_level=lark.LogLevel.INFO,
    )

    return client


def start_callback_thread(
    app_id: str,
    app_secret: str,
    brand: str,
    router: CommandRouter,
) -> lark.ws.Client:
    """Start the callback WebSocket client in a daemon thread."""
    client = start_callback_client(app_id, app_secret, brand, router)

    def _run():
        logger.info("Card callback WebSocket client starting...")
        client.start()

    thread = threading.Thread(target=_run, daemon=True, name="card-callback")
    thread.start()
    logger.info("Card callback thread started")

    return client
