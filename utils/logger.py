"""
Structured logging setup using loguru.

Call setup_logging() once in main.py before any imports use the logger.
All modules should do:  from utils.logger import logger
"""
from __future__ import annotations

import sys
from pathlib import Path

from loguru import logger  # re-exported for module consumers


def setup_logging(level: str = "INFO", file_enabled: bool = True, rotation_mb: int = 10) -> None:
    """Configure loguru with pretty console output and optional rotating file."""
    # Remove default handler
    logger.remove()

    # Console: colourful, human-readable
    fmt_console = (
        "<green>{time:HH:mm:ss}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>{name}</cyan>:<cyan>{line}</cyan> — "
        "<level>{message}</level>"
    )
    if sys.stderr is not None:
        logger.add(
            sys.stderr,
            format=fmt_console,
            level=level,
            colorize=True,
            backtrace=True,
            diagnose=True,
        )

    # File: structured, rotated
    if file_enabled:
        log_dir = Path.home() / ".pcsx2rpc"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / "pcsx2rpc.log"

        fmt_file = (
            "{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | "
            "{name}:{line} — {message}"
        )
        logger.add(
            log_file,
            format=fmt_file,
            level=level,
            rotation=f"{rotation_mb} MB",
            retention=5,
            compression="zip",
            backtrace=True,
            diagnose=False,  # no variable values in production file log
            encoding="utf-8",
        )

    logger.debug("Logging initialised (level={}, file={})", level, file_enabled)


__all__ = ["logger", "setup_logging"]
