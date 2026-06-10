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
from pathlib import Path

logger = logging.getLogger(__name__)

PRUNE_OPERATION = "hpt_prune_stale_snapshots"
CLEAR_OPERATION = "hpt_clear_snapshots"
# dbt unit tests use fixtures with hardcoded snapshot_ids, so the snapshot filter
# would strip their mock rows; exclude them from scoped build/test runs and leave
# them to unscoped runs (make dbt-build / CI).
UNIT_TEST_EXCLUDED_COMMANDS = {"build", "test"}


class DbtManager:
    """Executes seed, scoped commands, and the stale-snapshot prune in transform/."""

    def __init__(self, transform_dir: Path, log: logging.Logger | None = None) -> None:
        self._transform_dir = Path(transform_dir)
        self._log = log or logger
        self._runner: object | None = None
        self._base_args = [
            "--project-dir",
            str(self._transform_dir),
            "--profiles-dir",
            str(self._transform_dir),
        ]

    def seed(self) -> bool:
        """Run ``dbt seed``; log and return False on failure."""
        return self._invoke(["seed", *self._base_args], failure_event="dbt_seed_failed")

    def prune_stale_snapshots(self) -> bool:
        """Run the stale-snapshot prune operation; log and return False on failure."""
        return self._invoke(
            ["run-operation", PRUNE_OPERATION, *self._base_args],
            failure_event="dbt_prune_failed",
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
        )

    def execute(
        self,
        command: str,
        *,
        snapshot_ids: list[str] | None = None,
        selector: str | None = None,
        full_refresh: bool = False,
        extra_args: list[str] | None = None,
    ) -> bool:
        """Invoke a single (optionally snapshot-scoped) dbt command.

        Passing ``snapshot_ids`` adds the ``snapshot_ids`` dbt var that prunes
        Bronze partitions. ``selector`` scopes models; ``full_refresh`` adds
        ``--full-refresh``. Logs and returns False on failure.
        """
        args = [command, *self._base_args]
        if snapshot_ids:
            args += ["--vars", json.dumps({"snapshot_ids": list(snapshot_ids)})]
        if selector:
            args += ["--selector", selector]
        if command in UNIT_TEST_EXCLUDED_COMMANDS:
            args += ["--exclude-resource-type", "unit_test"]
        if full_refresh:
            args.append("--full-refresh")
        if extra_args:
            args += list(extra_args)
        return self._invoke(
            args,
            failure_event="dbt_run_failed",
            failure_extra={"command": command, "selector": selector},
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
    ) -> bool:
        """Run one dbt invocation from within transform/; log on failure."""
        runner = self._ensure_runner()
        # The dbt profile and Bronze source globs use paths relative to transform/
        # (matching the `make dbt-*` targets that cd into it). dbtRunner does not
        # change the working directory, so we do it here.
        with contextlib.chdir(self._transform_dir):
            result = runner.invoke(args)
        if result.success:
            return True
        self._log.error(failure_event, extra=failure_extra or {})
        return False
