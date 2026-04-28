from __future__ import annotations

import asyncio
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class EventFileWatcher:
    """Watch a directory for new NDJSON event files written by lark-cli.

    lark-cli event +subscribe with --output-dir writes events to files.
    This watcher uses OS-level file change events (via asyncio + polling)
    to detect new content.
    """

    def __init__(self, watch_dir: Path, poll_interval: float = 0.5):
        self.watch_dir = watch_dir
        self.poll_interval = poll_interval
        self._file_positions: dict[str, int] = {}
        self._running = False

    async def watch(self, callback) -> None:
        """Start watching for new events. Calls callback(parsed_line) for each new line.

        callback receives a raw NDJSON string line.
        """
        self._running = True
        self.watch_dir.mkdir(parents=True, exist_ok=True)

        logger.info("Watching event directory: %s", self.watch_dir)

        while self._running:
            try:
                await self._scan_files(callback)
            except Exception:
                logger.exception("Error scanning event files")
            await asyncio.sleep(self.poll_interval)

    def stop(self) -> None:
        self._running = False

    async def _scan_files(self, callback) -> None:
        for path in sorted(self.watch_dir.rglob("*.ndjson")):
            await self._read_new_lines(path, callback, multiline=False)
        # Also check for plain json files (route-based output)
        for path in sorted(self.watch_dir.rglob("*.json")):
            await self._read_new_lines(path, callback, multiline=True)

    async def _read_new_lines(self, path: Path, callback, *, multiline: bool = False) -> None:
        key = str(path)
        try:
            stat = path.stat()
        except OSError:
            return

        offset = self._file_positions.get(key, 0)
        if stat.st_size <= offset:
            return

        try:
            with open(path, encoding="utf-8") as f:
                f.seek(offset)
                if multiline:
                    content = f.read().strip()
                    if content:
                        callback(content)
                else:
                    for line in f:
                        line = line.strip()
                        if line:
                            callback(line)
                self._file_positions[key] = f.tell()
        except OSError:
            logger.debug("Failed to read event file %s", path)


def list_existing_events(watch_dir: Path) -> list[str]:
    """Read all existing events from the watch directory.

    Useful for catching up on events that occurred before the watcher started.
    """
    lines: list[str] = []
    for path in sorted(watch_dir.rglob("*.ndjson")):
        _read_all_lines(path, lines, multiline=False)
    for path in sorted(watch_dir.rglob("*.json")):
        _read_all_lines(path, lines, multiline=True)
    return lines


def _read_all_lines(path: Path, lines: list[str], *, multiline: bool = False) -> None:
    try:
        content = path.read_text(encoding="utf-8").strip()
        if not content:
            return
        if multiline:
            lines.append(content)
        else:
            for line in content.splitlines():
                line = line.strip()
                if line:
                    lines.append(line)
    except OSError:
        pass
