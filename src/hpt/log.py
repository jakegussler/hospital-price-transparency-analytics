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


def configure_logging(level: int = logging.INFO) -> None:
    """Attach a JSON handler to the root ``hpt`` logger.

    Safe to call multiple times; subsequent calls are no-ops so that
    library callers that import ``hpt`` sub-modules do not unexpectedly
    reconfigure logging.
    """
    root = logging.getLogger("hpt")
    if root.handlers:
        return
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(JsonFormatter())
    root.addHandler(handler)
    root.setLevel(level)


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
