"""Structured logging setup for CampusPulse."""

import logging
import sys


def setup_logger(
    name: str = "campuspulse",
    level: str = "INFO",
    batch_id: str | None = None,
) -> logging.Logger:
    """Configure a structured stream logger for console output."""
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    # Avoid duplicate handlers if setup_logger is called multiple times
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(getattr(logging, level.upper(), logging.INFO))

        prefix = f"[{batch_id}] " if batch_id else ""
        formatter = logging.Formatter(
            fmt=f"%(asctime)s | %(levelname)-7s | {prefix}%(name)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    return logger
