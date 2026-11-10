"""Centralized loguru configuration for ai-agents backends (canon)."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

from loguru import logger

from app.redaction import redact_text

__all__ = ["configure_logging", "logger"]

_configured = False
_configured_dir: str | None = None

_CONSOLE_FORMAT = (
    "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | "
    "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>"
)
_FILE_FORMAT = "{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}"

# Third-party DEBUG streams (aiosqlite, SQLAlchemy, HTTP clients) otherwise
# flood the daily file with thousands of lines per request.
_NOISY_LOGGERS = (
    "aiosqlite",
    "sqlalchemy.engine",
    "sqlalchemy.pool",
    "sqlalchemy.dialects",
    "sqlalchemy.orm",
    "httpx",
    "httpcore",
    "openai",
    "urllib3",
    "watchfiles",
    "asyncio",
    "multipart",
    "mcp",
    "langchain",
    "langgraph",
)


class InterceptHandler(logging.Handler):
    """Route stdlib logging records into loguru."""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        frame, depth = logging.currentframe(), 2
        while frame and frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back
            depth += 1

        logger.opt(depth=depth, exception=record.exc_info).log(level, record.getMessage())


def configure_logging(
    level: str = "INFO",
    *,
    json: bool = False,
    logs_dir: str = "logs",
    file_level: str = "DEBUG",
    file_rotation: str = "00:00",
    file_retention: str = "30 days",
    file_compression: str | None = "zip",
) -> None:
    """Initialize loguru sinks and intercept stdlib loggers (idempotent per dir)."""
    global _configured, _configured_dir
    target_dir = str(Path(logs_dir).resolve())
    if _configured and _configured_dir == target_dir:
        return

    normalized = (level or "INFO").upper()
    logger.remove()
    logger.configure(
        patcher=lambda record: record.update(
            message=redact_text(record.get("message", ""))
        )
    )

    logs_dir_path = Path(logs_dir)
    logs_dir_path.mkdir(parents=True, exist_ok=True)

    if json:
        logger.add(sys.stdout, level=normalized, serialize=True)
    else:
        logger.add(sys.stdout, level=normalized, format=_CONSOLE_FORMAT, colorize=True)

    logger.add(
        logs_dir_path / "app_{time:YYYY-MM-DD}.log",
        rotation=file_rotation,
        retention=file_retention,
        compression=file_compression,
        level=file_level,
        format=_FILE_FORMAT,
        backtrace=False,
        diagnose=False,
    )

    logging.basicConfig(handlers=[InterceptHandler()], level=0, force=True)

    for name in ("uvicorn", "uvicorn.error", "uvicorn.access", "fastapi", "sqlalchemy", "alembic"):
        stdlib_logger = logging.getLogger(name)
        stdlib_logger.handlers = [InterceptHandler()]
        stdlib_logger.propagate = False

    for name in _NOISY_LOGGERS:
        logging.getLogger(name).setLevel(logging.WARNING)

    _configured = True
    _configured_dir = target_dir
