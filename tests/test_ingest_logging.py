from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any

import pytest

import hpt.cli as cli
from hpt.ingest.snapshot import SnapshotRecord
from hpt.logging.log import (
    clear_context,
    configure_logging,
    get_logger,
    log_context,
    set_context,
)
from hpt.registry.models import HospitalSource, MrfSource


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


def _make_hospital(hospital_id: str, expected_format: str = "json") -> HospitalSource:
    return HospitalSource(
        hospital_id=hospital_id,
        canonical_hospital_name=f"{hospital_id.title()} Hospital",
        canonical_state="TN",
        hospital_type="community",
        mrf_source=MrfSource(
            url=f"https://example.com/{hospital_id}/charges.json",
            expected_format=expected_format,
        ),
    )


def _make_snapshot(hospital_id: str) -> SnapshotRecord:
    ingested_at = datetime(2025, 1, 1, tzinfo=UTC)
    return SnapshotRecord(
        snapshot_id=f"{hospital_id}-snapshot",
        hospital_id=hospital_id,
        source_url=f"https://example.com/{hospital_id}/charges.json",
        source_file_name="charges.json",
        file_hash="abc123",
        ingested_at=ingested_at,
        valid_from=ingested_at,
    )


def test_configure_logging_writes_stdout_and_json_files(tmp_path):
    log_paths = configure_logging(log_level="INFO", logs_root=tmp_path / "logs", run_id="run-123")
    log = get_logger("tests.ingest_logging")

    log.info("test_event", extra={"hospital_id": "h1"})

    stdout_text = log_paths.std_out_path.read_text(encoding="utf-8")
    json_lines = log_paths.json_path.read_text(encoding="utf-8").splitlines()

    assert log_paths.std_out_path.parent.name == "std_out"
    assert log_paths.json_path.parent.name == "json"
    assert log_paths.failures_dir.name == "failures"
    assert "test_event" in stdout_text
    assert "hospital_id=h1" in stdout_text
    assert json.loads(json_lines[-1])["msg"] == "test_event"
    assert json.loads(json_lines[-1])["hospital_id"] == "h1"
    assert json.loads(json_lines[-1])["run_id"] == "run-123"
    assert log_paths.run_id == "run-123"


def _json_records(json_path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in json_path.read_text(encoding="utf-8").splitlines()]


def test_log_context_binds_fields_and_restores_on_exit(tmp_path):
    log_paths = configure_logging(log_level="INFO", logs_root=tmp_path / "logs", run_id="run-ctx")
    log = get_logger("tests.ingest_logging")

    with log_context(snapshot_id="snap-1", hospital_id="h1"):
        log.info("inside_event")
    log.info("outside_event")

    records = {rec["msg"]: rec for rec in _json_records(log_paths.json_path)}
    assert records["inside_event"]["snapshot_id"] == "snap-1"
    assert records["inside_event"]["hospital_id"] == "h1"
    # The context is unbound once the block exits.
    assert "snapshot_id" not in records["outside_event"]
    assert "hospital_id" not in records["outside_event"]


def test_explicit_extra_wins_over_ambient_context(tmp_path):
    log_paths = configure_logging(log_level="INFO", logs_root=tmp_path / "logs", run_id="run-ctx2")
    log = get_logger("tests.ingest_logging")

    with log_context(hospital_id="ambient"):
        log.info("explicit_event", extra={"hospital_id": "explicit"})

    record = _json_records(log_paths.json_path)[-1]
    assert record["hospital_id"] == "explicit"


def test_set_and_clear_context_are_incremental(tmp_path):
    log_paths = configure_logging(log_level="INFO", logs_root=tmp_path / "logs", run_id="run-ctx3")
    log = get_logger("tests.ingest_logging")

    set_context(snapshot_id="snap-1")
    set_context(hospital_id="h1")
    try:
        log.info("first")
        clear_context("snapshot_id")
        log.info("second")
    finally:
        clear_context("snapshot_id", "hospital_id")

    records = {rec["msg"]: rec for rec in _json_records(log_paths.json_path)}
    assert records["first"]["snapshot_id"] == "snap-1"
    assert records["first"]["hospital_id"] == "h1"
    assert "snapshot_id" not in records["second"]
    assert records["second"]["hospital_id"] == "h1"


def test_ingest_logic_writes_descriptive_failure_logs(monkeypatch, tmp_path):
    logs_root = tmp_path / "logs"
    hospitals = [_make_hospital("missing"), _make_hospital("broken")]
    snapshots_by_hospital = {"broken": _make_snapshot("broken")}

    class FakeSnapshots:
        def __init__(self, storage: object) -> None:
            self.storage = storage

        def get_current_snapshot(self, hospital_id: str) -> SnapshotRecord | None:
            return snapshots_by_hospital.get(hospital_id)

    def fail_ingest_snapshot(**kwargs: Any) -> dict[str, Any]:
        raise RuntimeError("parser exploded while reading charges.json")

    monkeypatch.setattr("hpt.logging.log.get_default_logs_root", lambda: logs_root)
    monkeypatch.setattr(cli, "BronzeStorage", lambda raw_base_uri: object())
    monkeypatch.setattr(cli, "SnapshotManager", FakeSnapshots)
    monkeypatch.setattr(
        cli,
        "_load_hospitals_for_target",
        lambda log, hospital_ids, registry_path: hospitals,
    )
    monkeypatch.setattr(cli, "ingest_snapshot", fail_ingest_snapshot)

    exit_code = cli.ingest_logic(
        hospital_ids=["missing", "broken"],
        raw_base_uri=tmp_path / "raw",
        bronze_root=tmp_path / "bronze",
        quarantine_root=tmp_path / "quarantine",
        audit_root=tmp_path / "audit",
        log_level="INFO",
    )

    assert exit_code == 2

    std_out_logs = list((logs_root / "std_out").glob("*.log"))
    json_logs = list((logs_root / "json").glob("*.jsonl"))
    failure_text_logs = list((logs_root / "failures").glob("*_ingest_failures.log"))
    failure_json_logs = list((logs_root / "failures").glob("*_ingest_failures.jsonl"))

    assert len(std_out_logs) == 1
    assert len(json_logs) == 1
    assert len(failure_text_logs) == 1
    assert len(failure_json_logs) == 1

    failure_text = failure_text_logs[0].read_text(encoding="utf-8")
    assert "No current snapshot metadata found for hospital missing" in failure_text
    assert "parser exploded while reading charges.json" in failure_text
    assert "broken-snapshot" in failure_text

    failure_records = [
        json.loads(line) for line in failure_json_logs[0].read_text(encoding="utf-8").splitlines()
    ]
    assert [record["failure_type"] for record in failure_records] == [
        "no_snapshot",
        "ingest_failed",
    ]
    assert failure_records[0]["hospital_id"] == "missing"
    assert failure_records[1]["snapshot_id"] == "broken-snapshot"
    assert failure_records[1]["exception_type"] == "RuntimeError"

    std_out_text = std_out_logs[0].read_text(encoding="utf-8")
    assert "ingest_run_complete" in std_out_text
    assert "failure_count=2" in std_out_text
    assert "parser exploded while reading charges.json" in std_out_text

    json_events = [
        json.loads(line) for line in json_logs[0].read_text(encoding="utf-8").splitlines()
    ]
    complete_event = next(event for event in json_events if event["msg"] == "ingest_run_complete")
    assert complete_event["failure_count"] == 2
    assert complete_event["failures"][0]["failure_type"] == "no_snapshot"
