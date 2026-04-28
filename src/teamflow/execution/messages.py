from __future__ import annotations

from teamflow.config import FeishuConfig
from teamflow.execution.cli import CLIResult, run_cli


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

    return run_cli(args, feishu=feishu, cli_binary=cli_binary)


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
