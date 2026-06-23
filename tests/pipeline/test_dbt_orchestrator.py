"""Tests for hpt.pipeline.dbt_orchestrator."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from hpt.pipeline import dbt_orchestrator
from hpt.pipeline.dbt_config import RETENTION_MODE_ENV, DbtRunConfig, DbtRunMode
from hpt.pipeline.dbt_orchestrator import DbtOrchestrator, resolve_snapshot_ids

from ._dbt_doubles import FakeSnapshotManager, RecordingRunner, patch_dbt_runner


def _commands(runner: RecordingRunner) -> list[str]:
    return [call[0] for call in runner.calls]


def _vars(call: list[str]) -> dict:
    return json.loads(call[call.index("--vars") + 1])


def _selector(call: list[str]) -> str | None:
    return call[call.index("--selector") + 1] if "--selector" in call else None


def _select(call: list[str]) -> list[str]:
    if "--select" not in call:
        return []
    rest = call[call.index("--select") + 1 :]
    nodes: list[str] = []
    for token in rest:
        if token.startswith("--"):
            break
        nodes.append(token)
    return nodes


def _operation(call: list[str]) -> str | None:
    return call[1] if call[0] == "run-operation" else None


def _args(call: list[str]) -> dict:
    return json.loads(call[call.index("--args") + 1])


# ---------------------------------------------------------------------------
# resolve_snapshot_ids
# ---------------------------------------------------------------------------


def test_resolve_string_snapshot_ids_to_list() -> None:
    result = resolve_snapshot_ids(None, "snap-a, snap-b", FakeSnapshotManager({}))
    assert result == ["snap-a", "snap-b"]


def test_resolve_merges_explicit_and_hospital_snapshots() -> None:
    snapshots = FakeSnapshotManager({"h1": "snap-h1", "h2": "snap-h2"})
    result = resolve_snapshot_ids("h1,h2", ["snap-x"], snapshots)
    # Explicit first, then resolved hospital snapshots, order preserved.
    assert result == ["snap-x", "snap-h1", "snap-h2"]


def test_resolve_dedupes_overlapping_ids() -> None:
    snapshots = FakeSnapshotManager({"h1": "snap-shared"})
    assert resolve_snapshot_ids("h1", ["snap-shared"], snapshots) == ["snap-shared"]


def test_resolve_skips_hospital_without_snapshot() -> None:
    snapshots = FakeSnapshotManager({"h1": "snap-h1", "h2": None})
    assert resolve_snapshot_ids("h1,h2", None, snapshots) == ["snap-h1"]


def test_resolve_raises_when_empty() -> None:
    with pytest.raises(ValueError):
        resolve_snapshot_ids("h2", None, FakeSnapshotManager({"h2": None}))


# ---------------------------------------------------------------------------
# Fixtures: patch storage/snapshot construction so no real I/O happens.
# ---------------------------------------------------------------------------


@pytest.fixture
def patched_storage(monkeypatch: pytest.MonkeyPatch) -> FakeSnapshotManager:
    manager = FakeSnapshotManager({"h1": "snap-h1"})
    monkeypatch.delenv(RETENTION_MODE_ENV, raising=False)
    fake_cfg = SimpleNamespace(raw_base_uri="file:///tmp/raw", bronze_root="/tmp/bronze")
    monkeypatch.setattr(
        dbt_orchestrator.StorageConfig, "from_env", classmethod(lambda cls: fake_cfg)
    )
    monkeypatch.setattr(dbt_orchestrator, "BronzeStorage", lambda *a, **k: object())
    monkeypatch.setattr(dbt_orchestrator, "SnapshotManager", lambda *a, **k: manager)
    return manager


@pytest.fixture(autouse=True)
def patched_bootstrap(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    calls: list[str] = []
    monkeypatch.setattr(
        dbt_orchestrator,
        "ensure_bronze_source_bootstrap",
        lambda *_args, **_kwargs: calls.append("bootstrap"),
    )
    return calls


def _patch_two_hospitals(monkeypatch: pytest.MonkeyPatch) -> None:
    """Registry + snapshot manager covering h1 -> snap-h1 and h2 -> snap-h2."""
    manager = FakeSnapshotManager({"h1": "snap-h1", "h2": "snap-h2"})
    monkeypatch.setattr(dbt_orchestrator, "SnapshotManager", lambda *a, **k: manager)
    monkeypatch.setattr(
        dbt_orchestrator,
        "load_registry",
        lambda *a, **k: [SimpleNamespace(hospital_id="h1"), SimpleNamespace(hospital_id="h2")],
    )


def _run(config: DbtRunConfig, monkeypatch: pytest.MonkeyPatch, runner: RecordingRunner) -> int:
    patch_dbt_runner(monkeypatch, runner)
    return DbtOrchestrator(config).run()


# ---------------------------------------------------------------------------
# Single-pass: SCOPED
# ---------------------------------------------------------------------------


def test_run_passes_resolved_snapshot_ids_as_vars(
    monkeypatch: pytest.MonkeyPatch, patched_storage: FakeSnapshotManager
) -> None:
    runner = RecordingRunner()
    config = DbtRunConfig(hospital_ids="h1", command="build", selectors="pipeline_charge_data")
    assert _run(config, monkeypatch, runner) == 0

    assert len(runner.calls) == 2
    args = runner.calls[0]
    assert args[0] == "build"
    assert _selector(args) == "pipeline_charge_data"
    assert "--project-dir" in args and "--profiles-dir" in args
    assert _vars(args) == {"snapshot_ids": ["snap-h1"]}
    assert args[args.index("--exclude-resource-type") + 1] == "unit_test"
    assert runner.calls[1][:2] == ["run-operation", "hpt_prune_stale_snapshots"]
    assert "--vars" not in runner.calls[1]


def test_run_bootstraps_once_before_dbt(
    monkeypatch: pytest.MonkeyPatch,
    patched_storage: FakeSnapshotManager,
    patched_bootstrap: list[str],
) -> None:
    events = patched_bootstrap

    class OrderedRunner(RecordingRunner):
        def invoke(self, args: list[str]):
            events.append(args[0])
            return super().invoke(args)

    runner = OrderedRunner()
    config = DbtRunConfig(hospital_ids="h1", command="build", include_seeds=True)

    assert _run(config, monkeypatch, runner) == 0
    assert events == ["bootstrap", "seed", "build", "run-operation"]


def test_bootstrap_failure_prevents_dbt_invocation(
    monkeypatch: pytest.MonkeyPatch,
    patched_storage: FakeSnapshotManager,
) -> None:
    runner = RecordingRunner()
    patch_dbt_runner(monkeypatch, runner)

    def fail_bootstrap(*_args, **_kwargs):
        raise OSError("bootstrap unavailable")

    monkeypatch.setattr(dbt_orchestrator, "ensure_bronze_source_bootstrap", fail_bootstrap)

    with pytest.raises(OSError, match="bootstrap unavailable"):
        DbtOrchestrator(DbtRunConfig(hospital_ids="h1")).run()
    assert runner.calls == []


def test_run_does_not_exclude_unit_tests_for_run_command(
    monkeypatch: pytest.MonkeyPatch, patched_storage: FakeSnapshotManager
) -> None:
    runner = RecordingRunner()
    assert _run(DbtRunConfig(hospital_ids="h1", command="run"), monkeypatch, runner) == 0
    assert "--exclude-resource-type" not in runner.calls[0]
    assert runner.calls[1][:2] == ["run-operation", "hpt_prune_stale_snapshots"]


def test_run_seeds_only_when_requested(
    monkeypatch: pytest.MonkeyPatch, patched_storage: FakeSnapshotManager
) -> None:
    runner = RecordingRunner()
    assert _run(DbtRunConfig(hospital_ids="h1"), monkeypatch, runner) == 0
    assert _commands(runner) == ["build", "run-operation"]

    runner.calls.clear()
    assert _run(DbtRunConfig(hospital_ids="h1", include_seeds=True), monkeypatch, runner) == 0
    assert _commands(runner) == ["seed", "build", "run-operation"]


def test_run_omits_selector_when_none(
    monkeypatch: pytest.MonkeyPatch, patched_storage: FakeSnapshotManager
) -> None:
    runner = RecordingRunner()
    _run(DbtRunConfig(hospital_ids="h1"), monkeypatch, runner)
    assert "--selector" not in runner.calls[0]


def test_run_returns_one_on_dbt_failure(
    monkeypatch: pytest.MonkeyPatch, patched_storage: FakeSnapshotManager
) -> None:
    runner = RecordingRunner(success=False)
    assert _run(DbtRunConfig(hospital_ids="h1"), monkeypatch, runner) == 1
    assert _commands(runner) == ["build"]


def test_run_still_prunes_when_retaining_all_snapshots(
    monkeypatch: pytest.MonkeyPatch, patched_storage: FakeSnapshotManager
) -> None:
    # Python always invokes the prune op for materializing commands; the macro
    # itself honours retention mode. So the run-operation is still issued.
    monkeypatch.setenv(RETENTION_MODE_ENV, "all_snapshots")
    runner = RecordingRunner()
    assert _run(DbtRunConfig(hospital_ids="h1"), monkeypatch, runner) == 0
    assert _commands(runner) == ["build", "run-operation"]


def test_run_does_not_prune_test_command(
    monkeypatch: pytest.MonkeyPatch, patched_storage: FakeSnapshotManager
) -> None:
    runner = RecordingRunner()
    assert _run(DbtRunConfig(hospital_ids="h1", command="test"), monkeypatch, runner) == 0
    assert _commands(runner) == ["test"]


def test_run_returns_one_when_prune_fails(
    monkeypatch: pytest.MonkeyPatch, patched_storage: FakeSnapshotManager
) -> None:
    runner = RecordingRunner(successes=[True, False])
    assert _run(DbtRunConfig(hospital_ids="h1"), monkeypatch, runner) == 1
    assert _commands(runner) == ["build", "run-operation"]


def test_single_pass_iterates_selectors(
    monkeypatch: pytest.MonkeyPatch, patched_storage: FakeSnapshotManager
) -> None:
    runner = RecordingRunner()
    config = DbtRunConfig(hospital_ids="h1", command="build", selectors="silver_base,silver_core")
    assert _run(config, monkeypatch, runner) == 0

    # One build per selector (same snapshot scope), then a single prune.
    assert _commands(runner) == ["build", "build", "run-operation"]
    assert _selector(runner.calls[0]) == "silver_base"
    assert _selector(runner.calls[1]) == "silver_core"
    assert _vars(runner.calls[0]) == {"snapshot_ids": ["snap-h1"]}
    assert _vars(runner.calls[1]) == {"snapshot_ids": ["snap-h1"]}


def test_single_pass_aborts_remaining_selectors_on_failure(
    monkeypatch: pytest.MonkeyPatch, patched_storage: FakeSnapshotManager
) -> None:
    runner = RecordingRunner(successes=[False])
    config = DbtRunConfig(hospital_ids="h1", command="build", selectors="silver_base,silver_core")
    assert _run(config, monkeypatch, runner) == 1
    assert _commands(runner) == ["build"]


# ---------------------------------------------------------------------------
# Single-pass: ALL_CURRENT
# ---------------------------------------------------------------------------


def test_all_current_resolves_registry_hospitals(
    monkeypatch: pytest.MonkeyPatch, patched_storage: FakeSnapshotManager
) -> None:
    monkeypatch.setattr(
        dbt_orchestrator, "load_registry", lambda *a, **k: [SimpleNamespace(hospital_id="h1")]
    )
    runner = RecordingRunner()
    assert (
        _run(DbtRunConfig(mode=DbtRunMode.ALL_CURRENT, command="build"), monkeypatch, runner) == 0
    )
    assert _vars(runner.calls[0]) == {"snapshot_ids": ["snap-h1"]}


# ---------------------------------------------------------------------------
# Full rebuild
# ---------------------------------------------------------------------------


def test_full_rebuild_uses_full_refresh_without_snapshot_vars(
    monkeypatch: pytest.MonkeyPatch, patched_storage: FakeSnapshotManager
) -> None:
    runner = RecordingRunner()
    assert (
        _run(DbtRunConfig(mode=DbtRunMode.FULL_REBUILD, command="build"), monkeypatch, runner) == 0
    )
    assert _commands(runner) == ["build", "run-operation"]
    build_args = runner.calls[0]
    assert "--full-refresh" in build_args
    assert "--vars" not in build_args
    assert "--selector" not in build_args


def test_full_rebuild_can_seed_and_select(
    monkeypatch: pytest.MonkeyPatch, patched_storage: FakeSnapshotManager
) -> None:
    runner = RecordingRunner()
    config = DbtRunConfig(
        mode=DbtRunMode.FULL_REBUILD, command="build", selectors="silver", include_seeds=True
    )
    assert _run(config, monkeypatch, runner) == 0
    assert _commands(runner) == ["seed", "build", "run-operation"]
    assert _selector(runner.calls[1]) == "silver"


def test_full_rebuild_iterates_selectors(
    monkeypatch: pytest.MonkeyPatch, patched_storage: FakeSnapshotManager
) -> None:
    runner = RecordingRunner()
    config = DbtRunConfig(
        mode=DbtRunMode.FULL_REBUILD, command="build", selectors="silver_base,silver_core"
    )
    assert _run(config, monkeypatch, runner) == 0
    assert _commands(runner) == ["build", "build", "run-operation"]
    assert _selector(runner.calls[0]) == "silver_base"
    assert _selector(runner.calls[1]) == "silver_core"
    assert all("--full-refresh" in c for c in runner.calls[:2])
    assert all("--vars" not in c for c in runner.calls[:2])


# ---------------------------------------------------------------------------
# Per-snapshot iteration
# ---------------------------------------------------------------------------


def test_per_snapshot_runs_dbt_once_per_snapshot(
    monkeypatch: pytest.MonkeyPatch, patched_storage: FakeSnapshotManager
) -> None:
    _patch_two_hospitals(monkeypatch)
    runner = RecordingRunner()
    assert (
        _run(DbtRunConfig(mode=DbtRunMode.PER_SNAPSHOT, command="build"), monkeypatch, runner) == 0
    )

    assert _commands(runner) == ["build", "build", "run-operation"]
    assert _vars(runner.calls[0]) == {"snapshot_ids": ["snap-h1"]}
    assert _vars(runner.calls[1]) == {"snapshot_ids": ["snap-h2"]}
    assert "--full-refresh" not in runner.calls[0]
    assert runner.calls[2][:2] == ["run-operation", "hpt_prune_stale_snapshots"]


def test_per_snapshot_runs_selected_graph_once_per_snapshot(
    monkeypatch: pytest.MonkeyPatch, patched_storage: FakeSnapshotManager
) -> None:
    _patch_two_hospitals(monkeypatch)
    runner = RecordingRunner()
    config = DbtRunConfig(
        mode=DbtRunMode.PER_SNAPSHOT,
        command="build",
        selectors="per_snapshot",
    )
    assert _run(config, monkeypatch, runner) == 0

    assert _commands(runner) == ["build", "build", "run-operation"]
    assert _selector(runner.calls[0]) == "per_snapshot"
    assert _selector(runner.calls[1]) == "per_snapshot"


def test_per_snapshot_seeds_once_and_full_refreshes_first_only(
    monkeypatch: pytest.MonkeyPatch, patched_storage: FakeSnapshotManager
) -> None:
    _patch_two_hospitals(monkeypatch)
    runner = RecordingRunner()
    config = DbtRunConfig(
        mode=DbtRunMode.PER_SNAPSHOT, command="build", include_seeds=True, full_refresh=True
    )
    assert _run(config, monkeypatch, runner) == 0

    assert _commands(runner) == ["seed", "build", "build", "run-operation"]
    assert "--full-refresh" in runner.calls[1]
    assert "--full-refresh" not in runner.calls[2]


def test_per_snapshot_selected_full_refresh_refreshes_first_snapshot_per_selector(
    monkeypatch: pytest.MonkeyPatch, patched_storage: FakeSnapshotManager
) -> None:
    _patch_two_hospitals(monkeypatch)
    runner = RecordingRunner()
    config = DbtRunConfig(
        mode=DbtRunMode.PER_SNAPSHOT,
        command="build",
        selectors="per_snapshot,audit",
        full_refresh=True,
    )
    assert _run(config, monkeypatch, runner) == 0

    assert _selector(runner.calls[0]) == "per_snapshot"
    assert _selector(runner.calls[1]) == "per_snapshot"
    assert _selector(runner.calls[2]) == "audit"
    assert _selector(runner.calls[3]) == "audit"
    assert "--full-refresh" in runner.calls[0]
    assert "--full-refresh" not in runner.calls[1]
    assert "--full-refresh" in runner.calls[2]
    assert "--full-refresh" not in runner.calls[3]


def test_per_snapshot_stops_on_first_failure(
    monkeypatch: pytest.MonkeyPatch, patched_storage: FakeSnapshotManager
) -> None:
    _patch_two_hospitals(monkeypatch)
    runner = RecordingRunner(successes=[False])
    assert (
        _run(DbtRunConfig(mode=DbtRunMode.PER_SNAPSHOT, command="build"), monkeypatch, runner) == 1
    )
    assert _commands(runner) == ["build"]


# ---------------------------------------------------------------------------
# Snapshot injection (no storage construction needed)
# ---------------------------------------------------------------------------


def test_injected_snapshot_manager_skips_storage(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(RETENTION_MODE_ENV, raising=False)
    runner = RecordingRunner()
    patch_dbt_runner(monkeypatch, runner)
    snapshots = FakeSnapshotManager({"h1": "snap-h1"})
    config = DbtRunConfig(hospital_ids="h1", command="build")
    assert DbtOrchestrator(config, snapshots=snapshots).run() == 0
    assert _vars(runner.calls[0]) == {"snapshot_ids": ["snap-h1"]}


# ---------------------------------------------------------------------------
# Clear-on-failure
# ---------------------------------------------------------------------------


def test_no_clear_on_failure_by_default(
    monkeypatch: pytest.MonkeyPatch, patched_storage: FakeSnapshotManager
) -> None:
    runner = RecordingRunner(success=False)
    assert _run(DbtRunConfig(hospital_ids="h1", command="build"), monkeypatch, runner) == 1
    assert _commands(runner) == ["build"]


def test_single_pass_clears_scoped_ids_on_failure(
    monkeypatch: pytest.MonkeyPatch, patched_storage: FakeSnapshotManager
) -> None:
    runner = RecordingRunner(successes=[False])
    config = DbtRunConfig(hospital_ids="h1", command="build", clear_on_failure=True)
    assert _run(config, monkeypatch, runner) == 1
    assert _commands(runner) == ["build", "run-operation"]
    assert _operation(runner.calls[1]) == "hpt_clear_snapshots"
    assert _args(runner.calls[1]) == {"snapshot_ids": ["snap-h1"]}


def test_per_snapshot_clears_only_failing_snapshot(
    monkeypatch: pytest.MonkeyPatch, patched_storage: FakeSnapshotManager
) -> None:
    _patch_two_hospitals(monkeypatch)
    runner = RecordingRunner(successes=[True, False])
    config = DbtRunConfig(mode=DbtRunMode.PER_SNAPSHOT, command="build", clear_on_failure=True)
    assert _run(config, monkeypatch, runner) == 1
    # First snapshot builds, second fails and is cleared on its own.
    assert _commands(runner) == ["build", "build", "run-operation"]
    assert _operation(runner.calls[2]) == "hpt_clear_snapshots"
    assert _args(runner.calls[2]) == {"snapshot_ids": ["snap-h2"]}


def test_clear_on_failure_skips_non_materializing_command(
    monkeypatch: pytest.MonkeyPatch, patched_storage: FakeSnapshotManager
) -> None:
    runner = RecordingRunner(success=False)
    config = DbtRunConfig(hospital_ids="h1", command="test", clear_on_failure=True)
    assert _run(config, monkeypatch, runner) == 1
    assert _commands(runner) == ["test"]


def test_no_clear_when_only_prune_fails(
    monkeypatch: pytest.MonkeyPatch, patched_storage: FakeSnapshotManager
) -> None:
    # build succeeds, prune fails: the build's rows are good, so do not clear them.
    runner = RecordingRunner(successes=[True, False])
    config = DbtRunConfig(hospital_ids="h1", command="build", clear_on_failure=True)
    assert _run(config, monkeypatch, runner) == 1
    assert _commands(runner) == ["build", "run-operation"]
    assert _operation(runner.calls[1]) == "hpt_prune_stale_snapshots"


# ---------------------------------------------------------------------------
# --select node selection
# ---------------------------------------------------------------------------


def test_single_pass_threads_select_as_single_run(
    monkeypatch: pytest.MonkeyPatch, patched_storage: FakeSnapshotManager
) -> None:
    runner = RecordingRunner()
    config = DbtRunConfig(
        hospital_ids="h1", command="build", select="slv_core__payer_rates+,slv_core__charge_items"
    )
    assert _run(config, monkeypatch, runner) == 0
    # One build invocation carrying both nodes, then the prune.
    assert _commands(runner) == ["build", "run-operation"]
    assert _select(runner.calls[0]) == ["slv_core__payer_rates+", "slv_core__charge_items"]
    assert "--selector" not in runner.calls[0]
    assert _vars(runner.calls[0]) == {"snapshot_ids": ["snap-h1"]}


def test_per_snapshot_threads_select_each_snapshot(
    monkeypatch: pytest.MonkeyPatch, patched_storage: FakeSnapshotManager
) -> None:
    _patch_two_hospitals(monkeypatch)
    runner = RecordingRunner()
    config = DbtRunConfig(
        mode=DbtRunMode.PER_SNAPSHOT, command="build", select="slv_core__payer_rates+"
    )
    assert _run(config, monkeypatch, runner) == 0
    builds = [c for c in runner.calls if c[0] == "build"]
    assert len(builds) == 2
    for call in builds:
        assert _select(call) == ["slv_core__payer_rates+"]


# ---------------------------------------------------------------------------
# --defer-tests two-phase build
# ---------------------------------------------------------------------------


def test_defer_tests_materializes_with_run_then_tests_once(
    monkeypatch: pytest.MonkeyPatch, patched_storage: FakeSnapshotManager
) -> None:
    runner = RecordingRunner()
    config = DbtRunConfig(hospital_ids="h1", command="build", defer_tests=True)
    assert _run(config, monkeypatch, runner) == 0
    # Materialize with run, prune, then a single trailing test pass.
    assert _commands(runner) == ["run", "run-operation", "test"]
    # The deferred test pass is unscoped so it covers the whole table.
    assert "--vars" not in runner.calls[2]


def test_per_snapshot_defer_tests_runs_each_then_tests_once(
    monkeypatch: pytest.MonkeyPatch, patched_storage: FakeSnapshotManager
) -> None:
    _patch_two_hospitals(monkeypatch)
    runner = RecordingRunner()
    config = DbtRunConfig(
        mode=DbtRunMode.PER_SNAPSHOT,
        command="build",
        select="slv_core__payer_rates+",
        defer_tests=True,
    )
    assert _run(config, monkeypatch, runner) == 0
    # Two scoped run passes, prune, then exactly one unscoped test pass.
    assert _commands(runner) == ["run", "run", "run-operation", "test"]
    assert _select(runner.calls[-1]) == ["slv_core__payer_rates+"]
    assert "--vars" not in runner.calls[-1]


def test_defer_tests_skips_test_pass_when_materialize_fails(
    monkeypatch: pytest.MonkeyPatch, patched_storage: FakeSnapshotManager
) -> None:
    # The run (materialize) pass fails: no prune, no deferred test pass.
    runner = RecordingRunner(success=False)
    config = DbtRunConfig(hospital_ids="h1", command="build", defer_tests=True)
    assert _run(config, monkeypatch, runner) == 1
    assert _commands(runner) == ["run"]


def test_defer_tests_returns_one_when_test_pass_fails(
    monkeypatch: pytest.MonkeyPatch, patched_storage: FakeSnapshotManager
) -> None:
    # run + prune succeed, deferred test pass fails.
    runner = RecordingRunner(successes=[True, True, False])
    config = DbtRunConfig(hospital_ids="h1", command="build", defer_tests=True)
    assert _run(config, monkeypatch, runner) == 1
    assert _commands(runner) == ["run", "run-operation", "test"]
