"""TeamFlow setup CLI command."""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

from .feishu import probe_bot, qr_register


def _save_config(config_path: Path, app_id: str, app_secret: str, brand: str) -> None:
    """Write credentials to config.yaml."""
    config = {
        "feishu": {
            "app_id": app_id,
            "app_secret": app_secret,
            "brand": brand,
        }
    }
    config_path.parent.mkdir(parents=True, exist_ok=True)
    with open(config_path, "w", encoding="utf-8") as f:
        yaml.dump(config, f, default_flow_style=False, allow_unicode=True)
    print(f"\n  Credentials saved to {config_path}")


def _manual_setup(config_path: Path) -> bool:
    """Manual credential input fallback."""
    print("\n--- Manual Setup ---")
    print("Enter your Feishu/Lark app credentials.")
    print("(Create an app at https://open.feishu.cn/app or https://open.larksuite.com/app)\n")

    app_id = input("  App ID: ").strip()
    app_secret = input("  App Secret: ").strip()
    if not app_id or not app_secret:
        print("  App ID and App Secret are required.")
        return False

    print("\n  Select platform:")
    print("  1) Feishu (飞书, China)")
    print("  2) Lark (International)")
    choice = input("  Choice [1]: ").strip() or "1"
    brand = "feishu" if choice == "1" else "lark"

    print("\n  Verifying credentials...")
    bot_info = probe_bot(app_id, app_secret, brand)
    if bot_info:
        print(f"  Bot: {bot_info['bot_name']} (open_id: {bot_info['bot_open_id']})")
    else:
        print("  Warning: Could not verify bot. Credentials will be saved anyway.")

    _save_config(config_path, app_id, app_secret, brand)
    return True


def setup(config_path: Path | None = None) -> None:
    """Run the TeamFlow setup wizard."""
    if config_path is None:
        config_path = Path("config.yaml")

    print("=" * 50)
    print("  TeamFlow Setup")
    print("=" * 50)

    # Check for existing config
    if config_path.exists():
        print(f"\n  Existing config found at {config_path}")
        overwrite = input("  Overwrite? [y/N]: ").strip().lower()
        if overwrite != "y":
            print("  Setup cancelled.")
            return

    print("\n  Choose setup method:")
    print("  1) Scan QR code (recommended, auto-creates Feishu app)")
    print("  2) Enter credentials manually")
    choice = input("\n  Choice [1]: ").strip() or "1"

    if choice == "1":
        print("\n  Starting QR registration...")
        result = qr_register()
        if result:
            _save_config(config_path, result["app_id"], result["app_secret"], result["domain"])
            print("\n  Setup complete! Run TeamFlow with:")
            print(f"    python -m teamflow.main")
        else:
            print("\n  QR registration failed.")
            fallback = input("  Try manual setup? [Y/n]: ").strip().lower()
            if fallback != "n":
                _manual_setup(config_path)
    elif choice == "2":
        _manual_setup(config_path)
    else:
        print("  Invalid choice.")
        return

    print()
