"""
Centralized logging configuration.

Used by:
- API layer
- Workers
- Services

Import this module once at startup to configure logging globally.
"""

import logging
import sys


def setup_logging(level: int = logging.INFO):
    """
    Configure root logger.

    Call this early (FastAPI startup, worker startup).
    """

    formatter = logging.Formatter(
        "[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s"
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # Prevent duplicate handlers
    if not root_logger.handlers:
        root_logger.addHandler(handler)


def get_logger(name: str) -> logging.Logger:
    """
    Get a named logger with global configuration.
    """
    return logging.getLogger(name)
