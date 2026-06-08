"""
Logging utility for the Legal RAG Advisor.

Provides a pre-configured logger with structured formatting suitable for
production log aggregation while remaining human-readable during development.
"""

import logging
import sys
from config import settings


def get_logger(name: str) -> logging.Logger:
    """
    Return a named logger with consistent formatting.

    Args:
        name: Typically ``__name__`` of the calling module.

    Returns:
        A configured :class:`logging.Logger` instance.
    """
    logger = logging.getLogger(name)

    # Avoid duplicate handlers when called multiple times.
    if not logger.handlers:
        logger.setLevel(getattr(logging, settings.log_level.upper(), logging.INFO))

        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(logger.level)

        formatter = logging.Formatter(
            fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    return logger
