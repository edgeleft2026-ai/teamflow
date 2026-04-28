"""TeamFlow CLI entry point."""

from __future__ import annotations

import sys


def main() -> None:
    args = sys.argv[1:]
    if not args or args[0] in ("-h", "--help"):
        print("Usage: teamflow <command>")
        print()
        print("Commands:")
        print("  setup   Configure Feishu credentials (QR scan or manual)")
        print("  run     Start TeamFlow event loop")
        sys.exit(0 if args else 1)

    command = args[0]
    if command == "setup":
        from teamflow.setup.cli import setup
        setup()
    elif command == "run":
        from teamflow.main import main as run_main
        import asyncio
        asyncio.run(run_main())
    else:
        print(f"Unknown command: {command}")
        print("Commands: setup, run")
        sys.exit(1)


if __name__ == "__main__":
    main()
