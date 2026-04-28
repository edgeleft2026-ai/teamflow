"""TeamFlow 交互式设置向导。"""

from __future__ import annotations

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


def setup(config_path: Path | None = None) -> dict | None:
    """运行 TeamFlow 设置向导。返回配置信息或 None。"""
    if config_path is None:
        config_path = Path("config.yaml")

    print()
    print("=" * 50)
    print("  TeamFlow 设置向导")
    print("=" * 50)

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
