"""Tests for the `hpt clear-snapshot` CLI logic."""

from __future__ import annotations

import pytest

from hpt.cli import clear_snapshot_logic


class FakeManager:
    """Records clear_snapshots calls and returns a configurable success flag."""

    def __init__(self, success: bool = True) -> None:
        self._success = success
        self.calls: list[list[str]] = []

    def clear_snapshots(self, snapshot_ids: list[str]) -> bool:
        self.calls.append(list(snapshot_ids))
        return self._success


def _patch_manager(monkeypatch: pytest.MonkeyPatch, manager: FakeManager) -> None:
    monkeypatch.setattr("hpt.cli.DbtManager", lambda *_a, **_k: manager)


def test_clear_snapshot_logic_passes_cleaned_ids(monkeypatch: pytest.MonkeyPatch) -> None:
    manager = FakeManager()
    _patch_manager(monkeypatch, manager)

    exit_code = clear_snapshot_logic(snapshot_ids=" snap-a , snap-b ")

    assert exit_code == 0
    assert manager.calls == [["snap-a", "snap-b"]]


def test_clear_snapshot_logic_accepts_list(monkeypatch: pytest.MonkeyPatch) -> None:
    manager = FakeManager()
    _patch_manager(monkeypatch, manager)

    assert clear_snapshot_logic(snapshot_ids=["snap-a"]) == 0
    assert manager.calls == [["snap-a"]]


def test_clear_snapshot_logic_returns_one_on_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    manager = FakeManager(success=False)
    _patch_manager(monkeypatch, manager)

    assert clear_snapshot_logic(snapshot_ids="snap-a") == 1


def test_clear_snapshot_logic_rejects_empty_ids(monkeypatch: pytest.MonkeyPatch) -> None:
    manager = FakeManager()
    _patch_manager(monkeypatch, manager)

    assert clear_snapshot_logic(snapshot_ids="  ,  ") == 2
    assert manager.calls == []
