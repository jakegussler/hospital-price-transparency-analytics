"""Run snapshot-scoped dbt commands against the transform/ project.

Snapshot scoping is what keeps memory bounded: passing ``snapshot_ids`` as a dbt
var makes ``hpt_snapshot_filter()`` emit a ``snapshot_id in (...)`` predicate that
prunes Bronze hive partitions. Hospital IDs are resolved to their current
snapshot; explicit snapshot IDs pin historical snapshots.
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
from pathlib import Path

from hpt.ingest.config import StorageConfig
from hpt.ingest.snapshot import SnapshotManager
from hpt.ingest.storage import BronzeStorage
from hpt.utils.string_utils import convert_string_to_list

logger = logging.getLogger(__name__)

DEFAULT_SELECTOR = "pipeline_charge_data"
DEFAULT_COMMAND = "build"
RETENTION_MODE_ENV = "HPT_SILVER_RETENTION_MODE"
CURRENT_ONLY_RETENTION_MODE = "current_only"
ALL_SNAPSHOTS_RETENTION_MODE = "all_snapshots"
MATERIALIZING_COMMANDS = {"build", "run"}

# src/hpt/pipeline/dbt_runner.py -> project root is parents[3].
TRANSFORM_DIR = Path(__file__).resolve().parents[3] / "transform"


def _normalize_ids(ids: list[str] | str | None) -> list[str]:
    """Coerce a comma-separated string or list into a clean list of IDs."""
    if ids is None:
        return []
    if isinstance(ids, str):
        return convert_string_to_list(ids)
    cleaned: list[str] = []
    for item in ids:
        text = str(item).strip()
        if text:
            cleaned.append(text)
    return cleaned


def _retention_mode() -> str:
    return os.environ.get(RETENTION_MODE_ENV, CURRENT_ONLY_RETENTION_MODE).strip().lower()


def _validate_retention_mode() -> str:
    mode = _retention_mode()
    if mode not in {CURRENT_ONLY_RETENTION_MODE, ALL_SNAPSHOTS_RETENTION_MODE}:
        raise ValueError(
            f"{RETENTION_MODE_ENV} must be '{CURRENT_ONLY_RETENTION_MODE}' or "
            f"'{ALL_SNAPSHOTS_RETENTION_MODE}', got '{mode}'."
        )
    return mode


def _contains_full_refresh(extra_args: list[str] | None) -> bool:
    return bool(extra_args and "--full-refresh" in extra_args)


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
    resolved: list[str] = list(_normalize_ids(snapshot_ids))

    for hospital_id in _normalize_ids(hospital_ids):
        snapshot = snapshots.get_current_snapshot(hospital_id)
        if snapshot is None:
            log.warning(
                "no_current_snapshot",
                extra={"hospital_id": hospital_id},
            )
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


def run_dbt_for_snapshots(
    hospital_ids: list[str] | str | None = None,
    snapshot_ids: list[str] | str | None = None,
    *,
    command: str = DEFAULT_COMMAND,
    selector: str | None = DEFAULT_SELECTOR,
    include_seeds: bool = False,
    extra_args: list[str] | None = None,
    log: logging.Logger | None = None,
) -> int:
    """Resolve snapshot IDs and invoke dbt scoped to them. Returns an exit code."""
    log = log or logger
    if _contains_full_refresh(extra_args):
        raise ValueError(
            "Scoped dbt runs cannot use --full-refresh because dbt would replace "
            "incremental tables with only the scoped snapshot rows. Use the "
            "full rebuild path instead."
        )
    _validate_retention_mode()

    storage_cfg = StorageConfig.from_env()
    storage = BronzeStorage(storage_cfg.raw_base_uri)
    snapshots = SnapshotManager(storage)

    ids = resolve_snapshot_ids(hospital_ids, snapshot_ids, snapshots, log=log)

    transform_dir = str(TRANSFORM_DIR)
    log.info(
        "dbt_run_start",
        extra={
            "command": command,
            "selector": selector,
            "snapshot_count": len(ids),
            "snapshot_ids": ids,
            "include_seeds": include_seeds,
            "transform_dir": transform_dir,
        },
    )

    # Imported lazily so importing this module does not require dbt installed.
    from dbt.cli.main import dbtRunner

    runner = dbtRunner()

    base_args = ["--project-dir", transform_dir, "--profiles-dir", transform_dir]

    # The dbt profile and Bronze source globs use paths relative to transform/
    # (matching the `make dbt-*` targets that cd into it). dbtRunner does not
    # change the working directory, so we do it here.
    with contextlib.chdir(TRANSFORM_DIR):
        if include_seeds:
            seed_res = runner.invoke(["seed", *base_args])
            if not seed_res.success:
                log.error("dbt_seed_failed")
                return 1

        args = [command, *base_args, "--vars", json.dumps({"snapshot_ids": ids})]
        if selector:
            args += ["--selector", selector]
        # dbt unit tests use fixtures with hardcoded snapshot_ids, so the snapshot
        # filter would strip their mock rows. They are snapshot-agnostic logic
        # checks; leave them to unscoped runs (make dbt-build / CI).
        if command in ("build", "test"):
            args += ["--exclude-resource-type", "unit_test"]
        if extra_args:
            args += extra_args

        res = runner.invoke(args)
        if not res.success:
            log.error("dbt_run_failed", extra={"command": command, "selector": selector})
            return 1

        if command in MATERIALIZING_COMMANDS:
            prune_args = [
                "run-operation",
                "hpt_prune_stale_snapshots",
                *base_args,
            ]
            prune_res = runner.invoke(prune_args)
            if not prune_res.success:
                log.error("dbt_prune_failed")
                return 1

    log.info("dbt_run_complete", extra={"command": command, "selector": selector})
    return 0


def run_dbt_full_rebuild(
    *,
    command: str = DEFAULT_COMMAND,
    selector: str | None = None,
    include_seeds: bool = False,
    extra_args: list[str] | None = None,
    log: logging.Logger | None = None,
) -> int:
    """Run a true full rebuild: no snapshot vars and dbt --full-refresh."""
    log = log or logger
    if command not in MATERIALIZING_COMMANDS:
        raise ValueError(
            "Full rebuild only supports dbt build or run because it passes --full-refresh."
        )
    retention_mode = _validate_retention_mode()

    transform_dir = str(TRANSFORM_DIR)
    log.info(
        "dbt_full_rebuild_start",
        extra={
            "command": command,
            "selector": selector,
            "include_seeds": include_seeds,
            "transform_dir": transform_dir,
            "retention_mode": retention_mode,
        },
    )

    from dbt.cli.main import dbtRunner

    runner = dbtRunner()
    base_args = ["--project-dir", transform_dir, "--profiles-dir", transform_dir]
    main_args = [command, *base_args, "--full-refresh"]
    if selector:
        main_args += ["--selector", selector]
    if command in ("build", "test"):
        main_args += ["--exclude-resource-type", "unit_test"]
    if extra_args:
        main_args += extra_args

    with contextlib.chdir(TRANSFORM_DIR):
        if include_seeds:
            seed_res = runner.invoke(["seed", *base_args])
            if not seed_res.success:
                log.error("dbt_seed_failed")
                return 1

        res = runner.invoke(main_args)
        if not res.success:
            log.error("dbt_full_rebuild_failed", extra={"command": command, "selector": selector})
            return 1

        if command in MATERIALIZING_COMMANDS:
            prune_res = runner.invoke(
                [
                    "run-operation",
                    "hpt_prune_stale_snapshots",
                    *base_args,
                ]
            )
            if not prune_res.success:
                log.error("dbt_prune_failed")
                return 1

    log.info("dbt_full_rebuild_complete", extra={"command": command, "selector": selector})
    return 0
