from __future__ import annotations

import json

from typer.testing import CliRunner

from hpt.audit import AuditRun, AuditStore
from hpt.cli import cli


def test_audit_run_appends_states_and_joined_attempts(tmp_path):
    store = AuditStore(tmp_path / "audit")
    audit = AuditRun(
        store,
        command="ingest",
        requested_targets=["h1"],
        options={"bronze_root": "/tmp/bronze"},
    )
    audit.record_attempt(
        {
            "attempt_type": "ingest",
            "hospital_id": "h1",
            "snapshot_id": "s1",
            "status": "success",
            "stage_statuses": {"schema_sniff": "success"},
            "stage_elapsed_s": {"schema_sniff": 0.25},
            "bronze_row_counts": {"csv_charge_rows": 4},
            "quarantine_counts": {},
        }
    )
    assert audit.complete(0, target_count=1) == 0

    result = store.get_run(audit.run_id)

    assert result is not None
    assert result["run"]["terminal_status"] == "success"
    assert result["run"]["options"] == {"bronze_root": "/tmp/bronze"}
    assert result["attempts"][0]["bronze_row_counts"] == {"csv_charge_rows": 4}
    assert len(list((tmp_path / "audit" / "runs").rglob("*.parquet"))) == 2


def test_started_only_run_is_reported_as_interrupted(tmp_path):
    store = AuditStore(tmp_path / "audit")
    audit = AuditRun(store, command="download")

    result = store.get_run(audit.run_id)

    assert result is not None
    assert result["run"]["terminal_status"] == "running_or_interrupted"


def test_show_run_outputs_joined_json_and_missing_returns_two(tmp_path):
    store = AuditStore(tmp_path / "audit")
    audit = AuditRun(store, command="download")
    audit.complete(0)
    runner = CliRunner()

    found = runner.invoke(
        cli, ["show-run", "--run-id", audit.run_id, "--audit-root", str(store.root)]
    )
    missing = runner.invoke(
        cli, ["show-run", "--run-id", "missing", "--audit-root", str(store.root)]
    )

    assert found.exit_code == 0
    assert json.loads(found.stdout)["run"]["run_id"] == audit.run_id
    assert missing.exit_code == 2
