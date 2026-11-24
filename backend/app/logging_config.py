"""Readable console logging for the AI and indexing pipeline.

Every AI-related module logs through the ``stillroom.*`` logger hierarchy so the
output can be filtered, e.g. ``... | grep stillroom``. Lines are one event per
row with ``key=value`` fields so timings and token counts can be scanned or
grepped without parsing prose.
"""

import logging
import sys


LOG_FORMAT = "%(asctime)s %(levelname)-7s %(name)-22s %(message)s"


def configure_app_logging(level: int = logging.INFO) -> None:
    app_logger = logging.getLogger("stillroom")
    app_logger.setLevel(level)
    # Keep application lines out of the root/uvicorn handlers so nothing is
    # printed twice and uvicorn's access log stays untouched.
    app_logger.propagate = False
    if not app_logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(logging.Formatter(LOG_FORMAT, datefmt="%H:%M:%S"))
        app_logger.addHandler(handler)


def get_logger(name: str = "") -> logging.Logger:
    return logging.getLogger(f"stillroom.{name}" if name else "stillroom")


def fields(**values: object) -> str:
    """Render ``key=value`` pairs, skipping optional values that were not set."""
    return " ".join(f"{key}={value}" for key, value in values.items() if value is not None)
