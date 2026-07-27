"""Deterministic, idempotent logging configuration for scripts and research."""

from __future__ import annotations

import logging
import sys

DEFAULT_LOG_FORMAT = "%(asctime)sZ %(levelname)s %(name)s %(message)s"
DEFAULT_DATE_FORMAT = "%Y-%m-%dT%H:%M:%S"


class _UTCFormatter(logging.Formatter):
    converter = staticmethod(__import__("time").gmtime)


def configure_logging(level: int = logging.INFO) -> None:
    """Configure the root logger with UTC timestamps and a stable format."""
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(_UTCFormatter(DEFAULT_LOG_FORMAT, DEFAULT_DATE_FORMAT))
    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(level)
