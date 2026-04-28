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
from http.client import HTTPResponse
from typing import Any
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
        raise RuntimeError(f"Registration does not support client_secret auth. Supported: {methods}")


def _begin_registration(domain: str) -> dict:
    """Start the device-code flow. Returns device_code, qr_url, etc."""
    base_url = _ACCOUNTS_URLS.get(domain, _ACCOUNTS_URLS["feishu"])
    res = _post_registration(base_url, {
        "action": "begin",
        "archetype": "PersonalAgent",
        "auth_method": "client_secret",
        "request_user_info": "open_id",
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
            logger.warning("Registration %s", error)
            return None

        time.sleep(interval)

    if poll_count > 0:
        print()
    logger.warning("Registration timed out after %ds", expire_in)
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
        logger.debug("Bot probe failed: %s", exc)
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
    print(f"\n  Scan the QR code below with your Feishu/Lark mobile app:")
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
