"""TeamFlow 交互式设置向导。"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import questionary
import yaml

from .feishu import probe_bot, qr_register

_CUSTOM_STYLE = questionary.Style(
    [
        ("qmark", "fg:#673ab7 bold"),
        ("question", "bold"),
        ("answer", "fg:#f44336 bold"),
        ("pointer", "fg:#673ab7 bold"),
        ("highlighted", "fg:#673ab7 bold"),
        ("selected", "fg:#cc5454"),
        ("separator", "fg:#cc5454"),
        ("instruction", ""),
    ]
)

# Provider/model data is sourced from ai/model_registry (aligned with hermes-agent).
# This ensures setup wizard stays in sync with the canonical lists.
def _get_provider_choices() -> list[tuple]:
    """Build provider choices from model_registry.CANONICAL_PROVIDERS."""
    from teamflow.ai.model_registry import CANONICAL_PROVIDERS as CP

    return [(p.label, p.slug, p.desc, p.api_mode, p.primary_env_var) for p in CP]


def _get_provider_models() -> dict[str, list[str]]:
    """Return model lists from model_registry._PROVIDER_MODELS."""
    from teamflow.ai.model_registry import _PROVIDER_MODELS as PM

    return dict(PM)


def _get_provider_entry(provider_id: str):
    """Look up provider entry from model_registry."""
    from teamflow.ai.model_registry import get_provider_entry

    return get_provider_entry(provider_id)


_ENV_PATH = Path(".env")


def _save_env_value(key: str, value: str) -> None:
    """Save or update a key=value pair in .env file (project root)."""
    key = key.strip()
    value = value.replace("\n", "").replace("\r", "")
    lines: list[str] = []
    found = False
    if _ENV_PATH.exists():
        lines = _ENV_PATH.read_text(encoding="utf-8").splitlines(keepends=False)
    new_lines = []
    for line in lines:
        if line.startswith(f"{key}=") or line.startswith(f"export {key}="):
            new_lines.append(f"{key}={value}")
            found = True
        else:
            new_lines.append(line)
    if not found:
        new_lines.append(f"{key}={value}")
    _ENV_PATH.write_text("\n".join(new_lines).rstrip("\n") + "\n", encoding="utf-8")


def _prompt_credential(provider_id: str) -> None:
    """Prompt user for API key if not already set in env.

    借鉴 hermes-agent _model_flow_api_key_provider() 的凭证处理流程。
    保存时使用 LiteLLM 能识别的环境变量名和 base URL。
    """

    from teamflow.ai.model_registry import (
        get_litellm_base_url_override,
        get_litellm_env,
    )

    entry = _get_provider_entry(provider_id)
    if entry is None:
        return

    # OAuth / external process providers — skip key input
    if entry.auth_type in ("oauth_device_code", "oauth_external", "external_process"):
        print(f"  ⚠ {entry.label} 需要浏览器登录认证（非 API Key）。")
        print(f"    运行 hermes 或参照 {entry.label} 文档完成认证。")
        print()
        return

    # Get the LiteLLM-compatible env var name
    litellm_env = get_litellm_env(provider_id) or entry.primary_env_var

    # Check if any env var (hermes or LiteLLM) already has a value
    all_envs = list(entry.env_vars) + ([litellm_env] if litellm_env not in entry.env_vars else [])
    for env_var in all_envs:
        val = os.environ.get(env_var, "")
        if val:
            masked = val[:4] + "****" + val[-4:] if len(val) > 8 else "****"
            print(f"  ✓ 检测到 {env_var}={masked}")
            return

    # No env var set — prompt user
    if not litellm_env:
        return

    print(f"  {entry.label} 需要设置 API Key。")
    print(f"  (获取地址请查阅 {entry.label} 官方文档)")
    print()
    try:
        new_key = questionary.password(
            f"请输入 {litellm_env}（输入不可见）：",
            style=_CUSTOM_STYLE,
        ).ask()
        if new_key is not None:
            new_key = new_key.strip()
    except (KeyboardInterrupt, EOFError):
        print("\n  已取消。将跳过 API Key 设置。")
        return

    if not new_key:
        print("  已跳过。你可以稍后手动设置环境变量。")
        return

    # Save using LiteLLM-compatible env var name
    _save_env_value(litellm_env, new_key)
    os.environ[litellm_env] = new_key

    # Also set base URL override if needed (e.g. MiniMax CN vs global)
    base_url = get_litellm_base_url_override(provider_id)
    if base_url:
        base_env = litellm_env.replace("API_KEY", "API_BASE")
        _save_env_value(base_env, base_url)
        os.environ[base_env] = base_url
        print(f"  ✓ API Key 已保存: {litellm_env}=****")
        print(f"  ✓ Base URL: {base_env}={base_url}")
    else:
        masked = new_key[:4] + "****" + new_key[-4:] if len(new_key) > 8 else "****"
        print(f"  ✓ API Key 已保存: {litellm_env}={masked}")
    print()


def _save_config(
    config_path: Path,
    app_id: str,
    app_secret: str,
    brand: str,
    admin_open_id: str = "",
    agent_provider: str = "",
    fast_model: str = "openai/gpt-4o-mini",
    smart_model: str = "openai/gpt-4o",
    reasoning_model: str = "openai/gpt-4o",
    api_mode: str = "",
    max_iterations: int = 10,
    timeout_seconds: int = 120,
    gitea_base_url: str = "",
    gitea_access_token: str = "",
    gitea_default_private: bool = True,
    gitea_auto_create: bool = True,
) -> None:
    config = {
        "feishu": {
            "app_id": app_id,
            "app_secret": app_secret,
            "brand": brand,
            "admin_open_id": admin_open_id,
        },
        "agent": {
            "provider": agent_provider,
            "api_mode": api_mode,
            "fast_model": fast_model,
            "smart_model": smart_model,
            "reasoning_model": reasoning_model,
            "max_iterations": max_iterations,
            "timeout_seconds": timeout_seconds,
        },
    }
    if gitea_base_url or gitea_access_token:
        config["gitea"] = {
            "base_url": gitea_base_url,
            "access_token": gitea_access_token,
            "default_private": gitea_default_private,
            "auto_create": gitea_auto_create,
        }
    config_path.parent.mkdir(parents=True, exist_ok=True)
    with open(config_path, "w", encoding="utf-8") as f:
        yaml.dump(config, f, default_flow_style=False, allow_unicode=True)
    print(f"  配置已保存到 {config_path}")


def _qr_setup() -> dict | None:
    print("\n  [1/3] 初始化注册...")
    try:
        result = qr_register()
    except Exception as exc:
        print(f"  注册失败: {exc}")
        return None

    if result:
        admin_open_id = result.get("open_id", "")
        if admin_open_id:
            print(f"  管理员 open_id: {admin_open_id}")
        return result
    return None


def _manual_setup() -> dict | None:
    print("\n  --- 手动配置 ---")
    print("  请输入飞书应用凭证")
    print("  (在 https://open.feishu.cn/app 创建应用)\n")

    app_id = input("  App ID: ").strip()
    app_secret = input("  App Secret: ").strip()
    if not app_id or not app_secret:
        print("  App ID 和 App Secret 为必填项。")
        return None

    brand = questionary.select(
        "请选择平台：",
        choices=[
            questionary.Choice("飞书（国内）", "feishu"),
            questionary.Choice("Lark（国际）", "lark"),
        ],
        style=_CUSTOM_STYLE,
    ).ask()
    if brand is None:
        return None

    print("\n  正在验证凭证...")
    bot_info = probe_bot(app_id, app_secret, brand)
    if bot_info:
        print(f"  机器人: {bot_info['bot_name']} (open_id: {bot_info['bot_open_id']})")
    else:
        print("  警告：无法验证凭证，配置将仍然保存。")

    return {"app_id": app_id, "app_secret": app_secret, "domain": brand, "open_id": ""}


def _check_lark_cli() -> str | None:
    """检查 lark-cli 是否可用，返回路径或 None。"""
    resolved = shutil.which("lark-cli")
    if resolved:
        return resolved

    # 检查常见 npm 全局安装路径
    candidates = []
    if os.name == "nt":
        for env_var in ("LOCALAPPDATA", "APPDATA"):
            val = os.environ.get(env_var)
            if val:
                candidates.append(os.path.join(val, "npm", "lark-cli.exe"))
        prog_files = os.environ.get("ProgramFiles")
        if prog_files:
            candidates.append(os.path.join(prog_files, "nodejs", "lark-cli.exe"))
    else:
        candidates.extend([
            "/usr/local/bin/lark-cli",
            "/usr/bin/lark-cli",
            os.path.expanduser("~/.npm-global/bin/lark-cli"),
            os.path.expanduser("~/.local/bin/lark-cli"),
        ])
        npm_prefix = os.environ.get("NPM_CONFIG_PREFIX") or os.environ.get("npm_config_prefix")
        if npm_prefix:
            candidates.append(os.path.join(npm_prefix, "bin", "lark-cli"))

    for candidate in candidates:
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate
    return None


def _install_lark_cli_guide() -> bool:
    """引导用户安装 lark-cli，返回是否安装成功。"""
    print("\n  [环境检查] 未检测到 lark-cli，TeamFlow 依赖它操作飞书。")
    print("  安装方式：")
    print("    1. 先安装 Node.js (https://nodejs.org) 16+")
    if os.name == "nt":
        print("    2. 打开 PowerShell / CMD，执行：")
        print("       npm install -g @larksuite/cli")
        print("       npx skills add larksuite/cli -y -g")
    else:
        print("    2. 在终端执行：")
        print("       npm install -g @larksuite/cli")
        print("       npx skills add larksuite/cli -y -g")

    # 尝试检测 npm 是否存在
    npm_cmd = "npm"
    if os.name == "nt":
        npm_cmd = shutil.which("npm") or "npm"

    has_npm = shutil.which("npm") is not None

    if has_npm:
        do_install = questionary.confirm(
            "  检测到 npm，是否立即自动安装 lark-cli？",
            default=True,
            style=_CUSTOM_STYLE,
        ).ask()
        if do_install:
            print("\n  正在安装 @larksuite/cli ...")
            try:
                subprocess.run(
                    [npm_cmd, "install", "-g", "@larksuite/cli"],
                    check=True,
                    capture_output=True,
                    text=True,
                )
                print("  正在安装 Skills ...")
                subprocess.run(
                    [npm_cmd, "exec", "--yes", "skills", "add", "larksuite/cli", "-y", "-g"],
                    check=True,
                    capture_output=True,
                    text=True,
                )
                # 重新检测
                found = _check_lark_cli()
                if found:
                    print(f"  lark-cli 安装成功: {found}")
                    return True
                else:
                    print("  安装完成但未能检测到 lark-cli，请检查 PATH 配置。")
                    return False
            except subprocess.CalledProcessError as exc:
                print(f"  安装失败: {exc}")
                if exc.stderr:
                    print(f"  错误信息: {exc.stderr[:500]}")
                return False
    else:
        print("  未检测到 npm，请先安装 Node.js 后再试。")

    return False


def _to_litellm_model_id(provider_id: str, model_name: str) -> str:
    """Convert internal provider+model to LiteLLM-compatible model string."""
    from teamflow.ai.model_registry import to_litellm_model
    return to_litellm_model(provider_id, model_name)


def _build_model_choices(provider_id: str, tier: str) -> list:
    """Build questionary choices for models from registry's _PROVIDER_MODELS."""
    all_models = _get_provider_models().get(provider_id, [])
    choices: list = []
    for i, mid in enumerate(all_models):
        label = f"{mid} — 推荐" if i == 0 else mid
        # Use LiteLLM-compatible model ID as the value
        llm_id = _to_litellm_model_id(provider_id, mid)
        choices.append(questionary.Choice(label, llm_id))
    if not choices:
        choices.append(questionary.Choice("自定义输入", "__custom__"))
    else:
        choices.append(questionary.Choice("自定义（手动输入模型名）", "__custom__"))
    return choices


def _prompt_custom_model(provider_id: str, default: str) -> str | None:
    """Prompt user to enter a custom model identifier."""
    return questionary.text(
        f"请输入模型名（如 {default}）：",
        default=default,
        style=_CUSTOM_STYLE,
    ).ask()


def _llm_setup() -> tuple[str, str, str, str] | None:
    """Interactive LLM provider-first setup.

    借鉴 hermes-agent select_provider_and_model() 的流程：
    1. 先选提供商 (provider)
    2. 再根据提供商选 smart / fast / reasoning 模型
    3. 支持自定义提供商和模型

    Returns (provider, fast_model, smart_model, reasoning_model) or None.
    """
    print()
    print("-" * 50)
    print("  LLM 服务商与模型配置")
    print("-" * 50)
    print("  TeamFlow 需要 LLM 来驱动 AI Agent。")
    print()

    do_configure = questionary.confirm(
        "是否配置 LLM？（可以跳过，默认使用 OpenAI GPT-4o）",
        default=True,
        style=_CUSTOM_STYLE,
    ).ask()
    if not do_configure:
        return ("openai", "openai/gpt-4o-mini", "openai/gpt-4o", "openai/gpt-4o")

    # ═══ Step 1: 选择 LLM 服务商 ═══
    provider_choices = [
        questionary.Choice(f"{name}  — {desc}", pid)
        for name, pid, desc, _api_mode, _env_var in _get_provider_choices()
    ]
    provider_choices.append(questionary.Choice("其他（手动输入 provider 和模型）", "__custom__"))

    print("  [1/4] 选择 LLM 服务商：")
    provider_id = questionary.select(
        "服务商：",
        choices=provider_choices,
        style=_CUSTOM_STYLE,
    ).ask()
    if provider_id is None:
        return None

    if provider_id == "__custom__":
        provider_id = questionary.text(
            "请输入 provider ID（如 openai, deepseek, anthropic）：",
            default="openai",
            style=_CUSTOM_STYLE,
        ).ask()
        if not provider_id:
            return None

    # ═══ Step 1.5: API Key 凭证设置 ═══
    _prompt_credential(provider_id)

    # ═══ Step 2: 选择 smart 模型 ═══
    print("\n  [2/4] 选择主模型（Agent 任务执行）：")
    smart_choices = _build_model_choices(provider_id, "smart")
    if not smart_choices[:-1]:
        smart_choices = [questionary.Choice("自定义输入", "__custom__")]
    smart_model_short = questionary.select(
        "主模型（smart）：",
        choices=smart_choices,
        style=_CUSTOM_STYLE,
    ).ask()
    if smart_model_short is None:
        return None

    if smart_model_short == "__custom__":
        custom = _prompt_custom_model(
            provider_id, "openai/gpt-4o" if provider_id == "openai" else ""
        )
        if not custom:
            return None
        smart_model = custom if "/" in custom else _to_litellm_model_id(provider_id, custom)
    else:
        smart_model = smart_model_short

    # ═══ Step 3: 选择 fast 模型 ═══
    print("\n  [3/4] 选择快速模型（简单摘要、命令响应）：")
    fast_choices = _build_model_choices(provider_id, "fast")
    fast_choices.insert(
        0, questionary.Choice(f"与主模型相同 ({smart_model})", smart_model)
    )
    if not fast_choices[:-1]:
        fast_choices = [
            questionary.Choice(f"与主模型相同 ({smart_model})", smart_model),
            questionary.Choice("自定义输入", "__custom__"),
        ]
    fast_model = questionary.select(
        "快速模型（fast）：",
        choices=fast_choices,
        style=_CUSTOM_STYLE,
    ).ask()
    if fast_model is None:
        return None

    if fast_model == "__custom__":
        custom = _prompt_custom_model(provider_id, smart_model)
        if not custom:
            return None
        fast_model = custom if "/" in custom else _to_litellm_model_id(provider_id, custom)

    # ═══ Step 4: 选择 reasoning 模型 ═══
    print("\n  [4/4] 选择推理模型（复杂分析、多约束判断）：")
    reasoning_choices = _build_model_choices(provider_id, "reasoning")
    reasoning_choices.insert(
        0, questionary.Choice(f"与主模型相同 ({smart_model}) — 推荐", smart_model)
    )
    if not reasoning_choices[:-1]:
        reasoning_choices = [
            questionary.Choice(f"与主模型相同 ({smart_model}) — 推荐", smart_model),
            questionary.Choice("自定义输入", "__custom__"),
        ]
    reasoning_model = questionary.select(
        "推理模型（reasoning）：",
        choices=reasoning_choices,
        style=_CUSTOM_STYLE,
    ).ask()
    if reasoning_model is None:
        return None

    if reasoning_model == "__custom__":
        custom = _prompt_custom_model(provider_id, smart_model)
        if not custom:
            return None
        reasoning_model = custom if "/" in custom else _to_litellm_model_id(provider_id, custom)

    return (provider_id, fast_model, smart_model, reasoning_model)


def _gitea_setup() -> dict | None:
    """Interactive Gitea configuration.

    Returns a dict with gitea config keys or None if skipped.
    """
    print()
    print("-" * 50)
    print("  Gitea 代码仓库配置")
    print("-" * 50)
    print("  配置 Gitea 后，创建项目时可自动创建代码仓库。")
    print("  如不配置，创建项目时需手动输入仓库地址。")
    print()

    do_configure = questionary.confirm(
        "是否配置 Gitea？（可跳过，后续手动编辑 config.yaml）",
        default=False,
        style=_CUSTOM_STYLE,
    ).ask()
    if not do_configure:
        return None

    base_url = questionary.text(
        "Gitea 服务地址：",
        default="https://git.lighter.games",
        style=_CUSTOM_STYLE,
    ).ask()
    if not base_url:
        return None
    base_url = base_url.rstrip("/")

    access_token = questionary.password(
        "Access Token（输入不可见）：",
        style=_CUSTOM_STYLE,
    ).ask()
    if not access_token:
        print("  未输入 Token，跳过 Gitea 配置。")
        return None

    default_private = questionary.confirm(
        "默认创建私有仓库？",
        default=True,
        style=_CUSTOM_STYLE,
    ).ask()

    auto_create = questionary.confirm(
        "项目创建时自动创建仓库？（未填写仓库地址时）",
        default=True,
        style=_CUSTOM_STYLE,
    ).ask()

    print("\n  正在验证 Gitea 连接...")
    try:
        import asyncio

        from teamflow.config.settings import GiteaConfig
        from teamflow.git.gitea_service import GiteaService

        cfg = GiteaConfig(base_url=base_url, access_token=access_token)
        svc = GiteaService(cfg)

        async def _validate():
            valid = await svc.check_token()
            username = ""
            if valid:
                user = await svc.get_current_user()
                username = user.username
            await svc.close()
            return valid, username

        valid, username = asyncio.run(_validate())
        if valid:
            print(f"  ✓ 连接成功，用户: {username}")
        else:
            print("  ✗ Token 验证失败，请检查地址和 Token。")
            retry = questionary.confirm(
                "是否重新输入？",
                default=True,
                style=_CUSTOM_STYLE,
            ).ask()
            if retry:
                return _gitea_setup()
            return None
    except Exception as exc:
        print(f"  ✗ 连接失败: {exc}")
        retry = questionary.confirm(
            "是否重新输入？",
            default=True,
            style=_CUSTOM_STYLE,
        ).ask()
        if retry:
            return _gitea_setup()
        return None

    return {
        "base_url": base_url,
        "access_token": access_token,
        "default_private": default_private,
        "auto_create": auto_create,
    }


def setup(config_path: Path | None = None) -> dict | None:
    """运行 TeamFlow 设置向导。返回配置信息或 None。"""
    if config_path is None:
        config_path = Path("config.yaml")

    print()
    print("=" * 50)
    print("  TeamFlow 设置向导")
    print("=" * 50)

    # 环境依赖检查
    lark_cli_path = _check_lark_cli()
    if not lark_cli_path:
        ok = _install_lark_cli_guide()
        if not ok:
            print("\n  lark-cli 未就绪，无法继续设置。请手动安装后重试。")
            sys.exit(1)
    else:
        print(f"  [环境检查] lark-cli 已就绪: {lark_cli_path}")

    # 检查已有配置
    if config_path.exists():
        overwrite = questionary.confirm(
            f"检测到已有配置文件 ({config_path})，是否覆盖？",
            default=False,
            style=_CUSTOM_STYLE,
        ).ask()
        if not overwrite:
            print("  设置已取消。")
            return None

    # 选择设置方式
    method = questionary.select(
        "请选择设置方式：",
        choices=[
            questionary.Choice("扫码注册（推荐，自动创建飞书应用）", "qr"),
            questionary.Choice("手动输入凭证", "manual"),
        ],
        style=_CUSTOM_STYLE,
    ).ask()
    if method is None:
        return None

    # 执行飞书设置
    if method == "qr":
        result = _qr_setup()
        if result is None:
            fallback = questionary.confirm(
                "扫码注册失败，是否尝试手动配置？",
                default=True,
                style=_CUSTOM_STYLE,
            ).ask()
            if fallback:
                result = _manual_setup()
    else:
        result = _manual_setup()

    if result is None:
        return None

    # LLM 模型设置
    llm = _llm_setup()
    agent_provider = ""
    fast_model = "openai/gpt-4o-mini"
    smart_model = "openai/gpt-4o"
    reasoning_model = "openai/gpt-4o"
    if llm is not None:
        agent_provider, fast_model, smart_model, reasoning_model = llm

    # Gitea 代码仓库设置
    gitea = _gitea_setup()
    gitea_base_url = ""
    gitea_access_token = ""
    gitea_default_private = True
    gitea_auto_create = True
    if gitea is not None:
        gitea_base_url = gitea["base_url"]
        gitea_access_token = gitea["access_token"]
        gitea_default_private = gitea["default_private"]
        gitea_auto_create = gitea["auto_create"]

    # 保存配置
    _save_config(
        config_path,
        result["app_id"],
        result["app_secret"],
        result["domain"],
        result.get("open_id", ""),
        agent_provider=agent_provider,
        fast_model=fast_model,
        smart_model=smart_model,
        reasoning_model=reasoning_model,
        gitea_base_url=gitea_base_url,
        gitea_access_token=gitea_access_token,
        gitea_default_private=gitea_default_private,
        gitea_auto_create=gitea_auto_create,
    )

    print("\n  设置完成！")
    from teamflow.ai.model_registry import get_litellm_env
    litellm_env = get_litellm_env(agent_provider) or ""
    _print_next_steps(
        result.get("bot_name", ""),
        provider_id=agent_provider,
        env_var=litellm_env,
        app_id=result.get("app_id", ""),
    )
    return result


def _print_next_steps(
    bot_name: str, provider_id: str = "", env_var: str = "", app_id: str = "",
) -> None:
    """Print post-setup guidance with provider-specific hints and permission links."""
    from teamflow.setup.feishu import get_permission_url

    print()
    print("  下一步：")
    if env_var:
        val = os.environ.get(env_var, "")
        if not val:
            print(f"    1. 设置 API Key（已保存到 .env，启动时自动加载）：{env_var}")
        else:
            print(f"    1. API Key 已配置 ({env_var})")
    else:
        print("    1. 确保 API Key 已配置")

    if app_id:
        from teamflow.setup.feishu import get_all_scopes
        perm_url = get_permission_url(app_id)
        all_scopes = get_all_scopes()
        print("    2. ⚠️ 开通应用权限:")
        print(f"       链接: {perm_url}")
        print(f"       (链接含核心权限，共 {len(all_scopes)} 项权限，")
        print( "        在飞书后台搜索并逐一开通即可)")

    print("    3. 运行: teamflow run")
    if bot_name:
        print(f"    4. 在飞书中找到 '{bot_name}' 并发送消息")
    print()


def ensure_config(config_path: Path | None = None) -> bool:
    """检查配置是否存在，不存在则自动进入设置向导。

    返回 True 表示配置就绪，False 表示未完成设置。
    """
    if config_path is None:
        config_path = Path("config.yaml")

    if config_path.exists():
        return True

    print("\n  未检测到配置文件，正在进入设置向导...\n")
    result = setup(config_path)
    return result is not None
