"""Schemas and enums for append-only run audit records."""

from __future__ import annotations

from enum import Enum

import pyarrow as pa


class RunState(str, Enum):
    STARTED = "started"
    COMPLETED = "completed"


class TerminalStatus(str, Enum):
    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"
    RUNNING_OR_INTERRUPTED = "running_or_interrupted"


class AttemptStatus(str, Enum):
    SUCCESS = "success"
    FAILED = "failed"


STRING_MAP = pa.map_(pa.string(), pa.string())
FLOAT_MAP = pa.map_(pa.string(), pa.float64())
INT_MAP = pa.map_(pa.string(), pa.int64())

RUN_SCHEMA = pa.schema(
    [
        ("run_id", pa.string()),
        ("run_date", pa.string()),
        ("state", pa.string()),
        ("command", pa.string()),
        ("requested_targets", pa.list_(pa.string())),
        ("options", STRING_MAP),
        ("started_at", pa.timestamp("us", tz="UTC")),
        ("ended_at", pa.timestamp("us", tz="UTC")),
        ("elapsed_s", pa.float64()),
        ("exit_code", pa.int32()),
        ("terminal_status", pa.string()),
        ("target_count", pa.int64()),
        ("success_count", pa.int64()),
        ("failure_count", pa.int64()),
        ("failure_category", pa.string()),
        ("failure_message", pa.string()),
        ("stdout_log_path", pa.string()),
        ("json_log_path", pa.string()),
    ]
)

ATTEMPT_SCHEMA = pa.schema(
    [
        ("run_id", pa.string()),
        ("run_date", pa.string()),
        ("attempt_id", pa.string()),
        ("attempt_ordinal", pa.int64()),
        ("attempt_type", pa.string()),
        ("hospital_id", pa.string()),
        ("snapshot_id", pa.string()),
        ("snapshot_ids", pa.list_(pa.string())),
        ("source_url", pa.string()),
        ("source_file_name", pa.string()),
        ("file_hash", pa.string()),
        ("started_at", pa.timestamp("us", tz="UTC")),
        ("ended_at", pa.timestamp("us", tz="UTC")),
        ("elapsed_s", pa.float64()),
        ("status", pa.string()),
        ("failure_category", pa.string()),
        ("failure_message", pa.string()),
        ("stage_statuses", STRING_MAP),
        ("stage_elapsed_s", FLOAT_MAP),
        ("download_outcome", pa.string()),
        ("http_status", pa.int32()),
        ("content_length", pa.string()),
        ("last_modified", pa.string()),
        ("etag", pa.string()),
        ("bytes_downloaded", pa.int64()),
        ("hash_changed", pa.bool_()),
        ("raw_path", pa.string()),
        ("compression", pa.string()),
        ("content_format", pa.string()),
        ("detected_layout", pa.string()),
        ("schema_version", pa.string()),
        ("parser_class", pa.string()),
        ("parser_path", pa.string()),
        ("bronze_row_counts", INT_MAP),
        ("quarantine_counts", INT_MAP),
        ("dbt_action", pa.string()),
        ("dbt_command", pa.string()),
        ("dbt_selector", pa.string()),
        ("dbt_full_refresh", pa.bool_()),
    ]
)
