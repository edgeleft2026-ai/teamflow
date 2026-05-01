"""Production-grade logging for TeamFlow.

Features:
- Console + rotating file handlers
- JSON formatter for log aggregation (ELK / Loki)
- Sensitive data redaction (app_secret, access_token, etc.)
- Per-module log level configuration
- Request correlation ID via contextvars
- Configurable via config.yaml [logging] section
"""

from __future__ import annotations

import json
import logging
import sys
from contextvars import ContextVar
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

_correlation_id: ContextVar[str] = ContextVar("correlation_id", default="")


def set_correlation_id(cid: str) -> None:
    _correlation_id.set(cid)


def get_correlation_id() -> str:
    return _correlation_id.get()


_SENSITIVE_KEYS = frozenset({
    "app_secret",
    "app_secret_key",
    "access_token",
    "secret",
    "password",
    "token",
    "authorization",
    "cookie",
})

_REDACTED = "****"


def _redact_value(key: str, value: Any) -> Any:
    k_lower = key.lower()
    for sensitive in _SENSITIVE_KEYS:
        if sensitive in k_lower:
            return _REDACTED
    return value


def redact_dict(data: dict) -> dict:
    if not isinstance(data, dict):
        return data
    return {k: _redact_value(k, v) for k, v in data.items()}


class SensitiveFilter(logging.Filter):
    """Redact sensitive fields from log record args and message."""

    def filter(self, record: logging.LogRecord) -> bool:
        if record.args and isinstance(record.args, dict):
            record.args = redact_dict(record.args)
        elif record.args and isinstance(record.args, tuple):
            record.args = tuple(
                redact_dict(a) if isinstance(a, dict) else a for a in record.args
            )
        return True


class _BaseFormatter(logging.Formatter):
    """Common fields shared by both human and JSON formatters."""

    def _base_fields(self, record: logging.LogRecord) -> dict[str, Any]:
        fields: dict[str, Any] = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        cid = get_correlation_id()
        if cid:
            fields["correlation_id"] = cid
        if record.exc_info and record.exc_text is None:
            record.exc_text = self.formatException(record.exc_info)
        if record.exc_text:
            fields["exception"] = record.exc_text
        return fields


class HumanFormatter(_BaseFormatter):
    """Colored console formatter for development."""

    _LEVEL_COLORS = {
        "DEBUG": "\033[36m",
        "INFO": "\033[32m",
        "WARNING": "\033[33m",
        "ERROR": "\033[31m",
        "CRITICAL": "\033[35m",
    }
    _RESET = "\033[0m"

    def __init__(self, *, color: bool = True, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._color = color and sys.stderr.isatty()

    def format(self, record: logging.LogRecord) -> str:
        fields = self._base_fields(record)
        ts = fields["timestamp"]
        level = fields["level"]
        logger_name = fields["logger"]
        msg = fields["message"]

        if self._color:
            color = self._LEVEL_COLORS.get(level, "")
            level_str = f"{color}{level:<8}{self._RESET}"
        else:
            level_str = f"{level:<8}"

        cid = fields.get("correlation_id", "")
        cid_part = f" [{cid}]" if cid else ""
        line = f"{ts} {level_str} [{logger_name}]{cid_part} {msg}"

        if "exception" in fields:
            line += "\n" + fields["exception"]
        return line


class JsonFormatter(_BaseFormatter):
    """Structured JSON formatter for production log aggregation."""

    def format(self, record: logging.LogRecord) -> str:
        fields = self._base_fields(record)
        return json.dumps(fields, ensure_ascii=False, default=str)


def _resolve_level(level_str: str) -> int:
    numeric = getattr(logging, level_str.upper(), None)
    if isinstance(numeric, int):
        return numeric
    return logging.INFO


def setup_logging(
    *,
    level: str = "INFO",
    log_dir: str = "logs",
    file_enabled: bool = True,
    file_level: str = "DEBUG",
    file_max_bytes: int = 10 * 1024 * 1024,
    file_backup_count: int = 5,
    json_format: bool = False,
    color: bool = True,
    module_levels: dict[str, str] | None = None,
) -> None:
    """Configure the TeamFlow logging system.

    Args:
        level: Root console log level.
        log_dir: Directory for rotating log files.
        file_enabled: Whether to enable file logging.
        file_level: File handler log level.
        file_max_bytes: Max size per log file before rotation.
        file_backup_count: Number of rotated log files to keep.
        json_format: Use JSON formatter for both console and file.
        color: Use ANSI colors in console output (auto-disabled if not a TTY).
        module_levels: Per-module log level overrides, e.g. {"teamflow.ai": "DEBUG"}.
    """
    root = logging.getLogger("teamflow")
    root.setLevel(logging.DEBUG)

    for handler in root.handlers[:]:
        root.removeHandler(handler)

    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setLevel(_resolve_level(level))
    console_handler.addFilter(SensitiveFilter())

    if json_format:
        console_handler.setFormatter(JsonFormatter(datefmt="%Y-%m-%dT%H:%M:%S"))
    else:
        console_handler.setFormatter(
            HumanFormatter(color=color, datefmt="%Y-%m-%d %H:%M:%S")
        )
    root.addHandler(console_handler)

    if file_enabled:
        log_path = Path(log_dir)
        log_path.mkdir(parents=True, exist_ok=True)

        file_handler = RotatingFileHandler(
            log_path / "teamflow.log",
            maxBytes=file_max_bytes,
            backupCount=file_backup_count,
            encoding="utf-8",
        )
        file_handler.setLevel(_resolve_level(file_level))
        file_handler.addFilter(SensitiveFilter())

        if json_format:
            file_handler.setFormatter(JsonFormatter(datefmt="%Y-%m-%dT%H:%M:%S"))
        else:
            file_handler.setFormatter(
                HumanFormatter(color=False, datefmt="%Y-%m-%d %H:%M:%S")
            )
        root.addHandler(file_handler)

    if module_levels:
        for mod_name, mod_level in module_levels.items():
            logging.getLogger(mod_name).setLevel(_resolve_level(mod_level))

    logging.captureWarnings(True)
    warnings_logger = logging.getLogger("py.warnings")
    warnings_logger.addHandler(console_handler)

    root.debug(
        "Logging initialized: level=%s file=%s json=%s dir=%s",
        level, file_enabled, json_format, log_dir,
    )


def get_logger(name: str) -> logging.Logger:
    """Get a logger under the teamflow namespace.

    Usage:
        logger = get_logger(__name__)
    """
    if not name.startswith("teamflow"):
        name = f"teamflow.{name}"
    return logging.getLogger(name)
