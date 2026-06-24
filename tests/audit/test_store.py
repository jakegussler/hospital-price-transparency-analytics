from __future__ import annotations

import json

import pyarrow.dataset as ds
import pytest
from typer.testing import CliRunner

from hpt.audit import AuditRun, AuditStore
from hpt.audit.models import ATTEMPT_SCHEMA, NODE_RESULT_SCHEMA, RUN_SCHEMA
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
    run_partitions = tmp_path / "audit" / "runs"
    run_files = [
        path
        for path in run_partitions.glob("run_date=*/*.parquet")
        if path.name != "_schema.parquet"
    ]
    assert len(run_files) == 2


def test_record_nodes_appends_queryable_node_results(tmp_path):
    store = AuditStore(tmp_path / "audit")
    audit = AuditRun(store, command="run-dbt")
    audit.record_nodes(
        [
            {
                "attempt_id": "a1",
                "node_unique_id": "model.hpt.slv_core__payer_rates",
                "node_name": "slv_core__payer_rates",
                "resource_type": "model",
                "materialization": "incremental",
                "tags": ["silver_core"],
                "node_status": "success",
                "execution_time_s": 3.5,
                "rows_affected": 42,
                "snapshot_ids": ["s1", "s2"],
                "snapshot_count": 2,
            }
        ]
    )

    duckdb = pytest.importorskip("duckdb")
    connection = duckdb.connect()
    glob = store.root / "node_results" / "**" / "*.parquet"
    row = connection.sql(
        f"select node_unique_id, rows_affected, snapshot_count, tags "
        f"from read_parquet('{glob}', hive_partitioning=true) where attempt_id = 'a1'"
    ).fetchone()
    assert row[0] == "model.hpt.slv_core__payer_rates"
    assert row[1] == 42
    assert row[2] == 2
    assert list(row[3]) == ["silver_core"]


def test_record_nodes_with_no_rows_is_a_noop(tmp_path):
    store = AuditStore(tmp_path / "audit")
    audit = AuditRun(store, command="run-dbt")
    audit.record_nodes([])
    node_files = list((store.root / "node_results").glob("run_date=*/*.parquet"))
    assert [path for path in node_files if path.name != "_schema.parquet"] == []


def test_first_append_initializes_empty_schema_datasets(tmp_path):
    store = AuditStore(tmp_path / "audit")

    audit = AuditRun(store, command="download")

    run_sentinel = store.root / "runs" / "run_date=1970-01-01" / "_schema.parquet"
    attempt_sentinel = store.root / "attempts" / "run_date=1970-01-01" / "_schema.parquet"
    node_sentinel = store.root / "node_results" / "run_date=1970-01-01" / "_schema.parquet"
    assert run_sentinel.exists()
    assert attempt_sentinel.exists()
    assert node_sentinel.exists()
    assert ds.dataset(node_sentinel, schema=NODE_RESULT_SCHEMA).count_rows() == 0
    assert ds.dataset(run_sentinel, schema=RUN_SCHEMA).count_rows() == 0
    assert ds.dataset(attempt_sentinel, schema=ATTEMPT_SCHEMA).count_rows() == 0
    duckdb = pytest.importorskip("duckdb")
    connection = duckdb.connect()
    run_glob = store.root / "runs" / "**" / "*.parquet"
    attempt_glob = store.root / "attempts" / "**" / "*.parquet"
    assert connection.sql(
        f"select count(*) from read_parquet('{run_glob}', hive_partitioning=true)"
    ).fetchone() == (1,)
    assert connection.sql(
        f"select count(*) from read_parquet('{attempt_glob}', hive_partitioning=true)"
    ).fetchone() == (0,)
    assert store.get_run(audit.run_id) is not None


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
