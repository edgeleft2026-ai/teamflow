"""Feishu/Lark QR scan-to-create registration.

Adapted from hermes-agent (gateway/platforms/feishu.py).
Uses Feishu's device-code flow at /oauth/v1/app/registration:
user scans a QR code with the Feishu mobile app, and the platform
creates a bot application automatically, returning app_id + app_secret.
"""

from __future__ import annotations

import json
import logging
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)

_ACCOUNTS_URLS = {
    "feishu": "https://accounts.feishu.cn",
    "lark": "https://accounts.larksuite.com",
}
_OPEN_URLS = {
    "feishu": "https://open.feishu.cn",
    "lark": "https://open.larksuite.com",
}
_REGISTRATION_PATH = "/oauth/v1/app/registration"
_REQUEST_TIMEOUT = 10


def _post_registration(base_url: str, body: dict[str, str]) -> dict:
    """POST form-encoded data to the registration endpoint."""
    url = f"{base_url}{_REGISTRATION_PATH}"
    data = urlencode(body).encode("utf-8")
    req = Request(url, data=data, headers={"Content-Type": "application/x-www-form-urlencoded"})
    try:
        with urlopen(req, timeout=_REQUEST_TIMEOUT) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except HTTPError as exc:
        body_bytes = exc.read()
        if body_bytes:
            try:
                return json.loads(body_bytes.decode("utf-8"))
            except (ValueError, json.JSONDecodeError):
                raise exc from None
        raise


def _init_registration(domain: str) -> None:
    """Verify the environment supports client_secret auth."""
    base_url = _ACCOUNTS_URLS.get(domain, _ACCOUNTS_URLS["feishu"])
    res = _post_registration(base_url, {"action": "init"})
    methods = res.get("supported_auth_methods") or []
    if "client_secret" not in methods:
        msg = f"Registration does not support client_secret auth. Supported: {methods}"
        raise RuntimeError(msg)


# TeamFlow 需要的全部飞书权限，从 lark-cli 源码 shortcuts/ 提取的全部 bot scopes。
_TEAMFLOW_SCOPES = [
    # IM — 消息与群聊
    "im:message",
    "im:message:send_as_bot",
    "im:message:read",
    "im:message:readonly",
    "im:message.group_msg",
    "im:message.p2p_msg:readonly",
    "im:chat:create",
    "im:chat:read",
    "im:chat:update",
    "im:resource",
    # 通讯录
    "contact:user.base:readonly",
    "contact:user.basic_profile:readonly",
    "contact:contact.base:readonly",
    "contact:contact:read",
    "contact:user:search",
    # 云文档
    "docx:document:create",
    "docx:document:readonly",
    "docx:document:write_only",
    "docs:document.content:read",
    "docs:document.media:download",
    "docs:document.media:upload",
    "docs:document.comment:create",
    "docs:document.comment:write_only",
    "docs:document:export",
    "docs:document:import",
    "docs:permission.member:create",
    "docs:permission.member:transfer",
    "docs:permission.member:apply",
    # 云空间
    "drive:drive:read",
    "drive:drive.metadata:readonly",
    "drive:file:upload",
    "drive:file:download",
    "space:folder:create",
    "space:document:move",
    "space:document:shortcut",
    "space:document:delete",
    # 日历
    "calendar:calendar:read",
    "calendar:calendar.event:create",
    "calendar:calendar.event:read",
    "calendar:calendar.event:update",
    "calendar:calendar.event:reply",
    "calendar:calendar.free_busy:read",
    # 任务
    "task:task:read",
    "task:task:write",
    "task:tasklist:read",
    "task:tasklist:write",
    "task:comment:write",
    # 多维表格
    "base:app:create",
    "base:app:read",
    "base:app:update",
    "base:app:copy",
    "base:table:create",
    "base:table:read",
    "base:table:update",
    "base:table:delete",
    "base:field:create",
    "base:field:read",
    "base:field:update",
    "base:field:delete",
    "base:record:create",
    "base:record:read",
    "base:record:update",
    "base:record:delete",
    "base:view:read",
    "base:view:write_only",
    "base:dashboard:create",
    "base:dashboard:read",
    "base:dashboard:update",
    "base:dashboard:delete",
    "base:form:create",
    "base:form:read",
    "base:form:update",
    "base:form:delete",
    "base:role:create",
    "base:role:read",
    "base:role:update",
    "base:role:delete",
    "base:history:read",
    "base:workflow:create",
    "base:workflow:read",
    "base:workflow:update",
    # 电子表格
    "sheets:spreadsheet:create",
    "sheets:spreadsheet:read",
    "sheets:spreadsheet:write_only",
    # 幻灯片
    "slides:presentation:create",
    "slides:presentation:update",
    "slides:presentation:write_only",
    # 画板
    "board:whiteboard:node:create",
    "board:whiteboard:node:read",
    # 知识库
    "wiki:space:read",
    "wiki:space:write_only",
    "wiki:node:create",
    "wiki:node:read",
    "wiki:node:move",
    # 视频会议
    "vc:meeting.meetingevent:read",
    "vc:meeting.search:read",
    "vc:note:read",
    "vc:record:readonly",
    # 妙记
    "minutes:minutes:readonly",
    "minutes:minutes.search:read",
    "minutes:minutes.artifacts:read",
    "minutes:minutes.media:export",
    "minutes:minutes.transcript:export",
    # OKR
    "okr:okr.content:readonly",
    "okr:okr.period:readonly",
    # 邮箱
    "mail:user_mailbox:readonly",
    "mail:user_mailbox.message:readonly",
    "mail:user_mailbox.message:send",
    "mail:user_mailbox.message:modify",
    "mail:user_mailbox.message.body:read",
    "mail:user_mailbox.message.subject:read",
    "mail:user_mailbox.message.address:read",
    "mail:user_mailbox.folder:read",
    "mail:user_mailbox.event.mail_address:read",
    "mail:event",
    # 搜索
    "search:docs:read",
    "search:message",
]

_TEAMFLOW_SCOPE_STRING = " ".join(_TEAMFLOW_SCOPES)


def _begin_registration(domain: str) -> dict:
    """Start the device-code flow. Returns device_code, qr_url, etc.

    Note: 飞书的 scope 参数对新注册的应用部分权限（如 im:chat）需要
    人工审核，不会在扫码时直接弹出。注册完成后通过 get_permission_url()
    生成的链接可一键跳转到后台开通。
    """
    base_url = _ACCOUNTS_URLS.get(domain, _ACCOUNTS_URLS["feishu"])
    res = _post_registration(base_url, {
        "action": "begin",
        "archetype": "PersonalAgent",
        "auth_method": "client_secret",
        "request_user_info": "open_id tenant_brand",
    })
    device_code = res.get("device_code")
    if not device_code:
        raise RuntimeError("Registration did not return a device_code")
    qr_url = res.get("verification_uri_complete", "")
    if "?" in qr_url:
        qr_url += "&from=teamflow&tp=teamflow"
    else:
        qr_url += "?from=teamflow&tp=teamflow"
    return {
        "device_code": device_code,
        "qr_url": qr_url,
        "user_code": res.get("user_code", ""),
        "interval": res.get("interval") or 5,
        "expire_in": res.get("expire_in") or 600,
    }


def get_permission_url(app_id: str, brand: str = "feishu") -> str:
    """生成飞书应用权限配置页面的直达链接。

    链接只包含最核心的权限（URL 长度限制），完整列表在终端输出。
    """
    open_url = _OPEN_URLS.get(brand, _OPEN_URLS["feishu"])
    # 只放核心权限到 URL，避免参数过长
    core = [
        "im:message", "im:message:send_as_bot", "im:chat:create",
        "im:message.group_msg", "im:resource",
        "contact:user.base:readonly", "contact:user:search",
        "docx:document:create", "docx:document:readonly",
        "drive:drive:read", "drive:file:upload",
        "calendar:calendar:read", "calendar:calendar.event:create",
        "task:task:read", "task:task:write",
        "base:app:create", "base:table:read", "base:record:create",
        "wiki:space:read", "wiki:node:create",
        "vc:meeting.meetingevent:read",
        "minutes:minutes:readonly",
        "mail:user_mailbox:readonly",
    ]
    scope_param = ",".join(core)
    return (
        f"{open_url}/app/{app_id}/auth"
        f"?q={scope_param}&op_from=openapi&token_type=tenant"
    )


def get_all_scopes() -> list[str]:
    """返回完整的权限列表（终端输出用）。"""
    return list(_TEAMFLOW_SCOPES)


def _poll_registration(
    device_code: str,
    interval: int,
    expire_in: int,
    domain: str,
) -> dict | None:
    """Poll until the user scans the QR code. Returns credentials on success."""
    deadline = time.time() + expire_in
    current_domain = domain
    poll_count = 0

    while time.time() < deadline:
        base_url = _ACCOUNTS_URLS.get(current_domain, _ACCOUNTS_URLS["feishu"])
        try:
            res = _post_registration(base_url, {
                "action": "poll",
                "device_code": device_code,
                "tp": "ob_app",
            })
        except (URLError, OSError, json.JSONDecodeError):
            time.sleep(interval)
            continue

        poll_count += 1
        if poll_count == 1:
            print("  Waiting for scan result...", end="", flush=True)
        elif poll_count % 6 == 0:
            print(".", end="", flush=True)

        # Domain auto-detection
        user_info = res.get("user_info") or {}
        tenant_brand = user_info.get("tenant_brand")
        if tenant_brand == "lark" and current_domain != "lark":
            current_domain = "lark"

        # Success
        if res.get("client_id") and res.get("client_secret"):
            if poll_count > 0:
                print()
            return {
                "app_id": res["client_id"],
                "app_secret": res["client_secret"],
                "domain": current_domain,
                "open_id": user_info.get("open_id"),
            }

        # Terminal errors
        error = res.get("error", "")
        if error in ("access_denied", "expired_token"):
            if poll_count > 0:
                print()
            logger.warning("注册失败: %s", error)
            return None

        time.sleep(interval)

    if poll_count > 0:
        print()
    logger.warning("注册超时 (%d秒)", expire_in)
    return None


def _render_qr(url: str) -> bool:
    """Try to render a QR code in the terminal."""
    try:
        import qrcode
        qr = qrcode.QRCode()
        qr.add_data(url)
        qr.make(fit=True)
        qr.print_ascii(invert=True)
        return True
    except ImportError:
        return False
    except Exception:
        return False


def probe_bot(app_id: str, app_secret: str, domain: str) -> dict | None:
    """Verify bot connectivity via /open-apis/bot/v3/info.

    Returns {"bot_name": ..., "bot_open_id": ...} on success.
    """
    open_url = _OPEN_URLS.get(domain, _OPEN_URLS["feishu"])
    try:
        # Get tenant_access_token
        token_data = json.dumps({"app_id": app_id, "app_secret": app_secret}).encode("utf-8")
        token_req = Request(
            f"{open_url}/open-apis/auth/v3/tenant_access_token/internal",
            data=token_data,
            headers={"Content-Type": "application/json"},
        )
        with urlopen(token_req, timeout=_REQUEST_TIMEOUT) as resp:
            token_res = json.loads(resp.read().decode("utf-8"))

        access_token = token_res.get("tenant_access_token")
        if not access_token:
            return None

        # Get bot info
        bot_req = Request(
            f"{open_url}/open-apis/bot/v3/info",
            headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
        )
        with urlopen(bot_req, timeout=_REQUEST_TIMEOUT) as resp:
            bot_res = json.loads(resp.read().decode("utf-8"))

        bot_info = bot_res.get("bot", {})
        if not bot_info:
            return None
        return {
            "bot_name": bot_info.get("app_name", ""),
            "bot_open_id": bot_info.get("open_id", ""),
        }
    except (URLError, OSError, KeyError, json.JSONDecodeError) as exc:
        logger.debug("机器人探测失败: %s", exc)
        return None


def qr_register(*, initial_domain: str = "feishu") -> dict | None:
    """Run the full QR scan-to-create registration flow.

    Returns {"app_id", "app_secret", "domain", "open_id", "bot_name", "bot_open_id"}
    or None on failure.
    """
    domain = initial_domain

    print("\n[1/3] Initializing registration...")
    try:
        _init_registration(domain)
    except Exception as exc:
        print(f"  Failed: {exc}")
        return None

    print("[2/3] Generating QR code...")
    try:
        reg = _begin_registration(domain)
    except Exception as exc:
        print(f"  Failed: {exc}")
        return None

    qr_url = reg["qr_url"]
    print("\n  Scan the QR code below with your Feishu/Lark mobile app:")
    print(f"  (Or open: {qr_url})\n")
    if not _render_qr(qr_url):
        print(f"  URL: {qr_url}\n")

    print("[3/3] Waiting for scan...")
    result = _poll_registration(
        device_code=reg["device_code"],
        interval=reg["interval"],
        expire_in=reg["expire_in"],
        domain=domain,
    )
    if not result:
        return None

    # Probe bot
    print("  Verifying bot connection...")
    bot_info = probe_bot(result["app_id"], result["app_secret"], result["domain"])
    if bot_info:
        result["bot_name"] = bot_info["bot_name"]
        result["bot_open_id"] = bot_info["bot_open_id"]
        print(f"  Bot: {bot_info['bot_name']} (open_id: {bot_info['bot_open_id']})")
    else:
        print("  Warning: Could not verify bot (credentials saved anyway)")

    return result
