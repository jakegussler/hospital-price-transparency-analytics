"""Append-only Parquet audit storage and invocation tracking."""

from __future__ import annotations

import os
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.dataset as ds
import pyarrow.parquet as pq

from hpt.audit.models import (
    ATTEMPT_SCHEMA,
    RUN_SCHEMA,
    AttemptStatus,
    RunState,
    TerminalStatus,
)


def new_run_id() -> str:
    return str(uuid.uuid4())


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _normalize_map(value: dict[str, Any] | None, caster: type = str) -> dict[str, Any]:
    return {str(key): caster(item) for key, item in (value or {}).items()}


def _row_for_schema(data: dict[str, Any], schema: pa.Schema) -> dict[str, Any]:
    row = {field.name: data.get(field.name) for field in schema}
    for name in ("options", "stage_statuses"):
        row[name] = _normalize_map(row.get(name))
    row["stage_elapsed_s"] = _normalize_map(row.get("stage_elapsed_s"), float)
    for name in ("bronze_row_counts", "quarantine_counts"):
        row[name] = _normalize_map(row.get(name), int)
    return row


class AuditStore:
    """Read and append immutable Parquet records under one local audit root."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    def append_run(self, record: dict[str, Any]) -> Path:
        return self._append("runs", record, RUN_SCHEMA)

    def append_attempt(self, record: dict[str, Any]) -> Path:
        return self._append("attempts", record, ATTEMPT_SCHEMA)

    def _initialize_datasets(self) -> None:
        for dataset_name, schema in (("runs", RUN_SCHEMA), ("attempts", ATTEMPT_SCHEMA)):
            directory = self.root / dataset_name
            sentinel_directory = directory / "run_date=1970-01-01"
            sentinel_directory.mkdir(parents=True, exist_ok=True)
            sentinel = sentinel_directory / "_schema.parquet"
            if sentinel.exists():
                (directory / "_schema.parquet").unlink(missing_ok=True)
                continue
            temporary = sentinel_directory / f".schema-{uuid.uuid4().hex}.tmp"
            try:
                pq.write_table(pa.Table.from_pylist([], schema=schema), temporary)
                os.replace(temporary, sentinel)
                (directory / "_schema.parquet").unlink(missing_ok=True)
            finally:
                temporary.unlink(missing_ok=True)

    def _append(self, dataset_name: str, record: dict[str, Any], schema: pa.Schema) -> Path:
        self._initialize_datasets()
        run_date = str(record["run_date"])
        directory = self.root / dataset_name / f"run_date={run_date}"
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{record['run_id']}_{uuid.uuid4().hex}.parquet"
        table = pa.Table.from_pylist([_row_for_schema(record, schema)], schema=schema)
        pq.write_table(table, path)
        return path

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        run_rows = self._read_matching("runs", RUN_SCHEMA, run_id)
        if not run_rows:
            return None
        run = max(
            run_rows,
            key=lambda row: (
                row["state"] == RunState.COMPLETED.value,
                row.get("ended_at") or row["started_at"],
            ),
        )
        if run["state"] != RunState.COMPLETED.value:
            run["terminal_status"] = TerminalStatus.RUNNING_OR_INTERRUPTED.value
        attempts = self._read_matching("attempts", ATTEMPT_SCHEMA, run_id)
        attempts.sort(key=lambda row: row["attempt_ordinal"])
        for row in [run, *attempts]:
            for key in (
                "options",
                "stage_statuses",
                "stage_elapsed_s",
                "bronze_row_counts",
                "quarantine_counts",
            ):
                if isinstance(row.get(key), list):
                    row[key] = dict(row[key])
        return {"run": run, "attempts": attempts}

    def _read_matching(
        self, dataset_name: str, schema: pa.Schema, run_id: str
    ) -> list[dict[str, Any]]:
        root = self.root / dataset_name
        if not root.exists():
            return []
        dataset = ds.dataset(root, format="parquet", partitioning="hive", schema=schema)
        return dataset.to_table(filter=ds.field("run_id") == run_id).to_pylist()


class AuditRun:
    """Track and persist one command invocation."""

    def __init__(
        self,
        store: AuditStore,
        *,
        command: str,
        run_id: str | None = None,
        requested_targets: list[str] | None = None,
        options: dict[str, Any] | None = None,
        log_paths: Any | None = None,
    ) -> None:
        self.store = store
        self.run_id = run_id or new_run_id()
        self.command = command
        self.requested_targets = list(requested_targets or [])
        self.options = options or {}
        self.started_at = _utcnow()
        self._started_monotonic = time.monotonic()
        self._attempt_ordinal = 0
        self._success_count = 0
        self._failure_count = 0
        self._log_paths = log_paths
        self.store.append_run(self._run_record(RunState.STARTED))

    def record_attempt(self, attempt: dict[str, Any]) -> None:
        self._attempt_ordinal += 1
        status = str(attempt.get("status", AttemptStatus.SUCCESS.value))
        if status == AttemptStatus.FAILED.value:
            self._failure_count += 1
        else:
            self._success_count += 1
        now = _utcnow()
        record = {
            "run_id": self.run_id,
            "run_date": self.started_at.date().isoformat(),
            "attempt_id": str(uuid.uuid4()),
            "attempt_ordinal": self._attempt_ordinal,
            "started_at": attempt.get("started_at", now),
            "ended_at": attempt.get("ended_at", now),
            **attempt,
        }
        if record.get("elapsed_s") is None:
            record["elapsed_s"] = max(
                0.0, (record["ended_at"] - record["started_at"]).total_seconds()
            )
        self.store.append_attempt(record)

    def complete(
        self,
        exit_code: int,
        *,
        target_count: int | None = None,
        failure_category: str | None = None,
        failure_message: str | None = None,
    ) -> int:
        if self._failure_count == 0 and exit_code == 0:
            status = TerminalStatus.SUCCESS
        elif self._success_count > 0:
            status = TerminalStatus.PARTIAL
        else:
            status = TerminalStatus.FAILED
        self.store.append_run(
            self._run_record(
                RunState.COMPLETED,
                exit_code=exit_code,
                terminal_status=status,
                target_count=(
                    target_count
                    if target_count is not None
                    else self._success_count + self._failure_count
                ),
                failure_category=failure_category,
                failure_message=failure_message,
            )
        )
        return exit_code

    def _run_record(
        self,
        state: RunState,
        *,
        exit_code: int | None = None,
        terminal_status: TerminalStatus | None = None,
        target_count: int | None = None,
        failure_category: str | None = None,
        failure_message: str | None = None,
    ) -> dict[str, Any]:
        ended_at = _utcnow() if state is RunState.COMPLETED else None
        return {
            "run_id": self.run_id,
            "run_date": self.started_at.date().isoformat(),
            "state": state.value,
            "command": self.command,
            "requested_targets": self.requested_targets,
            "options": self.options,
            "started_at": self.started_at,
            "ended_at": ended_at,
            "elapsed_s": (
                time.monotonic() - self._started_monotonic if ended_at else None
            ),
            "exit_code": exit_code,
            "terminal_status": terminal_status.value if terminal_status else None,
            "target_count": target_count,
            "success_count": self._success_count,
            "failure_count": self._failure_count,
            "failure_category": failure_category,
            "failure_message": failure_message,
            "stdout_log_path": (
                str(self._log_paths.std_out_path) if self._log_paths else None
            ),
            "json_log_path": str(self._log_paths.json_path) if self._log_paths else None,
        }
