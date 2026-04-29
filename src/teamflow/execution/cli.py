from __future__ import annotations

import json
import logging
import os
import platform
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from teamflow.config import FeishuConfig

logger = logging.getLogger(__name__)

# Environment variable names used by lark-cli env credential provider.
_ENV_APP_ID = "LARKSUITE_CLI_APP_ID"
_ENV_APP_SECRET = "LARKSUITE_CLI_APP_SECRET"
_ENV_BRAND = "LARKSUITE_CLI_BRAND"
_ENV_TENANT_TOKEN = "LARKSUITE_CLI_TENANT_ACCESS_TOKEN"
_ENV_DEFAULT_AS = "LARKSUITE_CLI_DEFAULT_AS"

_OPEN_URLS = {
    "feishu": "https://open.feishu.cn",
    "lark": "https://open.larksuite.com",
}


@dataclass
class CLIResult:
    """Structured result from a lark-cli subprocess call."""

    success: bool
    output: dict | None = None
    error: str | None = None
    stderr_log: str = ""
    return_code: int = 0


@dataclass
class _CachedToken:
    token: str
    expires_at: float


_token_cache: dict[str, _CachedToken] = {}


def find_cli_binary(name: str = "lark-cli") -> str:
    """Find lark-cli binary in PATH or common install locations.

    Cross-platform resolution order:
    1. shutil.which(name)  — PATH lookup
    2. npm global prefix   — lark-cli installed via npm install -g @larksuite/cli
    3. Return name as-is   — let subprocess raise FileNotFoundError with a clear message
    """
    resolved = shutil.which(name)
    if resolved:
        return resolved

    # npm global binaries may not be on PATH in CI/container environments
    npm_prefix_candidates = []
    if os.name == "nt":
        # Windows: %APPDATA%\npm or %LOCALAPPDATA%\npm
        for env_var in ("LOCALAPPDATA", "APPDATA"):
            val = os.environ.get(env_var)
            if val:
                npm_prefix_candidates.append(os.path.join(val, "npm"))
        # Also check Node.js default install path
        prog_files = os.environ.get("ProgramFiles")
        if prog_files:
            npm_prefix_candidates.append(os.path.join(prog_files, "nodejs"))
    else:
        # Unix-like: /usr/local/bin, /usr/bin, ~/.npm-global/bin, ~/.local/bin
        npm_prefix_candidates.extend([
            "/usr/local/bin",
            "/usr/bin",
            os.path.expanduser("~/.npm-global/bin"),
            os.path.expanduser("~/.local/bin"),
        ])
        # Respect npm prefix if configured
        npm_prefix = os.environ.get("NPM_CONFIG_PREFIX") or os.environ.get("npm_config_prefix")
        if npm_prefix:
            npm_prefix_candidates.append(os.path.join(npm_prefix, "bin"))

    for directory in npm_prefix_candidates:
        candidate = os.path.join(directory, name)
        if os.name == "nt":
            for ext in (".exe", ".cmd", ".bat", ""):
                full = candidate + ext
                if os.path.isfile(full) and os.access(full, os.X_OK):
                    return full
        else:
            if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
                return candidate

    return name


def _exchange_tenant_token(feishu: FeishuConfig) -> str:
    """Exchange app_id + app_secret for tenant_access_token.

    Uses Feishu's /open-apis/auth/v3/tenant_access_token/internal endpoint.
    Caches the token with a 60s safety margin before expiry.
    """
    cache_key = feishu.app_id
    cached = _token_cache.get(cache_key)
    if cached and cached.expires_at > time.time():
        return cached.token

    open_url = _OPEN_URLS.get(feishu.brand, _OPEN_URLS["feishu"])
    url = f"{open_url}/open-apis/auth/v3/tenant_access_token/internal"
    body = json.dumps({"app_id": feishu.app_id, "app_secret": feishu.app_secret}).encode("utf-8")
    req = Request(url, data=body, headers={"Content-Type": "application/json"})

    with urlopen(req, timeout=10) as resp:
        result = json.loads(resp.read().decode("utf-8"))

    token = result.get("tenant_access_token")
    if not token:
        raise RuntimeError(f"Token exchange failed: {result.get('msg', 'unknown error')}")

    expire = result.get("expire", 7200)
    _token_cache[cache_key] = _CachedToken(token=token, expires_at=time.time() + expire - 60)
    logger.debug("Tenant token refreshed, expires in %ds", expire)
    return token


def _build_env(feishu: FeishuConfig, base_env: dict | None = None) -> dict:
    """Build subprocess environment with Feishu credentials and token injected."""
    env = dict(base_env or os.environ)
    env[_ENV_APP_ID] = feishu.app_id
    env[_ENV_APP_SECRET] = feishu.app_secret
    env[_ENV_BRAND] = feishu.brand

    token = _exchange_tenant_token(feishu)
    env[_ENV_TENANT_TOKEN] = token
    env[_ENV_DEFAULT_AS] = "bot"

    return env


def run_cli(
    args: list[str],
    feishu: FeishuConfig,
    cli_binary: str | None = None,
    timeout: int = 30,
) -> CLIResult:
    """Run a lark-cli command and return structured result.

    Args:
        args: CLI arguments, e.g. ["im", "+messages-send", "--chat-id", "xxx", "--text", "hello"]
        feishu: Feishu credential configuration
        cli_binary: Path to lark-cli binary (auto-detected if None)
        timeout: Subprocess timeout in seconds
    """
    binary = cli_binary or find_cli_binary()
    cmd = [binary, *args]
    env = _build_env(feishu)

    logger.debug("Running CLI: %s", " ".join(cmd))

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
        )
    except FileNotFoundError:
        platform_hint = ""
        if os.name != "nt":
            platform_hint = (
                " On Linux/macOS, install via: npm install -g @larksuite/cli"
            )
        return CLIResult(
            success=False,
            error=(
                f"CLI binary not found: {binary}. Install lark-cli and ensure it is in PATH."
                f"{platform_hint}"
            ),
        )
    except subprocess.TimeoutExpired:
        return CLIResult(success=False, error=f"CLI command timed out after {timeout}s")

    stderr_log = proc.stderr.strip()

    if proc.returncode != 0:
        return CLIResult(
            success=False,
            error=_extract_error(proc.stdout, stderr_log),
            stderr_log=stderr_log,
            return_code=proc.returncode,
        )

    output = _parse_stdout(proc.stdout)
    return CLIResult(
        success=True,
        output=output,
        stderr_log=stderr_log,
        return_code=0,
    )


def _parse_stdout(stdout: str) -> dict | None:
    """Try to parse CLI stdout as JSON. Return None if not JSON."""
    stdout = stdout.strip()
    if not stdout:
        return None
    try:
        return json.loads(stdout)
    except json.JSONDecodeError:
        return {"raw": stdout}


def _extract_error(stdout: str, stderr: str) -> str:
    """Extract a human-readable error message from CLI output."""
    for source in (stderr, stdout):
        text = source.strip()
        if text:
            try:
                data = json.loads(text)
                if isinstance(data, dict):
                    msg = data.get("msg") or data.get("message") or data.get("error")
                    if msg:
                        return str(msg)
            except json.JSONDecodeError:
                pass
            first_line = text.split("\n")[0]
            return first_line[:500]
    return "Unknown CLI error"
