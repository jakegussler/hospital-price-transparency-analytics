"""Tests for hpt.pipeline.dbt_config.DbtRunConfig."""

from __future__ import annotations

import pytest

from hpt.pipeline.dbt_config import (
    DEFAULT_COMMAND,
    DEFAULT_SELECTOR,
    RETENTION_MODE_ENV,
    DbtRunConfig,
    DbtRunMode,
)


@pytest.fixture(autouse=True)
def _clear_retention_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(RETENTION_MODE_ENV, raising=False)


# ---------------------------------------------------------------------------
# Normalization: comma-separated strings and lists both become clean lists
# ---------------------------------------------------------------------------


def test_comma_separated_strings_become_lists() -> None:
    cfg = DbtRunConfig(
        selectors="silver_base, silver_core",
        hospital_ids="H1, H2",
        snapshot_ids="Snap-A, snap-b",
    )
    assert cfg.selectors == ["silver_base", "silver_core"]
    # IDs are lowercased and stripped.
    assert cfg.hospital_ids == ["h1", "h2"]
    assert cfg.snapshot_ids == ["snap-a", "snap-b"]


def test_list_inputs_are_cleaned() -> None:
    cfg = DbtRunConfig(selectors=[" silver ", "", "core"], hospital_ids=["H1", " "])
    assert cfg.selectors == ["silver", "core"]
    assert cfg.hospital_ids == ["h1"]


def test_none_inputs_become_empty_lists() -> None:
    cfg = DbtRunConfig(selectors=None, hospital_ids=None, snapshot_ids=None, extra_args=None)
    assert cfg.selectors == []
    assert cfg.hospital_ids == []
    assert cfg.snapshot_ids == []
    assert cfg.extra_args == []


def test_selector_iter_defaults_to_single_none() -> None:
    assert DbtRunConfig().selector_iter == [None]
    assert DbtRunConfig(selectors="a,b").selector_iter == ["a", "b"]


def test_is_materializing() -> None:
    assert DbtRunConfig(command="build").is_materializing
    assert DbtRunConfig(command="run").is_materializing
    assert not DbtRunConfig(command="test").is_materializing


# ---------------------------------------------------------------------------
# from_cli mode derivation
# ---------------------------------------------------------------------------


def test_from_cli_defaults_to_scoped() -> None:
    cfg = DbtRunConfig.from_cli(hospital_ids="h1", selector=DEFAULT_SELECTOR)
    assert cfg.mode is DbtRunMode.SCOPED
    assert cfg.command == DEFAULT_COMMAND
    assert cfg.selectors == []
    assert cfg.hospital_ids == ["h1"]


def test_from_cli_modes() -> None:
    assert DbtRunConfig.from_cli(all_hospitals=True).mode is DbtRunMode.ALL_CURRENT
    assert DbtRunConfig.from_cli(per_snapshot=True).mode is DbtRunMode.PER_SNAPSHOT
    assert DbtRunConfig.from_cli(full_rebuild=True).mode is DbtRunMode.FULL_REBUILD


def test_from_cli_empty_selector_disables_selection() -> None:
    cfg = DbtRunConfig.from_cli(full_rebuild=True, selector="")
    assert cfg.selectors == []
    assert cfg.selector_iter == [None]


# ---------------------------------------------------------------------------
# from_cli mutually-exclusive flag guards
# ---------------------------------------------------------------------------


def test_full_rebuild_rejects_scope_flags() -> None:
    with pytest.raises(ValueError, match="--full-rebuild cannot be combined"):
        DbtRunConfig.from_cli(full_rebuild=True, hospital_ids="h1")


def test_per_snapshot_rejects_scope_flags() -> None:
    with pytest.raises(ValueError, match="--per-snapshot runs every current snapshot"):
        DbtRunConfig.from_cli(per_snapshot=True, hospital_ids="h1")


def test_all_hospitals_rejects_explicit_ids() -> None:
    with pytest.raises(ValueError, match="--all-hospitals cannot be combined"):
        DbtRunConfig.from_cli(all_hospitals=True, snapshot_ids="snap-a")


def test_full_refresh_requires_per_snapshot() -> None:
    with pytest.raises(ValueError, match="--full-refresh requires --per-snapshot"):
        DbtRunConfig.from_cli(hospital_ids="h1", full_refresh=True)
    with pytest.raises(ValueError, match="--full-refresh requires --per-snapshot"):
        DbtRunConfig.from_cli(all_hospitals=True, full_refresh=True)


# ---------------------------------------------------------------------------
# validate()
# ---------------------------------------------------------------------------


def test_invalid_retention_mode_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(RETENTION_MODE_ENV, "invalid")
    with pytest.raises(ValueError, match=RETENTION_MODE_ENV):
        DbtRunConfig(hospital_ids="h1")


def test_full_refresh_in_extra_args_rejected() -> None:
    with pytest.raises(ValueError, match="Do not pass --full-refresh in extra_args"):
        DbtRunConfig(hospital_ids="h1", extra_args=["--full-refresh"])


def test_full_refresh_only_for_materializing_command() -> None:
    with pytest.raises(ValueError, match="full_refresh only applies to dbt build or run"):
        DbtRunConfig(mode=DbtRunMode.PER_SNAPSHOT, command="test", full_refresh=True)


def test_full_refresh_only_for_per_snapshot_or_rebuild() -> None:
    with pytest.raises(ValueError, match="full_refresh only applies to per-snapshot"):
        DbtRunConfig(mode=DbtRunMode.SCOPED, command="build", full_refresh=True)


def test_per_snapshot_full_refresh_allows_partial_selector() -> None:
    cfg = DbtRunConfig.from_cli(
        per_snapshot=True,
        selector="per_snapshot",
        full_refresh=True,
    )
    assert cfg.mode is DbtRunMode.PER_SNAPSHOT
    assert cfg.selectors == ["per_snapshot"]


def test_full_rebuild_requires_materializing_command() -> None:
    with pytest.raises(ValueError, match="Full rebuild only supports"):
        DbtRunConfig(mode=DbtRunMode.FULL_REBUILD, command="test")


def test_full_rebuild_rejects_scope() -> None:
    with pytest.raises(ValueError, match="Full rebuild runs unscoped"):
        DbtRunConfig(mode=DbtRunMode.FULL_REBUILD, hospital_ids="h1")
