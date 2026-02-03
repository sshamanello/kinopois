"""Logging system for kinopois operations."""

import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

from rich.console import Console

from kinopois.config import config

console = Console()


class Logger:
    """Centralized logging system for kinopois."""

    def __init__(self, log_file: Optional[Path] = None):
        """Initialize logger.

        Args:
            log_file: Path to log file. Defaults to data/kinopois.log
        """
        if log_file is None:
            log_file = config.data_dir / "kinopois.log"

        self.log_file = log_file

        # Create logger
        self.logger = logging.getLogger("kinopois")
        self.logger.setLevel(logging.DEBUG)

        # Prevent duplicate handlers
        if not self.logger.handlers:
            # File handler with detailed format
            file_handler = logging.FileHandler(log_file, encoding="utf-8")
            file_handler.setLevel(logging.DEBUG)
            file_format = logging.Formatter(
                "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S"
            )
            file_handler.setFormatter(file_format)
            self.logger.addHandler(file_handler)

            # Console handler for errors only
            console_handler = logging.StreamHandler(sys.stderr)
            console_handler.setLevel(logging.ERROR)
            console_format = logging.Formatter(
                "%(levelname)s: %(message)s"
            )
            console_handler.setFormatter(console_format)
            self.logger.addHandler(console_handler)

        # Statistics tracking
        self.stats = {
            "movies_downloaded": 0,
            "collages_created": 0,
            "errors": 0,
            "last_operation": None,
            "last_update": None,
        }

    def debug(self, message: str):
        """Log debug message."""
        self.logger.debug(message)

    def info(self, message: str):
        """Log info message."""
        self.logger.info(message)

    def warning(self, message: str):
        """Log warning message."""
        self.logger.warning(message)

    def error(self, message: str, exc_info: bool = False):
        """Log error message.

        Args:
            message: Error message.
            exc_info: If True, include full stack trace.
        """
        self.logger.error(message, exc_info=exc_info)
        self.stats["errors"] += 1

    def exception(self, message: str):
        """Log exception with full traceback."""
        self.logger.exception(message)
        self.stats["errors"] += 1

    def log_operation(self, operation: str, details: Optional[dict] = None):
        """Log an operation with details.

        Args:
            operation: Operation name (e.g., "download", "collage", "export").
            details: Optional dict with operation details.
        """
        self.stats["last_operation"] = operation
        self.stats["last_update"] = datetime.now().isoformat()

        if details:
            details_str = ", ".join(f"{k}={v}" for k, v in details.items())
            self.info(f"Operation: {operation} | {details_str}")
        else:
            self.info(f"Operation: {operation}")

    def increment_stat(self, stat: str, value: int = 1):
        """Increment a statistic.

        Args:
            stat: Stat name (movies_downloaded, collages_created, etc.).
            value: Value to add (default: 1).
        """
        if stat in self.stats:
            self.stats[stat] += value

    def get_stats(self) -> dict:
        """Get current statistics.

        Returns:
            Dictionary with statistics.
        """
        return self.stats.copy()

    def log_ssl_error(self, url: str, error: Exception):
        """Log SSL error with details.

        Args:
            url: URL that failed.
            error: Exception object.
        """
        self.error(f"SSL Error for {url}: {type(error).__name__}: {error}", exc_info=True)

    def log_api_error(self, endpoint: str, status_code: Optional[int] = None, error: Optional[str] = None):
        """Log API error with details.

        Args:
            endpoint: API endpoint.
            status_code: HTTP status code (if applicable).
            error: Error message.
        """
        if status_code:
            self.error(f"API Error: {endpoint} returned {status_code}: {error}")
        else:
            self.error(f"API Error: {endpoint} - {error}")

    def get_recent_errors(self, count: int = 10) -> list:
        """Get recent error entries from log file.

        Args:
            count: Number of recent errors to return.

        Returns:
            List of recent error log lines.
        """
        if not self.log_file.exists():
            return []

        errors = []
        with open(self.log_file, "r", encoding="utf-8") as f:
            for line in f:
                if "| ERROR     |" in line:
                    errors.append(line.strip())
                    if len(errors) >= count:
                        break

        return errors[-count:]

    def clear_stats(self):
        """Reset statistics counters."""
        self.stats = {
            "movies_downloaded": 0,
            "collages_created": 0,
            "errors": 0,
            "last_operation": None,
            "last_update": None,
        }


# Global logger instance
_global_logger: Optional[Logger] = None


def get_logger() -> Logger:
    """Get global logger instance.

    Returns:
        Logger instance.
    """
    global _global_logger
    if _global_logger is None:
        _global_logger = Logger()
    return _global_logger


def reset_logger():
    """Reset global logger instance (mainly for testing)."""
    global _global_logger
    _global_logger = None
