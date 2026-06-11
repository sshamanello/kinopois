"""Structured logging setup for kinopois.

Configures Python's logging module with:
- Console handler (WARNING+) for production visibility
- File handler with rotation (INFO+) at data/logs/kinopois.log

Usage:
    from kinopois.logging_setup import get_logger
    logger = get_logger(__name__)
    logger.info("Step completed")
    logger.error("Something went wrong", extra={"key": "value"})
"""

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional

_initialized = False


def setup_logging(log_dir: Optional[Path] = None, level: str = "INFO") -> None:
    """Configure the root kinopois logger with console and file handlers.

    Safe to call multiple times — subsequent calls are no-ops.
    """
    global _initialized
    if _initialized:
        return

    from kinopois.config import config

    log_dir = log_dir or config.log_dir
    log_dir.mkdir(parents=True, exist_ok=True)
    log_level = getattr(logging, level.upper(), logging.INFO)

    # Root kinopois logger — does NOT propagate to the root logger
    # to avoid double-printing from rich.console calls.
    root_logger = logging.getLogger("kinopois")
    root_logger.setLevel(log_level)
    root_logger.propagate = False

    # Console handler — WARNING and above
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.WARNING)
    console_fmt = logging.Formatter("%(levelname)s: %(message)s")
    console_handler.setFormatter(console_fmt)
    root_logger.addHandler(console_handler)

    # File handler — INFO and above, with rotation
    log_file = log_dir / "kinopois.log"
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=10 * 1024 * 1024,  # 10 MB
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.INFO)
    file_fmt = logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    file_handler.setFormatter(file_fmt)
    root_logger.addHandler(file_handler)

    _initialized = True


def get_logger(name: str) -> logging.Logger:
    """Get a logger for a kinopois submodule.

    Ensures logging is set up before returning the logger.
    The name should typically be __name__ of the calling module.
    If the name doesn't start with 'kinopois', it's prefixed automatically
    so the logger inherits the kinopois handler configuration.
    """
    setup_logging()
    if not name.startswith("kinopois"):
        name = f"kinopois.{name}"
    return logging.getLogger(name)