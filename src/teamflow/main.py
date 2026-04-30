from __future__ import annotations

import asyncio
import logging
import os
import signal
import subprocess
from pathlib import Path

from teamflow.access import EventDispatcher, EventFileWatcher, FeishuEvent, is_bot_message
from teamflow.access.callback import start_callback_thread
from teamflow.access.parser import (
    extract_chat_id,
    extract_message_text,
    extract_open_id,
)
from teamflow.config import load_config
from teamflow.execution.cli import find_cli_binary
from teamflow.orchestration.command_router import CommandRouter
from teamflow.storage.database import init_db

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
    # Clean old event files to avoid replaying stale events from previous runs
    if output_path.exists():
        for f in output_path.rglob("*"):
            if f.is_file():
                f.unlink(missing_ok=True)
    output_path.mkdir(parents=True, exist_ok=True)

    cmd = [
        cli_binary,
        "event", "+subscribe",
        "--event-types", event_types or DEFAULT_EVENT_TYPES,
        "--compact",
        "--output-dir", str(output_path),
        "--force",
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


def handle_message_event(event: FeishuEvent, router: CommandRouter, bot_app_id: str) -> None:
    """Handle im.message.receive_v1 events: filter bot messages, route to CommandRouter."""
    if is_bot_message(event, bot_app_id):
        return

    text = extract_message_text(event)
    chat_id = extract_chat_id(event)
    open_id = extract_open_id(event)

    if not text or not chat_id or not open_id:
        logger.warning("Incomplete message context, skipping")
        return

    logger.info("Message received: chat=%s user=%s text=%s", chat_id, open_id, text[:100])
    router.handle(text=text, open_id=open_id, chat_id=chat_id)


async def _start_health_server(host: str = "127.0.0.1", port: int = 8080):
    """Start health check server in a thread. Returns the HTTPServer instance."""
    import threading
    from http.server import BaseHTTPRequestHandler, HTTPServer

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
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


async def main() -> None:
    config = load_config()
    feishu = config.feishu

    logger.info("TeamFlow starting (app_id=%s, brand=%s)", feishu.app_id[:8] + "...", feishu.brand)

    # Initialize database
    init_db()
    logger.info("Database initialized")

    # Create command router
    router = CommandRouter(feishu)

    # Startup self-test: send notification to admin if configured
    if feishu.admin_open_id:
        from teamflow.execution.messages import send_card
        from teamflow.orchestration.card_templates import startup_card

        result = send_card(
            feishu,
            startup_card(),
            user_id=feishu.admin_open_id,
        )
        if result.success:
            logger.info("Startup self-test: message sent to admin OK")
        else:
            logger.error("Startup self-test FAILED: %s", result.error)
    else:
        logger.warning("admin_open_id not configured, skipping startup self-test")

    # Resolve paths
    cli_binary = os.getenv("LARK_CLI_BINARY")
    if not cli_binary:
        cli_binary = find_cli_binary("lark-cli")
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

    # Wait briefly and check subscriber health
    await asyncio.sleep(3)
    if subscriber.poll() is not None:
        stderr_output = subscriber.stderr.read() if subscriber.stderr else ""
        logger.error(
            "Event subscriber crashed immediately (code=%d): %s",
            subscriber.returncode,
            stderr_output[:500],
        )
        return
    logger.info("Event subscriber is running")

    # Initialize Agent tool provider with Feishu API client
    tool_provider = None
    try:
        from teamflow.ai import tool_provider as tp
        from teamflow.ai.tools.feishu import init_feishu_client

        init_feishu_client(
            app_id=feishu.app_id,
            app_secret=feishu.app_secret,
            brand=feishu.brand,
        )
        tool_provider = tp
        logger.info(
            "Agent smart channel ready (%d tools registered)",
            len(tool_provider.tools),
        )
    except Exception:
        logger.exception("Agent tool provider init failed, smart channel disabled")

    # Start card callback WebSocket client (handles card.action.trigger)
    start_callback_thread(
        app_id=feishu.app_id,
        app_secret=feishu.app_secret,
        brand=feishu.brand,
        router=router,
    )

    # Set up event dispatcher
    dispatcher = EventDispatcher()
    dispatcher.on("im.message.receive_v1", lambda e: handle_message_event(e, router, feishu.app_id))

    # Log all events
    def log_event(event: FeishuEvent) -> None:
        eid = event.event_id[:16] if event.event_id else "?"
        logger.info("Event: %s (id=%s)", event.event_type, eid)

    dispatcher.on_any(log_event)

    # Start file watcher
    watcher = EventFileWatcher(Path(output_dir))

    # Start health check server
    health_port = int(os.getenv("TEAMFLOW_HEALTH_PORT", "9090"))
    health_server = await _start_health_server(port=health_port)
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
        def on_raw_line(line: str) -> None:
            logger.info("Watcher read line: %s", line[:120])
            dispatcher.dispatch_raw(line)

        await watcher.watch(on_raw_line)

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
        health_server.shutdown()
        if tool_provider:
            try:
                await asyncio.wait_for(tool_provider.disconnect(), timeout=5)
            except Exception:
                logger.warning("Tool provider cleanup failed, forcing shutdown")
        if subscriber.poll() is None:
            subscriber.terminate()
            try:
                subscriber.wait(timeout=3)
            except subprocess.TimeoutExpired:
                subscriber.kill()
        logger.info("TeamFlow stopped.")
        os._exit(0)


if __name__ == "__main__":
    asyncio.run(main())
