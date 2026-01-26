"""Python logging setup with dual output (terminal + file).

Features:
- Levels: DEBUG, INFO, WARNING, ERROR
- Output: Terminal + .log file
- Daily rotation (new file each day)
- Mode-aware filenames (dry-run vs live)
"""

import logging
import sys
from pathlib import Path
from typing import Optional

from pmkit.log.paths import PathManager


def setup_logging(
    name: str,
    path_manager: Optional[PathManager] = None,
    level: int = logging.INFO,
    console_level: Optional[int] = None,
    file_level: Optional[int] = None,
) -> logging.Logger:
    """
    Set up logging with console and file handlers.

    Args:
        name: Logger name (typically strategy name).
        path_manager: PathManager instance for file paths.
        level: Default log level.
        console_level: Console handler level (defaults to level).
        file_level: File handler level (defaults to DEBUG for verbose file logs).

    Returns:
        Configured logger instance.
    """
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)  # Capture all, filter at handlers

    # Clear existing handlers
    logger.handlers.clear()

    # Console handler
    console = logging.StreamHandler(sys.stdout)
    console.setLevel(console_level or level)
    console_fmt = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(message)s",
        datefmt="%H:%M:%S",
    )
    console.setFormatter(console_fmt)
    logger.addHandler(console)

    # File handler (if path_manager provided)
    if path_manager:
        log_path = path_manager.get_log_path(name)
        file_handler = logging.FileHandler(log_path)
        file_handler.setLevel(file_level or logging.DEBUG)
        file_fmt = logging.Formatter(
            "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        file_handler.setFormatter(file_fmt)
        logger.addHandler(file_handler)

    return logger


def get_logger(name: str) -> logging.Logger:
    """
    Get an existing logger by name.

    Args:
        name: Logger name.

    Returns:
        Logger instance (may not be configured if setup_logging wasn't called).
    """
    return logging.getLogger(name)


class LoggerMixin:
    """
    Mixin class that provides logging capability.

    Usage:
        class MyBot(LoggerMixin, BaseBot):
            def __init__(self):
                self.setup_logger("my_bot", path_manager)
    """

    _logger: Optional[logging.Logger] = None

    def setup_logger(
        self,
        name: str,
        path_manager: Optional[PathManager] = None,
        level: int = logging.INFO,
    ) -> None:
        """Set up logger for this instance."""
        self._logger = setup_logging(name, path_manager, level)

    @property
    def logger(self) -> logging.Logger:
        """Get the logger instance."""
        if self._logger is None:
            # Create a default logger if not set up
            self._logger = logging.getLogger(self.__class__.__name__)
        return self._logger
