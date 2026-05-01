from __future__ import annotations

import json
import logging

from teamflow.config import FeishuConfig
from teamflow.execution.cli import CLIResult, run_cli

logger = logging.getLogger(__name__)

_lark_client_cache: dict[str, object] = {}


def _get_lark_client(feishu: FeishuConfig):
    import lark_oapi as lark

    cache_key = feishu.app_id
    if cache_key not in _lark_client_cache:
        base_url = (
            "https://open.feishu.cn"
            if feishu.brand == "feishu"
            else "https://open.larksuite.com"
        )
        _lark_client_cache[cache_key] = (
            lark.Client.builder()
            .app_id(feishu.app_id)
            .app_secret(feishu.app_secret)
            .domain(base_url)
            .log_level(lark.LogLevel.WARNING)
            .build()
        )
    return _lark_client_cache[cache_key]


def send_message(
    feishu: FeishuConfig,
    *,
    chat_id: str | None = None,
    user_id: str | None = None,
    text: str | None = None,
    markdown: str | None = None,
    msg_type: str | None = None,
    content: str | None = None,
    as_bot: bool = True,
    idempotency_key: str | None = None,
    cli_binary: str | None = None,
) -> CLIResult:
    """Send a message to a chat or user via lark-cli.

    Exactly one of chat_id or user_id must be provided.
    Exactly one of text, markdown, or content must be provided.
    """
    args: list[str] = ["im", "+messages-send"]

    if chat_id:
        args += ["--chat-id", chat_id]
    if user_id:
        args += ["--user-id", user_id]
    if text:
        args += ["--text", text]
    if markdown:
        args += ["--markdown", markdown]
    if content:
        args += ["--content", content]
    if msg_type:
        args += ["--msg-type", msg_type]
    if not as_bot:
        args += ["--as", "user"]
    if idempotency_key:
        args += ["--idempotency-key", idempotency_key]

    result = run_cli(args, feishu=feishu, cli_binary=cli_binary)
    if not result.success:
        logger.warning("发送消息失败: %s", result.error)
    return result


def send_text(
    feishu: FeishuConfig,
    text: str,
    *,
    chat_id: str | None = None,
    user_id: str | None = None,
    **kwargs,
) -> CLIResult:
    """Shorthand for sending a plain text message."""
    return send_message(feishu, chat_id=chat_id, user_id=user_id, text=text, **kwargs)


def send_card(
    feishu: FeishuConfig,
    card: dict,
    *,
    chat_id: str | None = None,
    user_id: str | None = None,
    **kwargs,
) -> CLIResult:
    """Send an interactive card message."""
    return send_message(
        feishu,
        chat_id=chat_id,
        user_id=user_id,
        msg_type="interactive",
        content=json.dumps(card, ensure_ascii=False),
        **kwargs,
    )


def update_card_message(
    feishu: FeishuConfig,
    message_id: str,
    card: dict,
) -> CLIResult:
    """Update a previously sent interactive card message."""
    import lark_oapi as lark

    client = _get_lark_client(feishu)

    body = lark.im.v1.PatchMessageRequestBody.builder() \
        .content(json.dumps(card, ensure_ascii=False)) \
        .build()
    req = lark.im.v1.PatchMessageRequest.builder() \
        .message_id(message_id) \
        .request_body(body) \
        .build()
    resp = client.im.v1.message.patch(req)
    if not resp.success():
        logger.warning("更新卡片消息失败: %s (%s)", resp.msg, resp.code)
        return CLIResult(success=False, error=f"{resp.msg} ({resp.code})")
    return CLIResult(success=True)


def send_markdown(
    feishu: FeishuConfig,
    markdown: str,
    *,
    chat_id: str | None = None,
    user_id: str | None = None,
    **kwargs,
) -> CLIResult:
    """Shorthand for sending a markdown message."""
    return send_message(feishu, chat_id=chat_id, user_id=user_id, markdown=markdown, **kwargs)


async def send_text_async(
    feishu: FeishuConfig,
    text: str,
    *,
    chat_id: str | None = None,
    user_id: str | None = None,
    **kwargs,
) -> CLIResult:
    """Async wrapper for send_text — runs lark-cli in a thread to avoid blocking."""
    import asyncio
    return await asyncio.to_thread(
        send_text, feishu, text, chat_id=chat_id, user_id=user_id, **kwargs
    )


async def send_card_async(
    feishu: FeishuConfig,
    card: dict,
    *,
    chat_id: str | None = None,
    user_id: str | None = None,
    **kwargs,
) -> CLIResult:
    """Async wrapper for send_card — runs lark-cli in a thread to avoid blocking."""
    import asyncio
    return await asyncio.to_thread(
        send_card, feishu, card, chat_id=chat_id, user_id=user_id, **kwargs
    )


async def update_card_message_async(
    feishu: FeishuConfig,
    message_id: str,
    card: dict,
) -> CLIResult:
    """Async wrapper for update_card_message."""
    import asyncio

    return await asyncio.to_thread(update_card_message, feishu, message_id, card)


def create_chat(
    feishu: FeishuConfig,
    *,
    name: str | None = None,
    users: str | None = None,
    description: str | None = None,
    chat_type: str = "private",
    set_bot_manager: bool = False,
    cli_binary: str | None = None,
) -> CLIResult:
    """Create a group chat via lark-cli."""
    args: list[str] = ["im", "+chat-create", "--type", chat_type]
    if name:
        args += ["--name", name]
    if users:
        args += ["--users", users]
    if description:
        args += ["--description", description]
    if set_bot_manager:
        args += ["--set-bot-manager"]

    return run_cli(args, feishu=feishu, cli_binary=cli_binary)


def add_chat_members(
    feishu: FeishuConfig,
    chat_id: str,
    users: str,
    *,
    cli_binary: str | None = None,
) -> CLIResult:
    """Add members to a chat via lark-cli."""
    return run_cli(
        ["im", "+chat-members-add", "--chat-id", chat_id, "--users", users],
        feishu=feishu,
        cli_binary=cli_binary,
    )
