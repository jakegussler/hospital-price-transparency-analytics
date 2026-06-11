from __future__ import annotations

import logging
from types import SimpleNamespace

import pytest

import hpt.cli as cli
from hpt.audit import AuditStore
from hpt.ingest.download import DownloadResult, Outcome


@pytest.fixture(autouse=True)
def reset_hpt_logging():
    root = logging.getLogger("hpt")
    for handler in list(root.handlers):
        root.removeHandler(handler)
        handler.close()
    if hasattr(root, "_hpt_log_paths"):
        delattr(root, "_hpt_log_paths")
    yield
    for handler in list(root.handlers):
        root.removeHandler(handler)
        handler.close()
    if hasattr(root, "_hpt_log_paths"):
        delattr(root, "_hpt_log_paths")


def test_download_logic_writes_completed_audit_run(monkeypatch, tmp_path):
    hospital = SimpleNamespace(
        hospital_id="h1",
        mrf_source=SimpleNamespace(url="https://example.test/mrf.json"),
    )
    monkeypatch.setattr(cli, "BronzeStorage", lambda _uri: object())
    monkeypatch.setattr(cli, "SnapshotManager", lambda _storage: object())
    monkeypatch.setattr(
        cli,
        "_load_hospitals_for_target",
        lambda _log, _ids, _registry: [hospital],
    )
    monkeypatch.setattr(
        cli,
        "download_all",
        lambda *_args: [
            DownloadResult(
                hospital_id="h1",
                outcome=Outcome.UNCHANGED,
                file_hash="abc",
                resolved_snapshot_id="s1",
                hash_changed=False,
            )
        ],
    )

    exit_code = cli.download_logic(
        hospital_ids=["h1"],
        raw_base_uri=tmp_path / "raw",
        audit_root=tmp_path / "audit",
    )

    assert exit_code == 0
    run_files = list((tmp_path / "audit" / "runs").rglob("*.parquet"))
    assert len(run_files) == 2
    run_id = run_files[0].name.split("_", 1)[0]
    result = AuditStore(tmp_path / "audit").get_run(run_id)
    assert result is not None
    assert result["run"]["terminal_status"] == "success"
    assert result["attempts"][0]["snapshot_id"] == "s1"
    assert result["attempts"][0]["download_outcome"] == "unchanged"


def test_audit_start_failure_makes_command_fail(monkeypatch, tmp_path):
    def fail_start(**_kwargs):
        raise OSError("audit unavailable")

    monkeypatch.setattr(cli, "_start_audit", fail_start)

    exit_code = cli.download_logic(
        hospital_ids=["h1"],
        raw_base_uri=tmp_path / "raw",
        audit_root=tmp_path / "audit",
    )

    assert exit_code == 2
