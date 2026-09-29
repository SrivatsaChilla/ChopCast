"""Structured JSON / console logger factory.

See docs/MODULE_DESIGN.md §1.2 and docs/STANDARDS.md §8.
"""

from __future__ import annotations

import logging
import logging.handlers
import sys
from pathlib import Path
from typing import Any, Literal

import structlog

from chopcast.config import LoggingConfig


_configured = False


def configure(config: LoggingConfig, log_file_path: Path | None = None) -> None:
    """Configure the root logger exactly once per process.

    Safe to call multiple times; subsequent calls are no-ops.
    """
    global _configured
    if _configured:
        return

    level = getattr(logging, config.level.upper(), logging.INFO)

    handlers: list[logging.Handler] = []
    if config.destination in ("stdout", "both"):
        handlers.append(logging.StreamHandler(sys.stdout))
    if config.destination in ("file", "both") and log_file_path is not None:
        log_file_path.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(
            logging.handlers.RotatingFileHandler(
                log_file_path,
                maxBytes=config.rotate_max_bytes,
                backupCount=config.rotate_backup_count,
                encoding="utf-8",
            )
        )

    logging.basicConfig(
        level=level,
        format="%(message)s",
        handlers=handlers,
        force=True,
    )

    processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]
    if config.format == "json":
        processors.append(structlog.processors.JSONRenderer())
    else:  # console
        processors.append(structlog.dev.ConsoleRenderer(colors=sys.stdout.isatty()))

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )
    _configured = True


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """Return a bound logger for the given module name.

    Usage:
        log = get_logger(__name__)
        log.info("collector.cycle_complete", inserted=12, skipped=88)
    """
    return structlog.get_logger(name)

__all__ = ["configure", "get_logger"]
