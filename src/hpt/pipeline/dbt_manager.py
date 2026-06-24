"""Thin wrapper around dbtRunner that executes individual dbt actions.

``DbtManager`` knows *how* to invoke dbt in the ``transform/`` project: it owns
the lazy ``dbtRunner`` construction, the ``--project-dir``/``--profiles-dir``
base args, the working-directory change, and the assembly of a single dbt CLI
invocation. It has no awareness of the registry, snapshots, or run modes -- that
sequencing is the orchestrator's job. Each public method runs one dbt action and
returns whether it succeeded.
"""

from __future__ import annotations

import contextlib
import json
import logging
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable

from hpt.pipeline.rss_sampler import PeakRssSampler, peak_rss_sampler

logger = logging.getLogger(__name__)

PRUNE_OPERATION = "hpt_prune_stale_snapshots"
CLEAR_OPERATION = "hpt_clear_snapshots"
# dbt unit tests use fixtures with hardcoded snapshot_ids, so the snapshot filter
# would strip their mock rows; exclude them from scoped build/test runs and leave
# them to unscoped runs (make dbt-build / CI).
UNIT_TEST_EXCLUDED_COMMANDS = {"build", "test"}

# dbt timing phase names we split execution_time into.
_COMPILE_PHASE = "compile"
_EXECUTE_PHASE = "execute"


def _phase_durations(
    timing: Any,
) -> tuple[float | None, float | None, datetime | None, datetime | None]:
    """Return (compile_s, execute_s, started_at, ended_at) from a node's timing list.

    Each ``TimingInfo`` has a ``name`` and ``started_at`` / ``completed_at``
    timestamps; we sum nothing, just pick the compile and execute phases and bound
    the overall window. Missing or malformed entries are skipped.
    """
    compile_s = execute_s = None
    started_at: datetime | None = None
    ended_at: datetime | None = None
    for entry in timing or []:
        start = getattr(entry, "started_at", None)
        end = getattr(entry, "completed_at", None)
        if start is not None:
            started_at = start if started_at is None else min(started_at, start)
        if end is not None:
            ended_at = end if ended_at is None else max(ended_at, end)
        if start is None or end is None:
            continue
        duration = (end - start).total_seconds()
        if getattr(entry, "name", None) == _COMPILE_PHASE:
            compile_s = duration
        elif getattr(entry, "name", None) == _EXECUTE_PHASE:
            execute_s = duration
    return compile_s, execute_s, started_at, ended_at


def _harvest_node_results(
    result: Any, attempt_id: str, audit_extra: dict[str, Any]
) -> list[dict[str, Any]]:
    """Extract one row per dbt node from an in-process dbtRunner result.

    ``result.result`` is a ``RunExecutionResult`` for build/run/test/seed (its
    ``.results`` is a list of ``RunResult``); for other commands (e.g.
    run-operation) it has no ``.results`` list and we return ``[]``. Every field
    access is defensive so a dbt-version shape change cannot raise here.
    """
    run_result = getattr(result, "result", None)
    nodes = getattr(run_result, "results", None)
    if not isinstance(nodes, (list, tuple)):
        return []

    snapshot_ids = list(audit_extra.get("snapshot_ids") or [])
    invoke_context = {
        "dbt_command": audit_extra.get("dbt_command"),
        "dbt_selector": audit_extra.get("dbt_selector"),
        "dbt_full_refresh": audit_extra.get("dbt_full_refresh"),
        "snapshot_ids": snapshot_ids,
        "snapshot_count": len(snapshot_ids),
    }

    rows: list[dict[str, Any]] = []
    for node_result in nodes:
        node = getattr(node_result, "node", None)
        node_unique_id = getattr(node, "unique_id", None)
        # run-operations surface a result with no real node (node is None / has no
        # unique_id). They are not part of the model/test/seed grain, so skip them
        # rather than emit a null-keyed row that would break the grain.
        if node is None or node_unique_id is None:
            continue
        adapter = getattr(node_result, "adapter_response", None) or {}
        compile_s, execute_s, started_at, ended_at = _phase_durations(
            getattr(node_result, "timing", None)
        )
        resource_type = getattr(node, "resource_type", None)
        config = getattr(node, "config", None)
        rows.append(
            {
                "attempt_id": attempt_id,
                "node_unique_id": node_unique_id,
                "node_name": getattr(node, "name", None),
                "resource_type": str(resource_type) if resource_type is not None else None,
                "package_name": getattr(node, "package_name", None),
                "materialization": getattr(config, "materialized", None),
                "node_schema": getattr(node, "schema", None),
                "tags": list(getattr(node, "tags", None) or []),
                "node_status": str(getattr(node_result, "status", None)),
                "message": getattr(node_result, "message", None),
                "test_failures": getattr(node_result, "failures", None),
                "execution_time_s": getattr(node_result, "execution_time", None),
                "compile_elapsed_s": compile_s,
                "execute_elapsed_s": execute_s,
                "started_at": started_at,
                "ended_at": ended_at,
                "rows_affected": getattr(adapter, "rows_affected", None),
                "adapter_code": getattr(adapter, "code", None),
                "thread_id": getattr(node_result, "thread_id", None),
                **invoke_context,
            }
        )
    return rows


class DbtManager:
    """Executes seed, scoped commands, and the stale-snapshot prune in transform/."""

    def __init__(
        self,
        transform_dir: Path,
        log: logging.Logger | None = None,
        audit_recorder: Callable[[dict[str, Any]], None] | None = None,
        node_recorder: Callable[[list[dict[str, Any]]], None] | None = None,
    ) -> None:
        self._transform_dir = Path(transform_dir)
        self._log = log or logger
        self._runner: object | None = None
        self._audit_recorder = audit_recorder
        self._node_recorder = node_recorder
        self._base_args = [
            "--project-dir",
            str(self._transform_dir),
            "--profiles-dir",
            str(self._transform_dir),
        ]

    def seed(self) -> bool:
        """Run ``dbt seed``; log and return False on failure."""
        return self._invoke(
            ["seed", *self._base_args],
            failure_event="dbt_seed_failed",
            audit_extra={"dbt_action": "seed", "dbt_command": "seed"},
        )

    def prune_stale_snapshots(self) -> bool:
        """Run the stale-snapshot prune operation; log and return False on failure."""
        return self._invoke(
            ["run-operation", PRUNE_OPERATION, *self._base_args],
            failure_event="dbt_prune_failed",
            audit_extra={"dbt_action": "prune", "dbt_command": "run-operation"},
        )

    def clear_snapshots(self, snapshot_ids: list[str]) -> bool:
        """Delete every snapshot-grained row for ``snapshot_ids``; return False on failure.

        Mirror of :meth:`prune_stale_snapshots`, but targeted: it invokes the
        ``hpt_clear_snapshots`` run-operation with the snapshot ids passed as
        ``--args`` so a snapshot left partially materialized by a failed run can
        be removed from the Silver/validation tables.
        """
        args = json.dumps({"snapshot_ids": list(snapshot_ids)})
        return self._invoke(
            ["run-operation", CLEAR_OPERATION, "--args", args, *self._base_args],
            failure_event="dbt_clear_failed",
            failure_extra={"snapshot_ids": list(snapshot_ids)},
            audit_extra={
                "dbt_action": "clear",
                "dbt_command": "run-operation",
                "snapshot_ids": list(snapshot_ids),
            },
        )

    def execute(
        self,
        command: str,
        *,
        snapshot_ids: list[str] | None = None,
        selector: str | None = None,
        select: list[str] | None = None,
        full_refresh: bool = False,
        extra_args: list[str] | None = None,
    ) -> bool:
        """Invoke a single (optionally snapshot-scoped) dbt command.

        Passing ``snapshot_ids`` adds the ``snapshot_ids`` dbt var that prunes
        Bronze partitions. ``selector`` scopes models by named selector;
        ``select`` scopes models by node selection (FQNs/tags/paths and graph
        operators such as ``model+``) in a single union invocation. The caller is
        responsible for not passing both. ``full_refresh`` adds ``--full-refresh``.
        Logs and returns False on failure.
        """
        args = [command, *self._base_args]
        if snapshot_ids:
            args += ["--vars", json.dumps({"snapshot_ids": list(snapshot_ids)})]
        if selector:
            args += ["--selector", selector]
        if select:
            args += ["--select", *select]
        if command in UNIT_TEST_EXCLUDED_COMMANDS:
            args += ["--indirect-selection", "buildable"]
            args += ["--exclude-resource-type", "unit_test"]
        if full_refresh:
            args.append("--full-refresh")
        if extra_args:
            args += list(extra_args)
        return self._invoke(
            args,
            failure_event="dbt_run_failed",
            failure_extra={"command": command, "selector": selector},
            audit_extra={
                "dbt_action": "command",
                "dbt_command": command,
                "dbt_selector": selector,
                "dbt_select": list(select or []),
                "snapshot_ids": list(snapshot_ids or []),
                "dbt_full_refresh": full_refresh,
            },
        )

    # -- internals -------------------------------------------------------------

    def _ensure_runner(self) -> object:
        """Construct the dbtRunner lazily so importing this module needs no dbt."""
        if self._runner is None:
            from dbt.cli.main import dbtRunner

            self._runner = dbtRunner()
        return self._runner

    def _invoke(
        self,
        args: list[str],
        *,
        failure_event: str,
        failure_extra: dict[str, object] | None = None,
        audit_extra: dict[str, Any] | None = None,
    ) -> bool:
        """Run one dbt invocation from within transform/; log on failure."""
        runner = self._ensure_runner()
        # Mint the attempt id up front so the per-node rows harvested from this
        # invoke can be tied to the attempt row the audit_recorder writes; the
        # AuditRun honors a supplied attempt_id over its own default.
        attempt_id = str(uuid.uuid4())
        audit_extra = {"attempt_id": attempt_id, **(audit_extra or {})}
        started_at = datetime.now(UTC)
        started_monotonic = time.monotonic()
        # The dbt profile and Bronze source globs use paths relative to transform/
        # (matching the `make dbt-*` targets that cd into it). dbtRunner does not
        # change the working directory, so we do it here.
        error: Exception | None = None
        result: Any = None
        # Pre-bind so the audit record can always read a peak, even if entering the
        # sampler were to fail; measurement must never break the invocation.
        rss = PeakRssSampler()
        try:
            with peak_rss_sampler() as rss, contextlib.chdir(self._transform_dir):
                result = runner.invoke(args)
            success = bool(result.success)
        except Exception as exc:
            error = exc
            success = False
        if not success:
            self._log.error(failure_event, extra=failure_extra or {})
        if self._audit_recorder is not None:
            self._audit_recorder(
                {
                    "attempt_type": "dbt",
                    "status": "success" if success else "failed",
                    "failure_category": None if success else failure_event,
                    "failure_message": (
                        None
                        if success
                        else str(error)
                        if error
                        else f"{failure_event}: dbt returned failure"
                    ),
                    "started_at": started_at,
                    "ended_at": datetime.now(UTC),
                    "elapsed_s": time.monotonic() - started_monotonic,
                    "peak_rss_mb": rss.peak_mb,
                    **audit_extra,
                }
            )
        self._record_node_results(result, attempt_id, audit_extra)
        if error is not None:
            raise error
        return success

    def _record_node_results(
        self, result: Any, attempt_id: str, audit_extra: dict[str, Any]
    ) -> None:
        """Harvest per-node metrics from the dbtRunner result; never raise.

        Performance/observability capture must not be able to fail a dbt run, so
        the whole harvest is defensive: a missing recorder, a result type without
        per-node results (e.g. run-operation), or any extraction error degrades to
        recording nothing.
        """
        if self._node_recorder is None:
            return
        try:
            rows = _harvest_node_results(result, attempt_id, audit_extra)
            if rows:
                self._node_recorder(rows)
        except Exception:  # noqa: BLE001 - observability must never break a run
            self._log.warning("dbt_node_harvest_failed", extra={"attempt_id": attempt_id})
