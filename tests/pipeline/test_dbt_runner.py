"""Tests for hpt.pipeline.dbt_runner."""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from types import ModuleType, SimpleNamespace

import pytest

from hpt.ingest.snapshot import SnapshotRecord
from hpt.pipeline import dbt_runner
from hpt.pipeline.dbt_runner import (
    resolve_snapshot_ids,
    run_dbt_for_all_current_snapshots,
    run_dbt_for_snapshots,
    run_dbt_full_rebuild,
    run_dbt_per_current_snapshot,
)

# ---------------------------------------------------------------------------
# Test doubles
# ---------------------------------------------------------------------------


def _make_record(hospital_id: str, snapshot_id: str) -> SnapshotRecord:
    return SnapshotRecord(
        snapshot_id=snapshot_id,
        hospital_id=hospital_id,
        source_url="https://example.test/mrf.json",
        source_file_name="mrf.json",
        file_hash="abc123",
        ingested_at=datetime(2025, 6, 15, tzinfo=UTC),
    )


class FakeSnapshotManager:
    """Maps hospital_id -> current snapshot_id (or None for missing)."""

    def __init__(self, mapping: dict[str, str | None]) -> None:
        self._mapping = mapping

    def get_current_snapshot(self, hospital_id: str) -> SnapshotRecord | None:
        snapshot_id = self._mapping.get(hospital_id)
        if snapshot_id is None:
            return None
        return _make_record(hospital_id, snapshot_id)


class FakeResult:
    def __init__(self, success: bool = True) -> None:
        self.success = success


class RecordingRunner:
    """Stand-in for dbtRunner that records each invoke() call."""

    def __init__(self, success: bool = True, successes: list[bool] | None = None) -> None:
        self.success = success
        self.successes = list(successes or [])
        self.calls: list[list[str]] = []

    def invoke(self, args: list[str]) -> FakeResult:
        self.calls.append(args)
        success = self.successes.pop(0) if self.successes else self.success
        return FakeResult(success)


# ---------------------------------------------------------------------------
# resolve_snapshot_ids
# ---------------------------------------------------------------------------


def test_resolve_string_snapshot_ids_to_list() -> None:
    snapshots = FakeSnapshotManager({})
    result = resolve_snapshot_ids(None, "snap-a, snap-b", snapshots)
    assert result == ["snap-a", "snap-b"]


def test_resolve_merges_explicit_and_hospital_snapshots() -> None:
    snapshots = FakeSnapshotManager({"h1": "snap-h1", "h2": "snap-h2"})
    result = resolve_snapshot_ids("h1,h2", ["snap-x"], snapshots)
    # Explicit first, then resolved hospital snapshots, order preserved.
    assert result == ["snap-x", "snap-h1", "snap-h2"]


def test_resolve_dedupes_overlapping_ids() -> None:
    snapshots = FakeSnapshotManager({"h1": "snap-shared"})
    result = resolve_snapshot_ids("h1", ["snap-shared"], snapshots)
    assert result == ["snap-shared"]


def test_resolve_skips_hospital_without_snapshot() -> None:
    snapshots = FakeSnapshotManager({"h1": "snap-h1", "h2": None})
    result = resolve_snapshot_ids("h1,h2", None, snapshots)
    assert result == ["snap-h1"]


def test_resolve_raises_when_empty() -> None:
    snapshots = FakeSnapshotManager({"h2": None})
    with pytest.raises(ValueError):
        resolve_snapshot_ids("h2", None, snapshots)


# ---------------------------------------------------------------------------
# run_dbt_for_snapshots
# ---------------------------------------------------------------------------


@pytest.fixture
def patched_storage(monkeypatch: pytest.MonkeyPatch) -> FakeSnapshotManager:
    """Patch storage/snapshot construction so no real I/O happens."""
    manager = FakeSnapshotManager({"h1": "snap-h1"})

    monkeypatch.delenv(dbt_runner.RETENTION_MODE_ENV, raising=False)
    fake_cfg = SimpleNamespace(raw_base_uri="file:///tmp/raw")
    monkeypatch.setattr(dbt_runner.StorageConfig, "from_env", classmethod(lambda cls: fake_cfg))
    monkeypatch.setattr(dbt_runner, "BronzeStorage", lambda *a, **k: object())
    monkeypatch.setattr(dbt_runner, "SnapshotManager", lambda *a, **k: manager)
    return manager


def _patch_runner(monkeypatch: pytest.MonkeyPatch, runner: RecordingRunner) -> None:
    """Patch the lazily-imported dbtRunner symbol."""
    dbt_module = ModuleType("dbt")
    cli_module = ModuleType("dbt.cli")
    main_module = ModuleType("dbt.cli.main")
    main_module.dbtRunner = lambda: runner
    cli_module.main = main_module
    dbt_module.cli = cli_module

    monkeypatch.setitem(sys.modules, "dbt", dbt_module)
    monkeypatch.setitem(sys.modules, "dbt.cli", cli_module)
    monkeypatch.setitem(sys.modules, "dbt.cli.main", main_module)


def test_run_passes_resolved_snapshot_ids_as_vars(
    monkeypatch: pytest.MonkeyPatch, patched_storage: FakeSnapshotManager
) -> None:
    runner = RecordingRunner()
    _patch_runner(monkeypatch, runner)

    exit_code = run_dbt_for_snapshots(
        hospital_ids="h1", command="build", selector="pipeline_charge_data"
    )

    assert exit_code == 0
    assert len(runner.calls) == 2
    args = runner.calls[0]
    assert args[0] == "build"
    assert "--selector" in args
    assert args[args.index("--selector") + 1] == "pipeline_charge_data"
    assert "--project-dir" in args and "--profiles-dir" in args
    vars_payload = json.loads(args[args.index("--vars") + 1])
    assert vars_payload == {"snapshot_ids": ["snap-h1"]}
    # Unit tests are excluded from scoped build/test runs.
    assert "--exclude-resource-type" in args
    assert args[args.index("--exclude-resource-type") + 1] == "unit_test"
    assert runner.calls[1][:2] == ["run-operation", "hpt_prune_stale_snapshots"]
    assert "--vars" not in runner.calls[1]


def test_run_does_not_exclude_unit_tests_for_run_command(
    monkeypatch: pytest.MonkeyPatch, patched_storage: FakeSnapshotManager
) -> None:
    runner = RecordingRunner()
    _patch_runner(monkeypatch, runner)

    run_dbt_for_snapshots(hospital_ids="h1", command="run")
    assert "--exclude-resource-type" not in runner.calls[0]
    assert runner.calls[1][:2] == ["run-operation", "hpt_prune_stale_snapshots"]


def test_run_seeds_only_when_requested(
    monkeypatch: pytest.MonkeyPatch, patched_storage: FakeSnapshotManager
) -> None:
    runner = RecordingRunner()
    _patch_runner(monkeypatch, runner)

    run_dbt_for_snapshots(hospital_ids="h1", include_seeds=False)
    assert [c[0] for c in runner.calls] == ["build", "run-operation"]

    runner.calls.clear()
    run_dbt_for_snapshots(hospital_ids="h1", include_seeds=True)
    assert [c[0] for c in runner.calls] == ["seed", "build", "run-operation"]


def test_run_omits_selector_when_none(
    monkeypatch: pytest.MonkeyPatch, patched_storage: FakeSnapshotManager
) -> None:
    runner = RecordingRunner()
    _patch_runner(monkeypatch, runner)

    run_dbt_for_snapshots(hospital_ids="h1", selector=None)
    assert "--selector" not in runner.calls[0]


def test_run_returns_one_on_dbt_failure(
    monkeypatch: pytest.MonkeyPatch, patched_storage: FakeSnapshotManager
) -> None:
    runner = RecordingRunner(success=False)
    _patch_runner(monkeypatch, runner)

    assert run_dbt_for_snapshots(hospital_ids="h1") == 1
    assert [c[0] for c in runner.calls] == ["build"]


def test_run_skips_prune_when_retaining_all_snapshots(
    monkeypatch: pytest.MonkeyPatch, patched_storage: FakeSnapshotManager
) -> None:
    runner = RecordingRunner()
    _patch_runner(monkeypatch, runner)
    monkeypatch.setenv(dbt_runner.RETENTION_MODE_ENV, "all_snapshots")

    assert run_dbt_for_snapshots(hospital_ids="h1") == 0
    assert [c[0] for c in runner.calls] == ["build", "run-operation"]
    assert runner.calls[1][:2] == ["run-operation", "hpt_prune_stale_snapshots"]


def test_run_does_not_prune_test_command(
    monkeypatch: pytest.MonkeyPatch, patched_storage: FakeSnapshotManager
) -> None:
    runner = RecordingRunner()
    _patch_runner(monkeypatch, runner)

    assert run_dbt_for_snapshots(hospital_ids="h1", command="test") == 0
    assert [c[0] for c in runner.calls] == ["test"]


def test_scoped_run_rejects_full_refresh(
    monkeypatch: pytest.MonkeyPatch, patched_storage: FakeSnapshotManager
) -> None:
    runner = RecordingRunner()
    _patch_runner(monkeypatch, runner)

    with pytest.raises(ValueError, match="Scoped dbt runs cannot use --full-refresh"):
        run_dbt_for_snapshots(hospital_ids="h1", extra_args=["--full-refresh"])

    assert runner.calls == []


def test_run_returns_one_when_prune_fails(
    monkeypatch: pytest.MonkeyPatch, patched_storage: FakeSnapshotManager
) -> None:
    runner = RecordingRunner(successes=[True, False])
    _patch_runner(monkeypatch, runner)

    assert run_dbt_for_snapshots(hospital_ids="h1") == 1
    assert [c[0] for c in runner.calls] == ["build", "run-operation"]


def test_full_rebuild_uses_full_refresh_without_snapshot_vars(
    monkeypatch: pytest.MonkeyPatch, patched_storage: FakeSnapshotManager
) -> None:
    runner = RecordingRunner()
    _patch_runner(monkeypatch, runner)

    assert run_dbt_full_rebuild(selector=None) == 0

    assert [c[0] for c in runner.calls] == ["build", "run-operation"]
    build_args = runner.calls[0]
    assert "--full-refresh" in build_args
    assert "--vars" not in build_args
    assert "--selector" not in build_args


def test_full_rebuild_can_seed_and_select(
    monkeypatch: pytest.MonkeyPatch, patched_storage: FakeSnapshotManager
) -> None:
    runner = RecordingRunner()
    _patch_runner(monkeypatch, runner)

    assert run_dbt_full_rebuild(selector="silver", include_seeds=True) == 0

    assert [c[0] for c in runner.calls] == ["seed", "build", "run-operation"]
    assert "--selector" in runner.calls[1]
    assert runner.calls[1][runner.calls[1].index("--selector") + 1] == "silver"


def test_full_rebuild_rejects_non_materializing_command(
    monkeypatch: pytest.MonkeyPatch, patched_storage: FakeSnapshotManager
) -> None:
    runner = RecordingRunner()
    _patch_runner(monkeypatch, runner)

    with pytest.raises(ValueError, match="Full rebuild only supports"):
        run_dbt_full_rebuild(command="test")

    assert runner.calls == []


# ---------------------------------------------------------------------------
# run_dbt_for_all_current_snapshots
# ---------------------------------------------------------------------------


def test_all_current_snapshots_resolves_registry_hospitals(
    monkeypatch: pytest.MonkeyPatch, patched_storage: FakeSnapshotManager
) -> None:
    runner = RecordingRunner()
    _patch_runner(monkeypatch, runner)
    monkeypatch.setattr(
        dbt_runner,
        "load_registry",
        lambda *a, **k: [SimpleNamespace(hospital_id="h1")],
    )

    assert run_dbt_for_all_current_snapshots(command="build") == 0

    args = runner.calls[0]
    assert args[0] == "build"
    vars_payload = json.loads(args[args.index("--vars") + 1])
    assert vars_payload == {"snapshot_ids": ["snap-h1"]}


def test_invalid_retention_mode_raises(
    monkeypatch: pytest.MonkeyPatch, patched_storage: FakeSnapshotManager
) -> None:
    runner = RecordingRunner()
    _patch_runner(monkeypatch, runner)
    monkeypatch.setenv(dbt_runner.RETENTION_MODE_ENV, "invalid")

    with pytest.raises(ValueError, match="HPT_SILVER_RETENTION_MODE"):
        run_dbt_for_snapshots(hospital_ids="h1")


# ---------------------------------------------------------------------------
# run_dbt_per_current_snapshot
# ---------------------------------------------------------------------------


def _patch_two_hospitals(monkeypatch: pytest.MonkeyPatch) -> None:
    """Registry + snapshot manager covering h1 -> snap-h1 and h2 -> snap-h2."""
    manager = FakeSnapshotManager({"h1": "snap-h1", "h2": "snap-h2"})
    monkeypatch.setattr(dbt_runner, "SnapshotManager", lambda *a, **k: manager)
    monkeypatch.setattr(
        dbt_runner,
        "load_registry",
        lambda *a, **k: [SimpleNamespace(hospital_id="h1"), SimpleNamespace(hospital_id="h2")],
    )


def test_per_snapshot_runs_dbt_once_per_snapshot(
    monkeypatch: pytest.MonkeyPatch, patched_storage: FakeSnapshotManager
) -> None:
    runner = RecordingRunner()
    _patch_runner(monkeypatch, runner)
    _patch_two_hospitals(monkeypatch)

    assert run_dbt_per_current_snapshot(command="build") == 0

    # One scoped build per snapshot, then a single prune at the end.
    assert [c[0] for c in runner.calls] == ["build", "build", "run-operation"]
    first_vars = json.loads(runner.calls[0][runner.calls[0].index("--vars") + 1])
    second_vars = json.loads(runner.calls[1][runner.calls[1].index("--vars") + 1])
    assert first_vars == {"snapshot_ids": ["snap-h1"]}
    assert second_vars == {"snapshot_ids": ["snap-h2"]}
    assert "--full-refresh" not in runner.calls[0]
    assert runner.calls[2][:2] == ["run-operation", "hpt_prune_stale_snapshots"]


def test_per_snapshot_seeds_once_and_full_refreshes_first_only(
    monkeypatch: pytest.MonkeyPatch, patched_storage: FakeSnapshotManager
) -> None:
    runner = RecordingRunner()
    _patch_runner(monkeypatch, runner)
    _patch_two_hospitals(monkeypatch)

    assert run_dbt_per_current_snapshot(command="build", include_seeds=True, full_refresh=True) == 0

    # Seed runs once up front; full-refresh only on the first snapshot.
    assert [c[0] for c in runner.calls] == ["seed", "build", "build", "run-operation"]
    assert "--full-refresh" in runner.calls[1]
    assert "--full-refresh" not in runner.calls[2]


def test_per_snapshot_stops_on_first_failure(
    monkeypatch: pytest.MonkeyPatch, patched_storage: FakeSnapshotManager
) -> None:
    runner = RecordingRunner(successes=[False])
    _patch_runner(monkeypatch, runner)
    _patch_two_hospitals(monkeypatch)

    assert run_dbt_per_current_snapshot(command="build") == 1
    # Aborts after the first snapshot fails; no second build, no prune.
    assert [c[0] for c in runner.calls] == ["build"]


def test_per_snapshot_rejects_full_refresh_in_extra_args(
    monkeypatch: pytest.MonkeyPatch, patched_storage: FakeSnapshotManager
) -> None:
    runner = RecordingRunner()
    _patch_runner(monkeypatch, runner)
    _patch_two_hospitals(monkeypatch)

    with pytest.raises(ValueError, match="Pass full_refresh=True"):
        run_dbt_per_current_snapshot(extra_args=["--full-refresh"])

    assert runner.calls == []


def test_per_snapshot_rejects_full_refresh_for_non_materializing_command(
    monkeypatch: pytest.MonkeyPatch, patched_storage: FakeSnapshotManager
) -> None:
    runner = RecordingRunner()
    _patch_runner(monkeypatch, runner)
    _patch_two_hospitals(monkeypatch)

    with pytest.raises(ValueError, match="full_refresh only applies"):
        run_dbt_per_current_snapshot(command="test", full_refresh=True)

    assert runner.calls == []
