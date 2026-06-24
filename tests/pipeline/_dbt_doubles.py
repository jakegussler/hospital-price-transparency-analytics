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


class FakeTiming:
    """Stand-in for dbt's ``TimingInfo`` (one compile/execute phase)."""

    def __init__(self, name: str, started_at: datetime, completed_at: datetime) -> None:
        self.name = name
        self.started_at = started_at
        self.completed_at = completed_at


class FakeConfig:
    def __init__(self, materialized: str | None = None) -> None:
        self.materialized = materialized


class FakeNode:
    def __init__(
        self,
        unique_id: str,
        name: str,
        *,
        resource_type: str = "model",
        package_name: str = "hpt",
        materialized: str | None = "table",
        schema: str = "main",
        tags: list[str] | None = None,
    ) -> None:
        self.unique_id = unique_id
        self.name = name
        self.resource_type = resource_type
        self.package_name = package_name
        self.config = FakeConfig(materialized)
        self.schema = schema
        self.tags = tags or []


class FakeAdapterResponse:
    def __init__(self, rows_affected: int | None = None, code: str | None = None) -> None:
        self.rows_affected = rows_affected
        self.code = code


class FakeNodeResult:
    """Stand-in for dbt's ``RunResult`` (one node of an invocation)."""

    def __init__(
        self,
        node: FakeNode,
        *,
        status: str = "success",
        execution_time: float = 1.0,
        timing: list[FakeTiming] | None = None,
        adapter_response: FakeAdapterResponse | None = None,
        failures: int | None = None,
        thread_id: str = "Thread-1",
        message: str | None = None,
    ) -> None:
        self.node = node
        self.status = status
        self.execution_time = execution_time
        self.timing = timing or []
        self.adapter_response = adapter_response
        self.failures = failures
        self.thread_id = thread_id
        self.message = message


class FakeRunExecutionResult:
    def __init__(self, results: list[FakeNodeResult]) -> None:
        self.results = results


class FakeResult:
    def __init__(
        self, success: bool = True, node_results: list[FakeNodeResult] | None = None
    ) -> None:
        self.success = success
        # Mirrors dbtRunnerResult.result: a RunExecutionResult for build/run/etc.,
        # or None for commands (run-operation) that produce no per-node results.
        self.result = FakeRunExecutionResult(node_results) if node_results is not None else None


class RecordingRunner:
    """Stand-in for dbtRunner that records each invoke() call."""

    def __init__(
        self,
        success: bool = True,
        successes: list[bool] | None = None,
        node_results: list[FakeNodeResult] | None = None,
    ) -> None:
        self.success = success
        self.successes = list(successes or [])
        self.node_results = node_results
        self.calls: list[list[str]] = []

    def invoke(self, args: list[str]) -> FakeResult:
        self.calls.append(args)
        success = self.successes.pop(0) if self.successes else self.success
        return FakeResult(success, node_results=self.node_results)


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
