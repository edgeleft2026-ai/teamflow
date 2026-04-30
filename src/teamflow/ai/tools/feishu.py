"""Feishu API tools — callable by the Agent Executor via ToolProvider.

Each tool is an async function decorated with ``@tool_provider.register_func()``.
The lark-oapi SDK is used under the hood; credentials are read from the global
``feishu_client`` which must be initialized before any tool is called.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# Global Feishu client — set by main.py at startup.
feishu_client: Any = None


def init_feishu_client(app_id: str, app_secret: str, brand: str = "feishu") -> None:
    """Initialize the global Feishu client. Call once at startup."""
    global feishu_client
    import lark_oapi as lark

    base_url = (
        "https://open.feishu.cn"
        if brand == "feishu"
        else "https://open.larksuite.com"
    )
    feishu_client = lark.Client.builder() \
        .app_id(app_id) \
        .app_secret(app_secret) \
        .open_api_base_url(base_url) \
        .log_level(lark.LogLevel.INFO) \
        .build()
    logger.info("Feishu client initialized (brand=%s)", brand)


# ── IM: Chat tools ────────────────────────────────────────────────────────


async def _create_chat(name: str, description: str = "") -> dict:
    """Create a Feishu group chat."""
    import lark_oapi as lark

    body = lark.im.v1.CreateChatRequestBody.builder() \
        .name(name) \
        .description(description) \
        .chat_mode("group") \
        .build()
    req = lark.im.v1.CreateChatRequest.builder() \
        .request_body(body) \
        .build()
    resp = feishu_client.im.v1.chat.create(req)
    if not resp.success():
        raise RuntimeError(f"Create chat failed: {resp.msg} ({resp.code})")
    d = resp.data
    return {
        "chat_id": d.chat_id,
        "name": d.name,
        "description": d.description,
        "chat_type": "group",
    }


async def _add_members_to_chat(chat_id: str, open_ids: list[str]) -> dict:
    """Add members to a Feishu group chat."""
    import lark_oapi as lark

    builder = lark.im.v1.ChatMember.builder()
    members = [
        builder.member_id_type("open_id").member_id(oid).build()
        for oid in open_ids
    ]
    body = lark.im.v1.CreateChatMembersRequestBody.builder().members(members).build()
    req = (
        lark.im.v1.CreateChatMembersRequest.builder()
        .chat_id(chat_id)
        .member_id_type("open_id")
        .request_body(body)
        .build()
    )
    resp = feishu_client.im.v1.chat_members.create(req)
    if not resp.success():
        raise RuntimeError(f"Add members failed: {resp.msg} ({resp.code})")
    return {"chat_id": chat_id, "added_count": len(open_ids)}


async def _get_chat(chat_id: str) -> dict:
    """Get Feishu group chat info."""
    req = feishu_client.im.v1.GetChatRequest.builder().chat_id(chat_id).build()
    resp = feishu_client.im.v1.chat.get(req)
    if not resp.success():
        raise RuntimeError(f"Get chat failed: {resp.msg} ({resp.code})")
    d = resp.data
    return {"chat_id": d.chat_id, "name": d.name, "description": d.description}


async def _get_chat_link(chat_id: str) -> dict:
    """Get share link for a Feishu group chat."""
    import lark_oapi as lark

    body = lark.im.v1.LinkChatRequestBody.builder().build()
    req = lark.im.v1.LinkChatRequest.builder().chat_id(chat_id).request_body(body).build()
    resp = feishu_client.im.v1.chat.link(req)
    if not resp.success():
        raise RuntimeError(f"Get chat link failed: {resp.msg} ({resp.code})")
    return {"chat_id": chat_id, "share_link": resp.data.share_link}


# ── IM: Message tools ─────────────────────────────────────────────────────


async def _send_message(
    receive_id: str,
    content: str,
    msg_type: str = "text",
    receive_id_type: str = "chat_id",
) -> dict:
    """Send a message to a chat or user."""
    import lark_oapi as lark

    msg_content: Any
    if msg_type == "text":
        msg_content = json_dumps({"text": content})
    elif msg_type == "interactive":
        msg_content = content  # Already JSON
    else:
        msg_content = json_dumps({"text": content})

    body = lark.im.v1.CreateMessageRequestBody.builder() \
        .receive_id(receive_id) \
        .msg_type(msg_type) \
        .content(msg_content) \
        .build()
    req = lark.im.v1.CreateMessageRequest.builder() \
        .receive_id_type(receive_id_type) \
        .request_body(body) \
        .build()
    resp = feishu_client.im.v1.message.create(req)
    if not resp.success():
        raise RuntimeError(f"Send message failed: {resp.msg} ({resp.code})")
    return {"message_id": resp.data.message_id, "chat_id": resp.data.chat_id}


# ── Docx tools ──────────────────────────────────────────────────────────


async def _create_document(title: str, content: str = "") -> dict:
    """Create a Feishu Docx document."""
    import lark_oapi as lark

    body = lark.docx.v1.CreateDocumentRequestBody.builder() \
        .title(title) \
        .build()
    req = lark.docx.v1.CreateDocumentRequest.builder() \
        .request_body(body) \
        .build()
    resp = feishu_client.docx.v1.document.create(req)
    if not resp.success():
        raise RuntimeError(f"Create document failed: {resp.msg} ({resp.code})")
    d = resp.data
    return {"document_id": d.document.document_id, "title": d.document.title, "url": d.document.url}


# ── Bot info tool (for testing) ───────────────────────────────────────────


async def _get_bot_info() -> dict:
    """Get bot information."""
    resp = feishu_client.im.v1.bot.info()
    if not resp.success():
        raise RuntimeError(f"Get bot info failed: {resp.msg} ({resp.code})")
    d = resp.data
    return {"bot_name": d.name, "app_id": d.app_id, "activate_status": d.activate_status}


# ── Helpers ───────────────────────────────────────────────────────────────

def json_dumps(obj: Any) -> str:
    import json
    return json.dumps(obj, ensure_ascii=False)


# ── Tool definitions (schemas for LLM) ────────────────────────────────────

CHAT_TOOLS = [
    {
        "name": "im.v1.chat.create",
        "description": "Create a Feishu/Lark group chat. Returns the chat_id.",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Group chat name"},
                "description": {
            "type": "string",
            "description": "Group description",
            "default": "",
        },
            },
            "required": ["name"],
        },
        "handler": _create_chat,
    },
    {
        "name": "im.v1.chat.members.create",
        "description": "Add members to a Feishu/Lark group chat by open_id.",
        "parameters": {
            "type": "object",
            "properties": {
                "chat_id": {"type": "string", "description": "Target chat ID"},
                "open_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of user open_ids to add",
                },
            },
            "required": ["chat_id", "open_ids"],
        },
        "handler": _add_members_to_chat,
    },
    {
        "name": "im.v1.chat.get",
        "description": "Get information about a Feishu/Lark group chat.",
        "parameters": {
            "type": "object",
            "properties": {
                "chat_id": {"type": "string", "description": "Chat ID to query"},
            },
            "required": ["chat_id"],
        },
        "handler": _get_chat,
    },
    {
        "name": "im.v1.chat.link",
        "description": "Get the share link for a Feishu/Lark group chat.",
        "parameters": {
            "type": "object",
            "properties": {
                "chat_id": {"type": "string", "description": "Chat ID"},
            },
            "required": ["chat_id"],
        },
        "handler": _get_chat_link,
    },
]

MESSAGE_TOOLS = [
    {
        "name": "im.v1.message.create",
        "description": (
            "Send a message to a Feishu/Lark chat or user. "
            'Default msg_type is "text". For interactive cards, use msg_type="interactive" '
            "and pass the card JSON as content."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "receive_id": {"type": "string", "description": "Target chat_id or open_id"},
                "content": {"type": "string", "description": "Message content"},
                "msg_type": {
                    "type": "string",
                    "enum": ["text", "interactive"],
                    "description": 'Message type, default "text"',
                    "default": "text",
                },
                "receive_id_type": {
                    "type": "string",
                    "enum": ["chat_id", "open_id"],
                    "description": 'Receive ID type, default "chat_id"',
                    "default": "chat_id",
                },
            },
            "required": ["receive_id", "content"],
        },
        "handler": _send_message,
    },
]

DOCX_TOOLS = [
    {
        "name": "docx.v1.document.create",
        "description": "Create a Feishu/Lark Docx document. Returns the document_id and URL.",
        "parameters": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Document title"},
                "content": {"type": "string", "description": "Initial content", "default": ""},
            },
            "required": ["title"],
        },
        "handler": _create_document,
    },
]

BOT_TOOLS = [
    {
        "name": "im.v1.bot.info",
        "description": "Get information about the current bot (name, app_id, status).",
        "parameters": {"type": "object", "properties": {}},
        "handler": _get_bot_info,
    },
]

ALL_TOOLS = CHAT_TOOLS + MESSAGE_TOOLS + DOCX_TOOLS + BOT_TOOLS
