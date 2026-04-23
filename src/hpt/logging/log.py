"""Logging configuration for the HPT package.

Usage
-----
Call ``configure_logging()`` once at process startup (e.g. in each CLI
command), then obtain loggers anywhere in the package with the standard
library::

    import logging
    log = logging.getLogger(__name__)

All loggers that live under the ``hpt.*`` namespace inherit the handler and
formatter installed by ``configure_logging()``.
"""

from __future__ import annotations

import json
import logging
import sys

__all__ = ["configure_logging", "get_logger"]

_EXTRA_FIELDS = ("file_hash", "bytes", "duration_s", "snapshot_id", "error", "url")


class JsonFormatter(logging.Formatter):
    """Emit one JSON object per log line."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict = {
            "ts": self.formatTime(record),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        if hasattr(record, "hospital_id"):
            payload["hospital_id"] = record.hospital_id  # type: ignore[attr-defined]
        for key in _EXTRA_FIELDS:
            val = getattr(record, key, None)
            if val is not None:
                payload[key] = val
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload)
    
class StandardOutputFormatter(logging.Formatter):
    """Human-friendly formatter for local CLI and pipeline runs."""

    _DEFAULT_FMT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
    _DEFAULT_DATEFMT = "%Y-%m-%d %H:%M:%S"

    def __init__(
        self,
        fmt: str | None = None,
        datefmt: str | None = None,
        style: str = "%",
    ) -> None:
        super().__init__(
            fmt=fmt or self._DEFAULT_FMT,
            datefmt=datefmt or self._DEFAULT_DATEFMT,
            style=style,
        )

def get_log_level(log_level: str) -> int:
    """Get the log level from the string."""
    try:
        return logging.getLevelName(log_level.upper())
    except ValueError:
        raise ValueError(f"Invalid log level: {log_level}")


def configure_logging(log_level: str = "INFO") -> None:
    """Attach a JSON handler to the root ``hpt`` logger.

    Safe to call multiple times; subsequent calls are no-ops so that
    library callers that import ``hpt`` sub-modules do not unexpectedly
    reconfigure logging.
    """
    level = get_log_level(log_level)
    root = logging.getLogger("hpt")
    if root.handlers:
        root.setLevel(level)
        return
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(StandardOutputFormatter())
    root.addHandler(handler)
    root.setLevel(level)
    root.propagate = False


def get_logger(name: str) -> logging.Logger:
    """Return a child logger under the ``hpt`` namespace.

    Equivalent to ``logging.getLogger("hpt." + name)`` but validates that
    ``name`` is not already fully qualified.

    Parameters
    ----------
    name:
        Dot-separated name *relative* to ``hpt``, e.g. ``"cli.download"``
        or ``"ingest.snapshot"``.
    """
    if name.startswith("hpt.") or name == "hpt":
        return logging.getLogger(name)
    return logging.getLogger(f"hpt.{name}")
