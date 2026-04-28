"""TeamFlow CLI 入口。"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path


def main() -> None:
    args = sys.argv[1:]
    if not args or args[0] in ("-h", "--help"):
        print("用法: teamflow <命令>")
        print()
        print("命令:")
        print("  setup   设置向导（配置飞书凭证）")
        print("  run     启动 TeamFlow")
        print("  reset   重置配置和数据，从头开始")
        sys.exit(0 if args else 1)

    command = args[0]
    if command == "setup":
        _cmd_setup()
    elif command == "run":
        _cmd_run()
    elif command == "reset":
        _cmd_reset()
    else:
        print(f"未知命令: {command}")
        print("命令: setup, run, reset")
        sys.exit(1)


def _cmd_setup() -> None:
    """运行设置向导，完成后询问是否启动。"""
    import questionary

    from teamflow.setup.cli import setup

    result = setup()
    if result is None:
        return

    run_now = questionary.confirm(
        "是否立即启动 TeamFlow？",
        default=True,
    ).ask()
    if run_now:
        print()
        _start_app()


def _cmd_run() -> None:
    """启动应用，配置缺失时自动进入设置向导。"""
    from teamflow.setup.cli import ensure_config

    if not ensure_config():
        print("  设置未完成，无法启动。")
        sys.exit(1)

    _start_app()


def _start_app() -> None:
    """启动 TeamFlow 主进程。"""
    import asyncio

    from teamflow.main import main as run_main

    asyncio.run(run_main())


def _cmd_reset() -> None:
    """重置：删除配置、数据库和事件文件。"""
    paths = [
        Path("config.yaml"),
        Path("data/teamflow.db"),
        Path("tmp/teamflow/events"),
    ]
    removed = []
    for p in paths:
        if p.is_dir():
            shutil.rmtree(p, ignore_errors=True)
            removed.append(f"{p}/")
        elif p.exists():
            p.unlink()
            removed.append(str(p))

    if removed:
        print("已清除:")
        for r in removed:
            print(f"  - {r}")
    else:
        print("没有需要重置的内容。")

    print("\n运行 `teamflow setup` 重新开始设置。")


if __name__ == "__main__":
    main()
