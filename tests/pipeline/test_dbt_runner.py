"""Tests for hpt.pipeline.dbt_runner."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from hpt.ingest.snapshot import SnapshotRecord
from hpt.pipeline import dbt_runner
from hpt.pipeline.dbt_runner import resolve_snapshot_ids, run_dbt_for_snapshots

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

    def __init__(self, success: bool = True) -> None:
        self.success = success
        self.calls: list[list[str]] = []

    def invoke(self, args: list[str]) -> FakeResult:
        self.calls.append(args)
        return FakeResult(self.success)


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

    fake_cfg = SimpleNamespace(raw_base_uri="file:///tmp/raw")
    monkeypatch.setattr(dbt_runner.StorageConfig, "from_env", classmethod(lambda cls: fake_cfg))
    monkeypatch.setattr(dbt_runner, "BronzeStorage", lambda *a, **k: object())
    monkeypatch.setattr(dbt_runner, "SnapshotManager", lambda *a, **k: manager)
    return manager


def _patch_runner(monkeypatch: pytest.MonkeyPatch, runner: RecordingRunner) -> None:
    """Patch the lazily-imported dbtRunner symbol."""
    import dbt.cli.main as dbt_main

    monkeypatch.setattr(dbt_main, "dbtRunner", lambda: runner)


def test_run_passes_resolved_snapshot_ids_as_vars(
    monkeypatch: pytest.MonkeyPatch, patched_storage: FakeSnapshotManager
) -> None:
    runner = RecordingRunner()
    _patch_runner(monkeypatch, runner)

    exit_code = run_dbt_for_snapshots(
        hospital_ids="h1", command="build", selector="pipeline_charge_data"
    )

    assert exit_code == 0
    assert len(runner.calls) == 1
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


def test_run_does_not_exclude_unit_tests_for_run_command(
    monkeypatch: pytest.MonkeyPatch, patched_storage: FakeSnapshotManager
) -> None:
    runner = RecordingRunner()
    _patch_runner(monkeypatch, runner)

    run_dbt_for_snapshots(hospital_ids="h1", command="run")
    assert "--exclude-resource-type" not in runner.calls[0]


def test_run_seeds_only_when_requested(
    monkeypatch: pytest.MonkeyPatch, patched_storage: FakeSnapshotManager
) -> None:
    runner = RecordingRunner()
    _patch_runner(monkeypatch, runner)

    run_dbt_for_snapshots(hospital_ids="h1", include_seeds=False)
    assert [c[0] for c in runner.calls] == ["build"]

    runner.calls.clear()
    run_dbt_for_snapshots(hospital_ids="h1", include_seeds=True)
    assert [c[0] for c in runner.calls] == ["seed", "build"]


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
