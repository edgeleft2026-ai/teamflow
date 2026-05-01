"""Feishu API tools — callable by the Agent Executor via ToolProvider.

Each tool is an async function decorated with ``@tool_provider.register_func()``.
The lark-oapi SDK is used under the hood; credentials are read from the global
``feishu_client`` which must be initialized before any tool is called.
"""

from __future__ import annotations

import logging
import threading
from typing import Any

logger = logging.getLogger(__name__)

_client_lock = threading.Lock()
_feishu_client: Any = None
_clients_by_thread: dict[int, Any] = {}


def init_feishu_client(app_id: str, app_secret: str, brand: str = "feishu") -> None:
    """Initialize the Feishu client. Call once at startup."""
    global _feishu_client
    import lark_oapi as lark

    base_url = (
        "https://open.feishu.cn"
        if brand == "feishu"
        else "https://open.larksuite.com"
    )
    client = lark.Client.builder() \
        .app_id(app_id) \
        .app_secret(app_secret) \
        .domain(base_url) \
        .log_level(lark.LogLevel.INFO) \
        .build()
    with _client_lock:
        _feishu_client = client
    logger.info("飞书客户端已初始化 (brand=%s)", brand)


def get_client() -> Any:
    """Return the Feishu client, creating a thread-local copy if needed.

    Threads that call this from a worker context get their own client
    instance to avoid potential event-loop conflicts with async SDK usage.
    """
    with _client_lock:
        if _feishu_client is None:
            raise RuntimeError(
                "Feishu client not initialized. Call init_feishu_client() first."
            )
        # In the main thread, return the shared instance directly
        if threading.current_thread() is threading.main_thread():
            return _feishu_client

    # Worker threads get a thread-local copy
    tid = threading.get_ident()
    with _client_lock:
        if tid not in _clients_by_thread:
            import lark_oapi as lark
            _clients_by_thread[tid] = lark.Client.builder() \
                .app_id(_feishu_client.app_id) \
                .app_secret(_feishu_client.app_secret) \
                .domain(_feishu_client.domain) \
                .log_level(lark.LogLevel.INFO) \
                .build()
        return _clients_by_thread[tid]


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
    resp = get_client().im.v1.chat.create(req)
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

    body = lark.im.v1.CreateChatMembersRequestBody.builder().id_list(open_ids).build()
    req = (
        lark.im.v1.CreateChatMembersRequest.builder()
        .chat_id(chat_id)
        .member_id_type("open_id")
        .request_body(body)
        .build()
    )
    resp = get_client().im.v1.chat_members.create(req)
    if not resp.success():
        raise RuntimeError(f"Add members failed: {resp.msg} ({resp.code})")
    return {"chat_id": chat_id, "added_count": len(open_ids)}


async def _get_chat(chat_id: str) -> dict:
    """Get Feishu group chat info."""
    import lark_oapi as lark
    req = lark.im.v1.GetChatRequest.builder().chat_id(chat_id).build()
    resp = get_client().im.v1.chat.get(req)
    if not resp.success():
        raise RuntimeError(f"Get chat failed: {resp.msg} ({resp.code})")
    d = resp.data
    return {"chat_id": chat_id, "name": d.name, "description": d.description}


async def _get_chat_link(chat_id: str) -> dict:
    """Get share link for a Feishu group chat."""
    import lark_oapi as lark

    body = lark.im.v1.LinkChatRequestBody.builder().build()
    req = lark.im.v1.LinkChatRequest.builder().chat_id(chat_id).request_body(body).build()
    resp = get_client().im.v1.chat.link(req)
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
    resp = get_client().im.v1.message.create(req)
    if not resp.success():
        raise RuntimeError(f"Send message failed: {resp.msg} ({resp.code})")
    return {"message_id": resp.data.message_id, "chat_id": resp.data.chat_id}


# ── Docx tools ──────────────────────────────────────────────────────────


async def _create_document(title: str, content: str = "") -> dict:
    """Create a Feishu Docx document.

    Note: the SDK's CreateDocumentRequestBody only supports title and folder_token.
    Content must be written separately via the document block API after creation.
    """
    import lark_oapi as lark

    body = lark.docx.v1.CreateDocumentRequestBody.builder() \
        .title(title) \
        .build()
    req = lark.docx.v1.CreateDocumentRequest.builder() \
        .request_body(body) \
        .build()
    resp = get_client().docx.v1.document.create(req)
    if not resp.success():
        raise RuntimeError(f"Create document failed: {resp.msg} ({resp.code})")
    d = resp.data
    doc_url = f"https://{_open_domain()}/docx/{d.document.document_id}"
    return {"document_id": d.document.document_id, "title": d.document.title, "url": doc_url}


async def _add_document_collaborator(document_id: str, open_id: str) -> dict:
    """Add a collaborator (full access) to a document, so the admin can manage it.

    Feishu documents created by the bot are owned by the bot
    unless we explicitly share them with the admin.
    """
    import json
    from urllib.request import Request, urlopen

    token_req = Request(
        f"{get_client()._config.domain}/open-apis/auth/v3/tenant_access_token/internal",
        data=json.dumps({
            "app_id": get_client()._config.app_id,
            "app_secret": get_client()._config.app_secret,
        }).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urlopen(token_req, timeout=10) as resp:
        token_data = json.loads(resp.read().decode("utf-8"))
    access_token = token_data.get("tenant_access_token")
    if not access_token:
        raise RuntimeError("Failed to get tenant access token")

    body = json.dumps({
        "member_type": "openid",
        "member_id": open_id,
        "perm": "full_access",
    }).encode("utf-8")
    url = (
        f"{get_client()._config.domain}/open-apis/drive/v1/permissions/"
        f"{document_id}/members?type=docx"
    )
    req = Request(url, data=body, headers={
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    })
    with urlopen(req, timeout=10) as resp:
        result = json.loads(resp.read().decode("utf-8"))

    if result.get("code") != 0:
        raise RuntimeError(f"Add collaborator failed: {result.get('msg', 'unknown')}")
    return {"document_id": document_id, "collaborator": open_id}


async def _transfer_document_owner(document_id: str, open_id: str) -> dict:
    """Transfer document ownership to the specified admin user."""
    import lark_oapi as lark

    owner = lark.drive.v1.Owner.builder() \
        .member_type("openid") \
        .member_id(open_id) \
        .build()
    req = lark.drive.v1.TransferOwnerPermissionMemberRequest.builder() \
        .token(document_id) \
        .type("docx") \
        .need_notification(False) \
        .remove_old_owner(False) \
        .old_owner_perm("full_access") \
        .request_body(owner) \
        .build()
    resp = get_client().drive.v1.permission_member.transfer_owner(req)
    if not resp.success():
        raise RuntimeError(f"Transfer document owner failed: {resp.msg} ({resp.code})")
    return {"document_id": document_id, "owner_open_id": open_id}


def _open_domain() -> str:
    """Return the Feishu/Lark user-facing domain.

    open.feishu.cn is the API domain, not the document viewing domain.
    feishu.cn auto-redirects to the correct tenant subdomain.
    """
    domain = get_client()._config.domain
    if "larksuite" in domain:
        return "larksuite.com"
    return "feishu.cn"


# ── Bot info tool (for testing) ───────────────────────────────────────────


async def _get_bot_info() -> dict:
    """Get bot information via direct HTTP (not wrapped in lark-oapi SDK client)."""
    import json
    from urllib.request import Request, urlopen

    token_req = Request(
        f"{get_client()._config.domain}/open-apis/auth/v3/tenant_access_token/internal",
        data=json.dumps({
            "app_id": get_client()._config.app_id,
            "app_secret": get_client()._config.app_secret,
        }).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urlopen(token_req, timeout=10) as resp:
        token_data = json.loads(resp.read().decode("utf-8"))
    access_token = token_data.get("tenant_access_token")
    if not access_token:
        raise RuntimeError("Failed to get tenant access token for bot info")

    bot_req = Request(
        f"{get_client()._config.domain}/open-apis/bot/v3/info",
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        },
    )
    with urlopen(bot_req, timeout=10) as resp:
        bot_data = json.loads(resp.read().decode("utf-8"))
    bot = bot_data.get("bot", {})
    return {
        "bot_name": bot.get("app_name", ""),
        "app_id": bot.get("app_id", ""),
        "activate_status": bot.get("activate_status", 0),
    }


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
    {
        "name": "drive.v1.permission.add_collaborator",
        "description": (
            "Add a collaborator to a Feishu document with full access permission. "
            "Use this after creating a document to share it with the project admin "
            "so they can manage it."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "document_id": {"type": "string", "description": "Document ID to share"},
                "open_id": {"type": "string", "description": "User open_id to add as collaborator"},
            },
            "required": ["document_id", "open_id"],
        },
        "handler": _add_document_collaborator,
    },
]

async def _run_lark_cli(command: str, args: list[str]) -> dict:
    """Execute a lark-cli command via subprocess (in thread to avoid blocking).

    Uses the same feishu credentials as the SDK client.

    Args:
        command: lark-cli command. One of: im, contact, calendar, drive, task,
                 docs, sheets, base, approval, wiki, minutes, vc, mail, okr.
        args: CLI arguments, e.g. ["+search-user", "--query", "John"].
    """
    import asyncio

    from teamflow.config import FeishuConfig
    from teamflow.execution.cli import find_cli_binary
    from teamflow.execution.cli import run_cli as _run_cli_core

    fconfig = get_client()._config
    feishu_cfg = FeishuConfig(
        app_id=fconfig.app_id,
        app_secret=fconfig.app_secret,
        brand="feishu" if "feishu" in str(fconfig.domain) else "lark",
    )
    binary = find_cli_binary("lark-cli")
    cli_args = [command] + args
    result = await asyncio.to_thread(
        _run_cli_core, cli_args, feishu=feishu_cfg, cli_binary=binary, timeout=30,
    )
    if not result.success:
        return {"success": False, "error": result.error or "CLI command failed"}
    return {"success": True, "output": result.output or {}, "stderr": result.stderr_log}


BOT_TOOLS = [
    {
        "name": "im.v1.bot.info",
        "description": "Get information about the current bot (name, app_id, status).",
        "parameters": {"type": "object", "properties": {}},
        "handler": _get_bot_info,
    },
]

CLI_TOOLS = [
    {
        "name": "lark_cli.run",
        "description": (
            "Execute a lark-cli command via subprocess. "
            "Use this for Feishu operations that don't have a dedicated SDK tool. "
            "Available commands: im, contact, calendar, drive, task, docs, sheets, base, "
            "approval, wiki, minutes, vc, mail, okr. "
            "Each command has subcommands (prefixed with +) and API operations. "
            "Example: command='contact', args=['+search-user', '--query', 'John']. "
            "IMPORTANT: Never use destructive operations (delete, remove members) without "
            "explicit user confirmation."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": (
                        "lark-cli top-level command. One of: im, contact, calendar, drive, "
                        "task, docs, sheets, base, approval, wiki, minutes, vc, mail, okr"
                    ),
                },
                "args": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "CLI arguments for the command. E.g. for 'im': ['+messages-send', "
                        "'--chat-id', 'oc_xxx', '--text', 'hello']. "
                        "For 'contact': ['+search-user', '--query', 'name']. "
                        "Use '--help' to discover available subcommands."
                    ),
                },
            },
            "required": ["command", "args"],
        },
        "handler": _run_lark_cli,
    },
]

ALL_TOOLS = CHAT_TOOLS + MESSAGE_TOOLS + DOCX_TOOLS + BOT_TOOLS + CLI_TOOLS
