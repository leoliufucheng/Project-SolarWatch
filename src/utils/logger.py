from __future__ import annotations

"""
SolarWatch Unified Logger
==========================
Provides consistent logging across all modules using Rich for pretty output.
"""
import logging
import sys
from pathlib import Path

from rich.console import Console
from rich.logging import RichHandler


_LOG_FORMAT = "%(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

console = Console(stderr=True)


def get_logger(
    name: str,
    level: int = logging.INFO,
    log_file: Path | None = None,
) -> logging.Logger:
    """
    Create a named logger with Rich console + optional file output.

    Args:
        name:     Logger name (typically __name__).
        level:    Logging level.
        log_file: Optional file path for persistent logs.

    Returns:
        Configured logging.Logger instance.
    """
    logger = logging.getLogger(name)

    # Prevent duplicate handlers on repeated calls
    if logger.handlers:
        return logger

    logger.setLevel(level)

    # Rich console handler (pretty output)
    rich_handler = RichHandler(
        console=console,
        show_path=True,
        show_time=True,
        markup=True,
        rich_tracebacks=True,
    )
    rich_handler.setFormatter(logging.Formatter(_LOG_FORMAT, datefmt=_DATE_FORMAT))
    logger.addHandler(rich_handler)

    # Optional file handler
    if log_file:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setFormatter(
            logging.Formatter(
                "%(asctime)s | %(name)s | %(levelname)s | %(message)s",
                datefmt=_DATE_FORMAT,
            )
        )
        logger.addHandler(file_handler)

    return logger
