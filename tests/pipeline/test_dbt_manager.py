"""Tests for hpt.pipeline.dbt_manager.DbtManager."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from hpt.pipeline.dbt_manager import CLEAR_OPERATION, PRUNE_OPERATION, DbtManager

from ._dbt_doubles import RecordingRunner, patch_dbt_runner

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
