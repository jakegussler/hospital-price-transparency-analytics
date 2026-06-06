"""Configuration for snapshot-scoped dbt runs against the transform/ project.

``DbtRunConfig`` is the single source of truth for *what* a dbt run does: which
command, which selectors, which hospitals/snapshots, and which run mode. Every
comma-separated string input (selectors, hospital_ids, snapshot_ids) is
normalized to a clean list here, once, so the manager and orchestrator always
see lists. All cross-field validation lives in :meth:`DbtRunConfig.validate`,
and the mapping from CLI flags to a run mode lives in
:meth:`DbtRunConfig.from_cli` -- the CLI itself carries no flow logic.

Snapshot scoping is what keeps memory bounded: passing ``snapshot_ids`` as a dbt
var makes ``hpt_snapshot_filter()`` emit a ``snapshot_id in (...)`` predicate
that prunes Bronze hive partitions.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from hpt.utils.string_utils import to_clean_list

DEFAULT_SELECTOR = "pipeline_charge_data"
DEFAULT_COMMAND = "build"
RETENTION_MODE_ENV = "HPT_SILVER_RETENTION_MODE"
CURRENT_ONLY_RETENTION_MODE = "current_only"
ALL_SNAPSHOTS_RETENTION_MODE = "all_snapshots"
VALID_RETENTION_MODES = {CURRENT_ONLY_RETENTION_MODE, ALL_SNAPSHOTS_RETENTION_MODE}
MATERIALIZING_COMMANDS = {"build", "run"}

# src/hpt/pipeline/dbt_config.py -> project root is parents[3].
TRANSFORM_DIR = Path(__file__).resolve().parents[3] / "transform"


class DbtRunMode(str, Enum):
    """How the orchestrator sources snapshots and sequences dbt invocations."""

    SCOPED = "scoped"  # explicit hospital_ids / snapshot_ids, one run
    ALL_CURRENT = "all_current"  # every registry hospital's current snapshot, one run
    PER_SNAPSHOT = "per_snapshot"  # every current snapshot, iterated one run at a time
    FULL_REBUILD = "full_rebuild"  # no snapshot scope, dbt --full-refresh


def _retention_mode_from_env() -> str:
    return os.environ.get(RETENTION_MODE_ENV, CURRENT_ONLY_RETENTION_MODE).strip().lower()


@dataclass(frozen=True)
class DbtRunConfig:
    """Immutable, validated description of a single ``hpt run-dbt`` invocation."""

    mode: DbtRunMode = DbtRunMode.SCOPED
    command: str = DEFAULT_COMMAND
    selectors: list[str] | str | None = field(default_factory=list)
    hospital_ids: list[str] | str | None = field(default_factory=list)
    snapshot_ids: list[str] | str | None = field(default_factory=list)
    include_seeds: bool = False
    full_refresh: bool = False
    extra_args: list[str] | None = field(default_factory=list)
    retention_mode: str = field(default_factory=_retention_mode_from_env)
    transform_dir: Path = TRANSFORM_DIR

    def __post_init__(self) -> None:
        # Normalize every "comma-separated string OR list" input to a clean list.
        object.__setattr__(self, "selectors", to_clean_list(self.selectors))
        object.__setattr__(self, "hospital_ids", to_clean_list(self.hospital_ids))
        object.__setattr__(self, "snapshot_ids", to_clean_list(self.snapshot_ids))
        object.__setattr__(self, "extra_args", list(self.extra_args or []))
        object.__setattr__(self, "retention_mode", (self.retention_mode or "").strip().lower())
        self.validate()

    # -- derived helpers -------------------------------------------------------

    @property
    def is_materializing(self) -> bool:
        """Whether the command writes tables (so the stale-snapshot prune runs)."""
        return self.command in MATERIALIZING_COMMANDS

    @property
    def selector_iter(self) -> list[str | None]:
        """Selectors to iterate; ``[None]`` means a single run with no ``--selector``."""
        return list(self.selectors) or [None]

    # -- validation ------------------------------------------------------------

    def validate(self) -> None:
        """Reject incoherent combinations. Raises ``ValueError`` on the first one."""
        if self.retention_mode not in VALID_RETENTION_MODES:
            raise ValueError(
                f"{RETENTION_MODE_ENV} must be '{CURRENT_ONLY_RETENTION_MODE}' or "
                f"'{ALL_SNAPSHOTS_RETENTION_MODE}', got '{self.retention_mode}'."
            )
        if "--full-refresh" in self.extra_args:
            raise ValueError(
                "Do not pass --full-refresh in extra_args. Use full_refresh=True "
                "(per-snapshot or full-rebuild) so it is applied deliberately, or the "
                "full rebuild path, rather than rebuilding incremental tables from only "
                "the scoped snapshot rows."
            )
        if self.full_refresh:
            if self.mode not in (DbtRunMode.PER_SNAPSHOT, DbtRunMode.FULL_REBUILD):
                raise ValueError("full_refresh only applies to per-snapshot or full-rebuild runs.")
            if not self.is_materializing:
                raise ValueError("full_refresh only applies to dbt build or run.")
        if self.mode is DbtRunMode.FULL_REBUILD:
            if not self.is_materializing:
                raise ValueError(
                    "Full rebuild only supports dbt build or run because it passes --full-refresh."
                )
            if self.hospital_ids or self.snapshot_ids:
                raise ValueError(
                    "Full rebuild runs unscoped; do not combine it with hospital_ids or "
                    "snapshot_ids."
                )

    # -- construction ----------------------------------------------------------

    @classmethod
    def from_cli(
        cls,
        *,
        hospital_ids: str | None = None,
        snapshot_ids: str | None = None,
        command: str = DEFAULT_COMMAND,
        selector: str | None = None,
        seeds: bool = False,
        all_hospitals: bool = False,
        per_snapshot: bool = False,
        full_refresh: bool = False,
        full_rebuild: bool = False,
    ) -> DbtRunConfig:
        """Map mutually-exclusive CLI flags to a run mode and build the config.

        This is the only place flag combinations are interpreted. Raises
        ``ValueError`` (mapped to ``typer.BadParameter`` by the CLI) on any
        incoherent combination.
        """
        if full_rebuild:
            if hospital_ids or snapshot_ids or all_hospitals or per_snapshot or full_refresh:
                raise ValueError(
                    "--full-rebuild cannot be combined with --hospital-ids, --snapshot-ids, "
                    "--all-hospitals, --per-snapshot, or --full-refresh because it "
                    "intentionally runs unscoped with its own --full-refresh."
                )
            mode = DbtRunMode.FULL_REBUILD
        elif per_snapshot:
            if hospital_ids or snapshot_ids or all_hospitals:
                raise ValueError(
                    "--per-snapshot runs every current snapshot; do not combine it with "
                    "--hospital-ids, --snapshot-ids, or --all-hospitals."
                )
            mode = DbtRunMode.PER_SNAPSHOT
        elif all_hospitals:
            if hospital_ids or snapshot_ids:
                raise ValueError(
                    "--all-hospitals cannot be combined with --hospital-ids or --snapshot-ids."
                )
            if full_refresh:
                raise ValueError("--full-refresh requires --per-snapshot.")
            mode = DbtRunMode.ALL_CURRENT
        else:
            if full_refresh:
                raise ValueError("--full-refresh requires --per-snapshot.")
            mode = DbtRunMode.SCOPED

        return cls(
            mode=mode,
            command=command,
            selectors=selector,
            hospital_ids=hospital_ids,
            snapshot_ids=snapshot_ids,
            include_seeds=seeds,
            full_refresh=full_refresh,
        )
