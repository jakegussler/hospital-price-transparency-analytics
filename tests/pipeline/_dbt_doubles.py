"""Shared test doubles for the dbt config/manager/orchestrator modules."""

from __future__ import annotations

import sys
from datetime import UTC, datetime
from types import ModuleType

import pytest

from hpt.ingest.snapshot import SnapshotRecord


def make_record(hospital_id: str, snapshot_id: str) -> SnapshotRecord:
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
        return make_record(hospital_id, snapshot_id)


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


def patch_dbt_runner(monkeypatch: pytest.MonkeyPatch, runner: RecordingRunner) -> None:
    """Patch the lazily-imported ``dbt.cli.main.dbtRunner`` to return *runner*."""
    dbt_module = ModuleType("dbt")
    cli_module = ModuleType("dbt.cli")
    main_module = ModuleType("dbt.cli.main")
    main_module.dbtRunner = lambda: runner
    cli_module.main = main_module
    dbt_module.cli = cli_module

    monkeypatch.setitem(sys.modules, "dbt", dbt_module)
    monkeypatch.setitem(sys.modules, "dbt.cli", cli_module)
    monkeypatch.setitem(sys.modules, "dbt.cli.main", main_module)
