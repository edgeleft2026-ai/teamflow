from __future__ import annotations

import asyncio
import logging
import os
import signal
import subprocess
import sys
from pathlib import Path

from teamflow.access import EventDispatcher, EventFileWatcher, FeishuEvent, is_bot_message
from teamflow.config import load_config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("teamflow")

DEFAULT_EVENT_TYPES = ",".join([
    "im.message.receive_v1",
])

DEFAULT_OUTPUT_DIR = "tmp/teamflow/events"


def start_event_subscriber(
    feishu_app_id: str,
    feishu_app_secret: str,
    feishu_brand: str,
    output_dir: str,
    event_types: str | None = None,
    cli_binary: str = "lark-cli",
) -> subprocess.Popen:
    """Start lark-cli event +subscribe as a long-running subprocess."""
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    cmd = [
        cli_binary,
        "event", "+subscribe",
        "--event-types", event_types or DEFAULT_EVENT_TYPES,
        "--compact",
        "--output-dir", str(output_path),
    ]

    env = dict(os.environ)
    env["LARKSUITE_CLI_APP_ID"] = feishu_app_id
    env["LARKSUITE_CLI_APP_SECRET"] = feishu_app_secret
    env["LARKSUITE_CLI_BRAND"] = feishu_brand

    logger.info("Starting event subscriber: %s", " ".join(cmd))
    proc = subprocess.Popen(
        cmd,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return proc


def handle_message_event(event: FeishuEvent) -> None:
    """Basic handler for im.message.receive_v1 events."""
    from teamflow.access.parser import extract_chat_id, extract_message_text, extract_open_id

    text = extract_message_text(event)
    chat_id = extract_chat_id(event)
    open_id = extract_open_id(event)

    logger.info(
        "Message received: chat=%s user=%s text=%s",
        chat_id,
        open_id,
        (text or "")[:100],
    )


async def run_health_server(host: str = "127.0.0.1", port: int = 8080) -> None:
    """Simple health check server using only stdlib."""
    from http.server import HTTPServer, BaseHTTPRequestHandler

    class HealthHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/health":
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(b'{"status":"ok"}')
            else:
                self.send_response(404)
                self.end_headers()

        def log_message(self, format, *args):
            logger.debug("Health server: %s", format % args)

    server = HTTPServer((host, port), HealthHandler)
    server.serve_forever()


async def main() -> None:
    config = load_config()
    feishu = config.feishu

    logger.info("TeamFlow starting (app_id=%s, brand=%s)", feishu.app_id[:8] + "...", feishu.brand)

    # Resolve paths
    cli_binary = os.getenv("LARK_CLI_BINARY", "lark-cli")
    output_dir = os.getenv("TEAMFLOW_EVENT_DIR", DEFAULT_OUTPUT_DIR)
    event_types = os.getenv("TEAMFLOW_EVENT_TYPES", None)

    # Start event subscriber subprocess
    subscriber = start_event_subscriber(
        feishu_app_id=feishu.app_id,
        feishu_app_secret=feishu.app_secret,
        feishu_brand=feishu.brand,
        output_dir=output_dir,
        event_types=event_types,
        cli_binary=cli_binary,
    )
    logger.info("Event subscriber started (pid=%d)", subscriber.pid)

    # Set up event dispatcher
    dispatcher = EventDispatcher()
    dispatcher.on("im.message.receive_v1", handle_message_event)

    # Log all events
    def log_event(event: FeishuEvent) -> None:
        logger.info("Event: %s (id=%s)", event.event_type, event.event_id[:16] if event.event_id else "?")

    dispatcher.on_any(log_event)

    # Start file watcher
    watcher = EventFileWatcher(Path(output_dir))

    # Start health check server
    health_port = int(os.getenv("TEAMFLOW_HEALTH_PORT", "8080"))
    health_task = asyncio.create_task(run_health_server(port=health_port))
    logger.info("Health check at http://127.0.0.1:%d/health", health_port)

    # Shutdown signal
    stop_event = asyncio.Event()

    def signal_handler(sig, frame):
        logger.info("Received signal %s, shutting down...", sig)
        stop_event.set()

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Main loop: watch events
    async def watch_loop():
        await watcher.watch(lambda line: dispatcher.dispatch_raw(line))

    watch_task = asyncio.create_task(watch_loop())

    # Wait for shutdown signal or subscriber exit
    try:
        while not stop_event.is_set():
            # Check if subscriber is still alive
            retcode = subscriber.poll()
            if retcode is not None:
                stdout = subscriber.stdout.read() if subscriber.stdout else ""
                stderr = subscriber.stderr.read() if subscriber.stderr else ""
                logger.error(
                    "Event subscriber exited (code=%d). stdout=%s stderr=%s",
                    retcode,
                    stdout[:200],
                    stderr[:500],
                )
                break
            await asyncio.sleep(1)
    finally:
        logger.info("Shutting down...")
        watcher.stop()
        watch_task.cancel()
        health_task.cancel()
        if subscriber.poll() is None:
            subscriber.terminate()
            try:
                subscriber.wait(timeout=5)
            except subprocess.TimeoutExpired:
                subscriber.kill()
        logger.info("TeamFlow stopped.")


if __name__ == "__main__":
    asyncio.run(main())
