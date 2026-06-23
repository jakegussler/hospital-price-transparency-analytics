"""Runtime contract checks for the custom snapshot_replace incremental strategy."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from dbt.adapters.factory import cleanup_connections
from dbt.cli.main import dbtRunner

duckdb = pytest.importorskip("duckdb", reason="DuckDB is required for snapshot strategy tests")

PROJECT_ROOT = Path(__file__).resolve().parents[2]
REAL_MACRO_DIR = PROJECT_ROOT / "transform" / "macros"

MODEL_SQL = """
{{ config(
    materialized='incremental',
    incremental_strategy='snapshot_replace',
    unique_key=var('strategy_unique_key', 'snapshot_id'),
    incremental_predicates=var('strategy_incremental_predicates', none)
) }}

select *
from (
    select
        cast(null as varchar) as snapshot_id,
        cast(null as integer) as row_id,
        cast(null as varchar) as value
    where false
    {% for row in var('rows', []) %}
    union all
    select
        {% if row['snapshot_id'] is none %}
        cast(null as varchar),
        {% else %}
        {{ dbt.string_literal(dbt.escape_single_quotes(row['snapshot_id'])) }},
        {% endif %}
        {{ row['row_id'] }},
        {{ dbt.string_literal(dbt.escape_single_quotes(row['value'])) }}
    {% endfor %}
) rows
"""


def _write_project(project_dir: Path, database_path: Path) -> None:
    (project_dir / "models").mkdir(parents=True)
    (project_dir / "macros").mkdir()
    (project_dir / "models" / "snapshot_rows.sql").write_text(MODEL_SQL)
    (project_dir / "dbt_project.yml").write_text(
        """
name: snapshot_replace_runtime
version: "1.0"
config-version: 2
profile: snapshot_replace_runtime
model-paths: ["models"]
macro-paths: ["macros"]
"""
    )
    (project_dir / "profiles.yml").write_text(
        f"""
snapshot_replace_runtime:
  target: dev
  outputs:
    dev:
      type: duckdb
      path: "{database_path}"
      threads: 1
"""
    )
    for macro_name in ("snapshot_filter.sql", "snapshot_replace.sql"):
        shutil.copy(REAL_MACRO_DIR / macro_name, project_dir / "macros" / macro_name)


def _run_dbt(project_dir: Path, *, variables: dict[str, object], full_refresh: bool = False):
    args = [
        "run",
        "--project-dir",
        str(project_dir),
        "--profiles-dir",
        str(project_dir),
        "--target-path",
        str(project_dir / "target"),
        "--log-path",
        str(project_dir / "logs"),
        "--no-partial-parse",
        "--vars",
        json.dumps(variables),
    ]
    if full_refresh:
        args.append("--full-refresh")
    result = dbtRunner().invoke(args)
    cleanup_connections()
    return result


def _rows(database_path: Path) -> list[tuple[str, int, str]]:
    with duckdb.connect(str(database_path)) as connection:
        return connection.execute(
            "select snapshot_id, row_id, value from main.snapshot_rows order by snapshot_id, row_id"
        ).fetchall()


def _result_text(result) -> str:
    return f"{result.exception}\n{result.result}"


def test_snapshot_replace_runtime_contract(tmp_path: Path) -> None:
    project_dir = tmp_path / "project"
    database_path = tmp_path / "snapshot_replace.duckdb"
    _write_project(project_dir, database_path)

    initial = _run_dbt(
        project_dir,
        variables={
            "rows": [
                {"snapshot_id": "snapshot-a", "row_id": 1, "value": "old-a-1"},
                {"snapshot_id": "snapshot-a", "row_id": 2, "value": "old-a-2"},
                {"snapshot_id": "snapshot-b", "row_id": 1, "value": "stable-b"},
            ]
        },
    )
    assert initial.success

    nonzero_replace = _run_dbt(
        project_dir,
        variables={
            "snapshot_ids": ["snapshot-a"],
            "rows": [{"snapshot_id": "snapshot-a", "row_id": 3, "value": "new-a"}],
        },
    )
    assert nonzero_replace.success
    assert _rows(database_path) == [
        ("snapshot-a", 3, "new-a"),
        ("snapshot-b", 1, "stable-b"),
    ]

    zero_replace = _run_dbt(
        project_dir,
        variables={"snapshot_ids": ["snapshot-a"], "rows": []},
    )
    assert zero_replace.success
    assert _rows(database_path) == [("snapshot-b", 1, "stable-b")]

    multi_snapshot_replace = _run_dbt(
        project_dir,
        variables={
            "snapshot_ids": "snapshot-a, snapshot-b",
            "rows": [{"snapshot_id": "snapshot-a", "row_id": 4, "value": "newer-a"}],
        },
    )
    assert multi_snapshot_replace.success
    assert _rows(database_path) == [("snapshot-a", 4, "newer-a")]

    for invalid_snapshot_id in ("snapshot-c", None):
        invalid_output = _run_dbt(
            project_dir,
            variables={
                "snapshot_ids": ["snapshot-a"],
                "rows": [
                    {
                        "snapshot_id": invalid_snapshot_id,
                        "row_id": 5,
                        "value": "invalid",
                    }
                ],
            },
        )
        assert not invalid_output.success
        assert "null or unrequested snapshot_id" in _result_text(invalid_output)
        assert _rows(database_path) == [("snapshot-a", 4, "newer-a")]

    invalid_unique_key = _run_dbt(
        project_dir,
        variables={
            "snapshot_ids": ["snapshot-a"],
            "strategy_unique_key": "row_id",
            "rows": [{"snapshot_id": "snapshot-a", "row_id": 6, "value": "invalid-key"}],
        },
    )
    assert not invalid_unique_key.success
    assert "snapshot_replace requires unique_key='snapshot_id'" in _result_text(invalid_unique_key)
    assert _rows(database_path) == [("snapshot-a", 4, "newer-a")]

    invalid_predicates = _run_dbt(
        project_dir,
        variables={
            "snapshot_ids": ["snapshot-a"],
            "strategy_incremental_predicates": ["snapshot_id = 'snapshot-a'"],
            "rows": [{"snapshot_id": "snapshot-a", "row_id": 6, "value": "invalid-predicate"}],
        },
    )
    assert not invalid_predicates.success
    assert "snapshot_replace does not accept incremental_predicates" in _result_text(
        invalid_predicates
    )
    assert _rows(database_path) == [("snapshot-a", 4, "newer-a")]

    unscoped_incremental = _run_dbt(
        project_dir,
        variables={"rows": [{"snapshot_id": "snapshot-b", "row_id": 6, "value": "unscoped"}]},
    )
    assert not unscoped_incremental.success
    assert "snapshot_replace requires at least one snapshot_id" in _result_text(
        unscoped_incremental
    )
    assert _rows(database_path) == [("snapshot-a", 4, "newer-a")]

    unscoped_full_refresh = _run_dbt(
        project_dir,
        variables={"rows": [{"snapshot_id": "snapshot-b", "row_id": 7, "value": "full-refresh"}]},
        full_refresh=True,
    )
    assert unscoped_full_refresh.success
    assert _rows(database_path) == [("snapshot-b", 7, "full-refresh")]
