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


def _save_config(
    config_path: Path,
    app_id: str,
    app_secret: str,
    brand: str,
    admin_open_id: str = "",
) -> None:
    config = {
        "feishu": {
            "app_id": app_id,
            "app_secret": app_secret,
            "brand": brand,
            "admin_open_id": admin_open_id,
        }
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

    # 执行设置
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

    # 保存配置
    _save_config(
        config_path,
        result["app_id"],
        result["app_secret"],
        result["domain"],
        result.get("open_id", ""),
    )

    print("\n  设置完成！")
    return result


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
