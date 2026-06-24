"""Orchestrate snapshot-scoped dbt runs.

``DbtOrchestrator`` decides *which* dbt actions run and *in what order* for a
given :class:`~hpt.pipeline.dbt_config.DbtRunConfig`. It resolves snapshot IDs
(from the registry and ``SnapshotManager``), dispatches on the run mode, and
iterates over selectors (and, for per-snapshot mode, snapshots), delegating every
actual dbt invocation to :class:`~hpt.pipeline.dbt_manager.DbtManager`.

Hospital IDs are resolved to their current snapshot; explicit snapshot IDs pin
historical snapshots. The stale-snapshot prune runs once after a materializing
run completes.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Callable

from hpt.ingest.config import StorageConfig
from hpt.ingest.snapshot import SnapshotManager
from hpt.ingest.storage import BronzeStorage
from hpt.pipeline.bronze_bootstrap import ensure_bronze_source_bootstrap
from hpt.pipeline.dbt_config import DbtRunConfig, DbtRunMode
from hpt.pipeline.dbt_manager import DbtManager
from hpt.registry.loader import load_registry
from hpt.utils.string_utils import to_clean_list

logger = logging.getLogger(__name__)

# Modes that target every hospital's current snapshot rather than explicit inputs.
_REGISTRY_MODES = (DbtRunMode.ALL_CURRENT, DbtRunMode.PER_SNAPSHOT)


def resolve_snapshot_ids(
    hospital_ids: list[str] | str | None,
    snapshot_ids: list[str] | str | None,
    snapshots: SnapshotManager,
    log: logging.Logger | None = None,
) -> list[str]:
    """Merge explicit snapshot_ids with the current snapshot for each hospital_id.

    Hospitals with no current snapshot are warned and skipped. Order is preserved
    and duplicates are removed (explicit snapshot_ids first, then resolved ones).
    Raises ``ValueError`` if the merged set is empty.
    """
    log = log or logger
    resolved: list[str] = list(to_clean_list(snapshot_ids))

    for hospital_id in to_clean_list(hospital_ids):
        snapshot = snapshots.get_current_snapshot(hospital_id)
        if snapshot is None:
            log.warning("no_current_snapshot", extra={"hospital_id": hospital_id})
            continue
        resolved.append(snapshot.snapshot_id)

    # Dedupe while preserving order.
    deduped = list(dict.fromkeys(resolved))
    if not deduped:
        raise ValueError(
            "No snapshot IDs resolved. Provide --snapshot-ids and/or --hospital-ids "
            "that have a current snapshot in raw storage."
        )
    return deduped


class DbtOrchestrator:
    """Runs the dbt actions for a :class:`DbtRunConfig` and returns an exit code."""

    def __init__(
        self,
        config: DbtRunConfig,
        *,
        log: logging.Logger | None = None,
        snapshots: SnapshotManager | None = None,
        audit_recorder: Callable[[dict[str, Any]], None] | None = None,
        node_recorder: Callable[[list[dict[str, Any]]], None] | None = None,
        bronze_root: Path | None = None,
    ) -> None:
        self._config = config
        self._log = log or logger
        self._snapshots = snapshots
        self._bronze_root = bronze_root
        self._manager = DbtManager(config.transform_dir, self._log, audit_recorder, node_recorder)

    def run(self) -> int:
        """Dispatch on the run mode and return a process-style exit code."""
        bronze_root = self._bronze_root
        if bronze_root is None:
            bronze_root = StorageConfig.from_env().bronze_root
        ensure_bronze_source_bootstrap(
            bronze_root,
            self._config.transform_dir / "models" / "staging" / "_bronze_sources.yml",
            log=self._log,
        )
        mode = self._config.mode
        if mode is DbtRunMode.FULL_REBUILD:
            exit_code = self._run_full_rebuild()
        elif mode is DbtRunMode.PER_SNAPSHOT:
            exit_code = self._run_per_snapshot()
        else:
            exit_code = self._run_single_pass()
        if exit_code != 0:
            return exit_code
        if self._config.runs_deferred_tests:
            return self._run_deferred_tests()
        return 0

    # -- flows -----------------------------------------------------------------

    def _run_single_pass(self) -> int:
        """SCOPED / ALL_CURRENT: one run scoping every resolved snapshot at once."""
        cfg = self._config
        ids = self._resolve_snapshots()
        self._log.info(
            "dbt_run_start",
            extra={
                "mode": cfg.mode.value,
                "command": cfg.materialize_command,
                "selectors": cfg.selectors,
                "select": cfg.select,
                "defer_tests": cfg.runs_deferred_tests,
                "snapshot_count": len(ids),
                "snapshot_ids": ids,
                "include_seeds": cfg.include_seeds,
                "transform_dir": str(cfg.transform_dir),
            },
        )
        if cfg.include_seeds and not self._manager.seed():
            return 1
        for selector in cfg.selector_iter:
            if not self._manager.execute(
                cfg.materialize_command,
                snapshot_ids=ids,
                selector=selector,
                select=cfg.select,
                extra_args=cfg.extra_args,
            ):
                self._clear_on_failure(ids)
                return 1
        if cfg.is_materializing and not self._manager.prune_stale_snapshots():
            return 1
        self._log.info("dbt_run_complete", extra={"command": cfg.command})
        return 0

    def _run_per_snapshot(self) -> int:
        """PER_SNAPSHOT: iterate snapshots (per selector) to bound peak memory.

        ``full_refresh`` applies ``--full-refresh`` to the first snapshot for
        each selector, rebuilding that selected graph so later snapshots append
        rather than overwrite. The prune runs once after every snapshot is built.
        """
        cfg = self._config
        ids = self._resolve_snapshots()
        self._log.info(
            "dbt_per_snapshot_start",
            extra={
                "command": cfg.materialize_command,
                "selectors": cfg.selectors,
                "select": cfg.select,
                "defer_tests": cfg.runs_deferred_tests,
                "snapshot_count": len(ids),
                "snapshot_ids": ids,
                "include_seeds": cfg.include_seeds,
                "full_refresh": cfg.full_refresh,
                "transform_dir": str(cfg.transform_dir),
            },
        )
        if cfg.include_seeds and not self._manager.seed():
            return 1
        for selector in cfg.selector_iter:
            for index, snapshot_id in enumerate(ids):
                if not self._manager.execute(
                    cfg.materialize_command,
                    snapshot_ids=[snapshot_id],
                    selector=selector,
                    select=cfg.select,
                    full_refresh=cfg.full_refresh and index == 0,
                    extra_args=cfg.extra_args,
                ):
                    self._clear_on_failure([snapshot_id])
                    return 1
        if cfg.is_materializing and not self._manager.prune_stale_snapshots():
            return 1
        self._log.info("dbt_per_snapshot_complete", extra={"command": cfg.command})
        return 0

    def _run_full_rebuild(self) -> int:
        """FULL_REBUILD: unscoped dbt --full-refresh, once per selector."""
        cfg = self._config
        self._log.info(
            "dbt_full_rebuild_start",
            extra={
                "command": cfg.materialize_command,
                "selectors": cfg.selectors,
                "select": cfg.select,
                "defer_tests": cfg.runs_deferred_tests,
                "include_seeds": cfg.include_seeds,
                "transform_dir": str(cfg.transform_dir),
                "retention_mode": cfg.retention_mode,
            },
        )
        if cfg.include_seeds and not self._manager.seed():
            return 1
        for selector in cfg.selector_iter:
            if not self._manager.execute(
                cfg.materialize_command,
                selector=selector,
                select=cfg.select,
                full_refresh=True,
                extra_args=cfg.extra_args,
            ):
                return 1
        if cfg.is_materializing and not self._manager.prune_stale_snapshots():
            return 1
        self._log.info("dbt_full_rebuild_complete", extra={"command": cfg.command})
        return 0

    def _run_deferred_tests(self) -> int:
        """Run a single unscoped ``test`` pass after a deferred-test materialization.

        Reached only when ``--defer-tests`` split a ``build`` into a ``run``
        materialization (already complete and pruned) plus this trailing test
        pass. The pass is intentionally unscoped (no ``snapshot_ids`` var): generic
        tests then cover the whole table and ``hpt_scoped_ref`` singular tests see
        every snapshot, so it is the comprehensive final gate. ``--select`` (when
        set) still narrows the pass to the tests attached to the rebuilt models.
        """
        cfg = self._config
        self._log.info(
            "dbt_deferred_tests_start",
            extra={
                "command": "test",
                "selectors": cfg.selectors,
                "select": cfg.select,
                "transform_dir": str(cfg.transform_dir),
            },
        )
        for selector in cfg.selector_iter:
            if not self._manager.execute(
                "test",
                selector=selector,
                select=cfg.select,
                extra_args=cfg.extra_args,
            ):
                return 1
        self._log.info("dbt_deferred_tests_complete", extra={"command": cfg.command})
        return 0

    # -- internals -------------------------------------------------------------

    def _clear_on_failure(self, snapshot_ids: list[str]) -> None:
        """Delete the just-built snapshot(s) after a failed materializing run.

        Opt-in via ``clear_on_failure``. Only fires for build/run, where rows may
        have been written before the failure left the snapshot partially
        materialized; it is a no-op for non-materializing commands. A clear
        failure is logged but does not change the run's exit code -- the run has
        already failed.
        """
        cfg = self._config
        if not cfg.clear_on_failure or not cfg.is_materializing:
            return
        self._log.warning("dbt_run_failed_clearing_snapshots", extra={"snapshot_ids": snapshot_ids})
        if not self._manager.clear_snapshots(snapshot_ids):
            self._log.error("dbt_clear_on_failure_failed", extra={"snapshot_ids": snapshot_ids})

    def _resolve_snapshots(self) -> list[str]:
        """Resolve the snapshot IDs this run targets, sourcing hospitals per mode."""
        snapshots = self._snapshots
        if snapshots is None:
            storage_cfg = StorageConfig.from_env()
            storage = BronzeStorage(storage_cfg.raw_base_uri)
            snapshots = SnapshotManager(storage)

        if self._config.mode in _REGISTRY_MODES:
            hospital_ids = [hospital.hospital_id for hospital in load_registry()]
            explicit_ids: list[str] | None = None
        else:
            hospital_ids = self._config.hospital_ids
            explicit_ids = self._config.snapshot_ids

        return resolve_snapshot_ids(hospital_ids, explicit_ids, snapshots, log=self._log)
