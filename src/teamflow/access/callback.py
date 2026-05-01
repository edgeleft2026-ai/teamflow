"""Feishu card callback handler using lark-oapi WebSocket long connection."""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable

import lark_oapi as lark
from lark_oapi.event.callback.model.p2_card_action_trigger import (
    CallBackCard,
    CallBackToast,
    P2CardActionTrigger,
    P2CardActionTriggerResponse,
)

from teamflow.core.types import CardActionData, CardActionHandleResult

logger = logging.getLogger(__name__)

CardActionHandler = Callable[[CardActionData], CardActionHandleResult]


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
        open_message_id=context.open_message_id if context else "",
        action_tag=action.tag or "" if action else "",
        action_value=action.value or {} if action else {},
        form_values=action.form_value or {} if action else {},
        token=event.token or "",
    )


def start_callback_client(
    app_id: str,
    app_secret: str,
    brand: str,
    handle_card_action: CardActionHandler,
) -> lark.ws.Client:
    """Create and return a lark-oapi WebSocket client for card callbacks.

    Args:
        app_id: Feishu app ID.
        app_secret: Feishu app secret.
        brand: "feishu" or "lark".
        handle_card_action: Callback that receives CardActionData and returns
            CardActionHandleResult (toast type/text and optional replacement card).

    The caller should run `client.start()` in a daemon thread.
    """

    def on_card_action(data: P2CardActionTrigger) -> P2CardActionTriggerResponse:
        card_data = _build_card_action_data(data)
        if card_data is None:
            logger.warning("卡片回调数据不完整，跳过")
            return P2CardActionTriggerResponse()

        logger.info(
            "收到卡片回调: chat=%s user=%s tag=%s",
            card_data.chat_id, card_data.open_id, card_data.action_tag,
        )

        result = CardActionHandleResult()
        try:
            result = handle_card_action(card_data)
        except Exception:
            logger.exception("卡片回调处理异常")

        resp = P2CardActionTriggerResponse()
        resp.toast = CallBackToast()
        resp.toast.type = result.toast_type if result else "info"
        resp.toast.content = result.toast_text if result else "处理中"
        if result and result.card:
            resp.card = CallBackCard()
            resp.card.type = "raw"
            resp.card.data = result.card
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
        log_level=lark.LogLevel.WARNING,
    )

    return client


def start_callback_thread(
    app_id: str,
    app_secret: str,
    brand: str,
    handle_card_action: CardActionHandler,
) -> lark.ws.Client:
    """Start the callback WebSocket client in a daemon thread.

    Args:
        app_id: Feishu app ID.
        app_secret: Feishu app secret.
        brand: "feishu" or "lark".
        handle_card_action: Card action handler callback.
    """
    client = start_callback_client(app_id, app_secret, brand, handle_card_action)

    def _run_with_reconnect():
        max_retries = 10
        for attempt in range(max_retries):
            try:
                logger.info("卡片回调 WebSocket 客户端启动中...")
                client.start()
            except Exception:
                if attempt >= max_retries - 1:
                    logger.exception("WebSocket 重连次数耗尽，卡片回调已停止")
                    return
                delay = min(2 ** attempt, 60)
                logger.warning(
                    "WebSocket 断开，%ds 后重连 (attempt %d/%d)",
                    delay, attempt + 1, max_retries,
                )
                import time
                time.sleep(delay)

    thread = threading.Thread(
        target=_run_with_reconnect, daemon=True, name="card-callback"
    )
    thread.start()
    logger.info("卡片回调线程已启动")

    return client
