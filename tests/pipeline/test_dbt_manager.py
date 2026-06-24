"""Tests for hpt.pipeline.dbt_manager.DbtManager."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from hpt.pipeline.dbt_manager import CLEAR_OPERATION, PRUNE_OPERATION, DbtManager

from ._dbt_doubles import (
    FakeAdapterResponse,
    FakeNode,
    FakeNodeResult,
    FakeTiming,
    RecordingRunner,
    patch_dbt_runner,
)

TRANSFORM = Path("/tmp/transform")


@pytest.fixture
def manager(monkeypatch: pytest.MonkeyPatch) -> tuple[DbtManager, RecordingRunner]:
    # Avoid actually changing directories during _invoke.
    monkeypatch.setattr("hpt.pipeline.dbt_manager.contextlib.chdir", _noop_chdir)
    runner = RecordingRunner()
    patch_dbt_runner(monkeypatch, runner)
    return DbtManager(TRANSFORM), runner


class _noop_chdir:
    def __init__(self, *_args: object) -> None: ...
    def __enter__(self) -> None: ...
    def __exit__(self, *_exc: object) -> bool:
        return False


def _base_args_present(args: list[str]) -> bool:
    return (
        "--project-dir" in args
        and "--profiles-dir" in args
        and args[args.index("--project-dir") + 1] == str(TRANSFORM)
    )


def test_seed_invokes_seed(manager: tuple[DbtManager, RecordingRunner]) -> None:
    mgr, runner = manager
    assert mgr.seed() is True
    assert runner.calls[0][0] == "seed"
    assert _base_args_present(runner.calls[0])


def test_prune_invokes_run_operation(manager: tuple[DbtManager, RecordingRunner]) -> None:
    mgr, runner = manager
    assert mgr.prune_stale_snapshots() is True
    assert runner.calls[0][:2] == ["run-operation", PRUNE_OPERATION]
    assert "--vars" not in runner.calls[0]


def test_clear_snapshots_invokes_run_operation_with_args(
    manager: tuple[DbtManager, RecordingRunner],
) -> None:
    mgr, runner = manager
    assert mgr.clear_snapshots(["s1", "s2"]) is True
    args = runner.calls[0]
    assert args[:2] == ["run-operation", CLEAR_OPERATION]
    assert _base_args_present(args)
    assert json.loads(args[args.index("--args") + 1]) == {"snapshot_ids": ["s1", "s2"]}


def test_execute_assembles_scoped_args(manager: tuple[DbtManager, RecordingRunner]) -> None:
    mgr, runner = manager
    assert mgr.execute("build", snapshot_ids=["s1", "s2"], selector="silver") is True
    args = runner.calls[0]
    assert args[0] == "build"
    assert _base_args_present(args)
    assert json.loads(args[args.index("--vars") + 1]) == {"snapshot_ids": ["s1", "s2"]}
    assert args[args.index("--selector") + 1] == "silver"
    # build excludes unit tests.
    assert args[args.index("--exclude-resource-type") + 1] == "unit_test"
    assert "--full-refresh" not in args


def test_execute_run_command_keeps_unit_tests(manager: tuple[DbtManager, RecordingRunner]) -> None:
    mgr, runner = manager
    mgr.execute("run", snapshot_ids=["s1"])
    assert "--exclude-resource-type" not in runner.calls[0]


def test_execute_test_command_excludes_unit_tests(
    manager: tuple[DbtManager, RecordingRunner],
) -> None:
    mgr, runner = manager
    mgr.execute("test", snapshot_ids=["s1"])
    assert runner.calls[0][runner.calls[0].index("--exclude-resource-type") + 1] == "unit_test"


def test_execute_omits_selector_and_vars_when_absent(
    manager: tuple[DbtManager, RecordingRunner],
) -> None:
    mgr, runner = manager
    mgr.execute("build")
    assert "--selector" not in runner.calls[0]
    assert "--vars" not in runner.calls[0]


def test_execute_appends_full_refresh_and_extra_args(
    manager: tuple[DbtManager, RecordingRunner],
) -> None:
    mgr, runner = manager
    mgr.execute("build", full_refresh=True, extra_args=["--threads", "2"])
    args = runner.calls[0]
    assert "--full-refresh" in args
    assert args[-2:] == ["--threads", "2"]


def test_execute_emits_select_as_single_union(
    manager: tuple[DbtManager, RecordingRunner],
) -> None:
    mgr, runner = manager
    mgr.execute("build", select=["slv_core__payer_rates+", "slv_core__charge_items"])
    args = runner.calls[0]
    idx = args.index("--select")
    # All nodes follow a single --select flag (one union invocation).
    assert args[idx + 1 : idx + 3] == ["slv_core__payer_rates+", "slv_core__charge_items"]
    assert args.count("--select") == 1
    assert "--selector" not in args


def test_execute_omits_select_when_absent(
    manager: tuple[DbtManager, RecordingRunner],
) -> None:
    mgr, runner = manager
    mgr.execute("build")
    assert "--select" not in runner.calls[0]


def test_execute_select_scopes_with_snapshot_vars(
    manager: tuple[DbtManager, RecordingRunner],
) -> None:
    mgr, runner = manager
    mgr.execute("build", snapshot_ids=["s1"], select=["slv_core__payer_rates+"])
    args = runner.calls[0]
    assert json.loads(args[args.index("--vars") + 1]) == {"snapshot_ids": ["s1"]}
    assert args[args.index("--select") + 1] == "slv_core__payer_rates+"


def test_execute_records_select_in_audit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("hpt.pipeline.dbt_manager.contextlib.chdir", _noop_chdir)
    runner = RecordingRunner()
    patch_dbt_runner(monkeypatch, runner)
    attempts: list[dict[str, object]] = []
    mgr = DbtManager(TRANSFORM, audit_recorder=attempts.append)
    mgr.execute("build", select=["slv_core__payer_rates+"])
    assert attempts[0]["dbt_select"] == ["slv_core__payer_rates+"]


def test_failed_invocation_returns_false(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("hpt.pipeline.dbt_manager.contextlib.chdir", _noop_chdir)
    runner = RecordingRunner(success=False)
    patch_dbt_runner(monkeypatch, runner)
    mgr = DbtManager(TRANSFORM)
    assert mgr.execute("build", snapshot_ids=["s1"]) is False
    assert mgr.seed() is False
    assert mgr.prune_stale_snapshots() is False
    assert mgr.clear_snapshots(["s1"]) is False


def test_runner_constructed_once(manager: tuple[DbtManager, RecordingRunner]) -> None:
    mgr, runner = manager
    mgr.seed()
    mgr.execute("build", snapshot_ids=["s1"])
    mgr.prune_stale_snapshots()
    # All three actions land on the same recorded runner instance.
    assert [c[0] for c in runner.calls] == ["seed", "build", "run-operation"]


def test_invocations_emit_audit_attempts(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("hpt.pipeline.dbt_manager.contextlib.chdir", _noop_chdir)
    runner = RecordingRunner(successes=[True, False])
    patch_dbt_runner(monkeypatch, runner)
    attempts: list[dict[str, object]] = []
    mgr = DbtManager(TRANSFORM, audit_recorder=attempts.append)

    assert mgr.seed() is True
    assert mgr.execute("build", snapshot_ids=["s1"], selector="silver") is False

    assert attempts[0]["dbt_action"] == "seed"
    assert attempts[0]["status"] == "success"
    assert attempts[1]["snapshot_ids"] == ["s1"]
    assert attempts[1]["dbt_selector"] == "silver"
    assert attempts[1]["status"] == "failed"


# -- per-node harvest ----------------------------------------------------------


def _node_result() -> FakeNodeResult:
    start = datetime(2025, 6, 15, 12, 0, 0, tzinfo=UTC)
    return FakeNodeResult(
        FakeNode(
            "model.hpt.slv_core__payer_rates",
            "slv_core__payer_rates",
            materialized="incremental",
            tags=["silver_core"],
        ),
        status="success",
        execution_time=3.5,
        timing=[
            FakeTiming("compile", start, start.replace(second=1)),
            FakeTiming("execute", start.replace(second=1), start.replace(second=4)),
        ],
        adapter_response=FakeAdapterResponse(rows_affected=42, code="SELECT"),
    )


def _manager_with_nodes(
    monkeypatch: pytest.MonkeyPatch, results: list[FakeNodeResult]
) -> tuple[DbtManager, list[dict[str, object]]]:
    monkeypatch.setattr("hpt.pipeline.dbt_manager.contextlib.chdir", _noop_chdir)
    runner = RecordingRunner(node_results=results)
    patch_dbt_runner(monkeypatch, runner)
    nodes: list[dict[str, object]] = []
    mgr = DbtManager(TRANSFORM, node_recorder=nodes.extend)
    return mgr, nodes


def test_invoke_harvests_node_metrics(monkeypatch: pytest.MonkeyPatch) -> None:
    mgr, nodes = _manager_with_nodes(monkeypatch, [_node_result()])
    mgr.execute("build", snapshot_ids=["s1", "s2"], selector="silver")

    assert len(nodes) == 1
    row = nodes[0]
    assert row["node_unique_id"] == "model.hpt.slv_core__payer_rates"
    assert row["resource_type"] == "model"
    assert row["materialization"] == "incremental"
    assert row["tags"] == ["silver_core"]
    assert row["execution_time_s"] == 3.5
    assert row["compile_elapsed_s"] == 1.0
    assert row["execute_elapsed_s"] == 3.0
    assert row["rows_affected"] == 42
    assert row["adapter_code"] == "SELECT"
    # Denormalized invoke context rides on every node row.
    assert row["dbt_command"] == "build"
    assert row["dbt_selector"] == "silver"
    assert row["snapshot_ids"] == ["s1", "s2"]
    assert row["snapshot_count"] == 2


def test_node_rows_share_their_attempts_id(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("hpt.pipeline.dbt_manager.contextlib.chdir", _noop_chdir)
    runner = RecordingRunner(node_results=[_node_result()])
    patch_dbt_runner(monkeypatch, runner)
    attempts: list[dict[str, object]] = []
    nodes: list[dict[str, object]] = []
    mgr = DbtManager(TRANSFORM, audit_recorder=attempts.append, node_recorder=nodes.extend)

    mgr.execute("build", snapshot_ids=["s1"])

    assert nodes[0]["attempt_id"] == attempts[0]["attempt_id"]


def test_test_node_captures_failures(monkeypatch: pytest.MonkeyPatch) -> None:
    failing = FakeNodeResult(
        FakeNode("test.hpt.some_test", "some_test", resource_type="test", materialized=None),
        status="fail",
        failures=7,
    )
    mgr, nodes = _manager_with_nodes(monkeypatch, [failing])
    mgr.execute("build", snapshot_ids=["s1"])

    assert nodes[0]["resource_type"] == "test"
    assert nodes[0]["node_status"] == "fail"
    assert nodes[0]["test_failures"] == 7


def test_run_operation_node_without_identity_is_skipped(monkeypatch: pytest.MonkeyPatch) -> None:
    # run-operations return a RunExecutionResult whose entry has node=None; it is
    # not part of the model/test/seed grain and must not emit a null-keyed row.
    operation = FakeNodeResult(None, status="success", execution_time=0.5)  # type: ignore[arg-type]
    mgr, nodes = _manager_with_nodes(monkeypatch, [operation, _node_result()])
    mgr.execute("build", snapshot_ids=["s1"])

    assert [row["node_unique_id"] for row in nodes] == ["model.hpt.slv_core__payer_rates"]


def test_invoke_without_node_results_emits_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    # node_results=None -> result.result is None (e.g. a run-operation).
    mgr, nodes = _manager_with_nodes(monkeypatch, results=None)  # type: ignore[arg-type]
    mgr.prune_stale_snapshots()
    assert nodes == []


def test_node_harvest_failure_is_non_fatal(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("hpt.pipeline.dbt_manager.contextlib.chdir", _noop_chdir)
    runner = RecordingRunner(node_results=[_node_result()])
    patch_dbt_runner(monkeypatch, runner)

    def _boom(_rows: list[dict[str, object]]) -> None:
        raise RuntimeError("recorder exploded")

    mgr = DbtManager(TRANSFORM, node_recorder=_boom)
    # The run still succeeds even though node capture raised.
    assert mgr.execute("build", snapshot_ids=["s1"]) is True


# -- peak RSS ------------------------------------------------------------------


def test_dbt_attempt_records_peak_rss(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("hpt.pipeline.dbt_manager.contextlib.chdir", _noop_chdir)
    runner = RecordingRunner()
    patch_dbt_runner(monkeypatch, runner)
    attempts: list[dict[str, object]] = []
    mgr = DbtManager(TRANSFORM, audit_recorder=attempts.append)

    mgr.execute("build", snapshot_ids=["s1"])

    peak = attempts[0]["peak_rss_mb"]
    assert isinstance(peak, float)
    assert peak > 0
