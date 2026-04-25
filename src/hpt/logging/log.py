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
import os
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from hpt.utils.paths import get_default_logs_root

__all__ = ["LoggingRunPaths", "configure_logging", "get_logger"]


@dataclass(frozen=True)
class LoggingRunPaths:
    """File paths created for one configured logging run."""

    run_id: str
    std_out_path: Path
    json_path: Path
    failures_dir: Path

_BASE_RECORD_KEYS = set(logging.makeLogRecord({}).__dict__.keys()) | {
    "message",
    "asctime",
}


def _build_payload(
    formatter: logging.Formatter, record: logging.LogRecord
) -> dict[str, object]:
    payload: dict[str, object] = {
        "ts": formatter.formatTime(record),
        "level": record.levelname,
        "logger": record.name,
        "msg": record.getMessage(),
    }
    for key, val in record.__dict__.items():
        if key.startswith("_") or key in _BASE_RECORD_KEYS or val is None:
            continue
        payload[key] = val
    if record.exc_info:
        payload["exc_info"] = formatter.formatException(record.exc_info)
    return payload


def _render_stdout_value(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        if not value:
            return '""'
        if any(ch.isspace() or ch in {'"', "="} for ch in value):
            return json.dumps(value)
        return value
    return json.dumps(value, default=str, sort_keys=True)


class JsonFormatter(logging.Formatter):
    """Emit one JSON object per log line."""

    def format(self, record: logging.LogRecord) -> str:
        payload = _build_payload(self, record)
        return json.dumps(payload, default=str)


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

    def format(self, record: logging.LogRecord) -> str:
        payload = _build_payload(self, record)
        structured_fields = {
            key: val
            for key, val in payload.items()
            if key not in {"ts", "level", "logger", "msg", "exc_info"}
        }
        base = (
            f"{payload['ts']} | {payload['level']:<8} | "
            f"{payload['logger']} | {payload['msg']}"
        )
        if structured_fields:
            fields = " ".join(
                f"{key}={_render_stdout_value(structured_fields[key])}"
                for key in sorted(structured_fields)
            )
            base = f"{base} | {fields}"
        if "exc_info" in payload:
            return f"{base}\n{payload['exc_info']}"
        return base

def get_log_level(log_level: str) -> int:
    """Get the log level from the string."""
    try:
        return logging.getLevelName(log_level.upper())
    except ValueError:
        raise ValueError(f"Invalid log level: {log_level}")


def _build_run_paths(logs_root: Path) -> LoggingRunPaths:
    run_id = f"{datetime.now(UTC).strftime('%Y%m%dT%H%M%S%fZ')}_pid{os.getpid()}"
    std_out_dir = logs_root / "std_out"
    json_dir = logs_root / "json"
    failures_dir = logs_root / "failures"
    std_out_dir.mkdir(parents=True, exist_ok=True)
    json_dir.mkdir(parents=True, exist_ok=True)
    failures_dir.mkdir(parents=True, exist_ok=True)
    return LoggingRunPaths(
        run_id=run_id,
        std_out_path=std_out_dir / f"{run_id}.log",
        json_path=json_dir / f"{run_id}.jsonl",
        failures_dir=failures_dir,
    )


def _set_handler_levels(root: logging.Logger, level: int) -> None:
    root.setLevel(level)
    for handler in root.handlers:
        handler.setLevel(level)


def configure_logging(
    log_level: str = "INFO",
    *,
    logs_root: Path | None = None,
) -> LoggingRunPaths:
    """Attach stdout and file handlers to the root ``hpt`` logger.

    Safe to call multiple times; subsequent calls are no-ops so that
    library callers that import ``hpt`` sub-modules do not unexpectedly
    reconfigure logging.
    """
    level = get_log_level(log_level)
    root = logging.getLogger("hpt")
    if root.handlers:
        _set_handler_levels(root, level)
        existing_paths = getattr(root, "_hpt_log_paths", None)
        if isinstance(existing_paths, LoggingRunPaths):
            return existing_paths

    run_paths = _build_run_paths((logs_root or get_default_logs_root()).resolve())

    stdout_formatter = StandardOutputFormatter()
    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(stdout_formatter)
    stream_handler.setLevel(level)
    root.addHandler(stream_handler)

    std_out_handler = logging.FileHandler(run_paths.std_out_path, encoding="utf-8")
    std_out_handler.setFormatter(StandardOutputFormatter())
    std_out_handler.setLevel(level)
    root.addHandler(std_out_handler)

    json_handler = logging.FileHandler(run_paths.json_path, encoding="utf-8")
    json_handler.setFormatter(JsonFormatter())
    json_handler.setLevel(level)
    root.addHandler(json_handler)

    root.setLevel(level)
    root.propagate = False
    root._hpt_log_paths = run_paths  # type: ignore[attr-defined]
    return run_paths


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
