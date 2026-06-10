"""Isolated runtime checks for consumer-side snapshot scoping."""

from __future__ import annotations

from pathlib import Path

import pytest

duckdb = pytest.importorskip("duckdb", reason="DuckDB is required for scoped-input runtime tests")


def _sql_path(path: Path) -> str:
    return str(path).replace("'", "''")


def test_scoped_consumer_preserves_unscoped_staging_and_incremental_isolation() -> None:
    connection = duckdb.connect()
    connection.execute(
        """
        create table bronze_rows(snapshot_id varchar, row_id integer, value varchar);
        insert into bronze_rows values
            ('snapshot-a', 1, 'new-a'),
            ('snapshot-b', 1, 'stable-b');
        create view stg_bronze__rows as select * from bronze_rows;

        create table silver_rows(snapshot_id varchar, row_id integer, value varchar);
        insert into silver_rows values
            ('snapshot-a', 1, 'old-a'),
            ('snapshot-b', 1, 'stable-b');
        """
    )

    assert connection.execute(
        "select count(distinct snapshot_id) from stg_bronze__rows"
    ).fetchone() == (2,)

    scoped_input = """
        select *
        from stg_bronze__rows
        where 1 = 1
            and snapshot_id in ('snapshot-a')
    """
    assert connection.execute(scoped_input).fetchall() == [("snapshot-a", 1, "new-a")]
    assert connection.execute("select * from stg_bronze__rows where 1 = 1").fetchall() == [
        ("snapshot-a", 1, "new-a"),
        ("snapshot-b", 1, "stable-b"),
    ]

    connection.execute("delete from silver_rows where snapshot_id = 'snapshot-a'")
    connection.execute(f"insert into silver_rows {scoped_input}")

    assert connection.execute(
        "select * from silver_rows order by snapshot_id, row_id"
    ).fetchall() == [
        ("snapshot-a", 1, "new-a"),
        ("snapshot-b", 1, "stable-b"),
    ]
    assert connection.execute("select * from stg_bronze__rows order by snapshot_id").fetchall() == [
        ("snapshot-a", 1, "new-a"),
        ("snapshot-b", 1, "stable-b"),
    ]


def test_scoped_derived_table_prunes_hive_partition(tmp_path: Path) -> None:
    connection = duckdb.connect()
    for snapshot_id in ("snapshot-a", "snapshot-b"):
        partition = tmp_path / f"snapshot_id={snapshot_id}"
        partition.mkdir()
        connection.execute(
            f"""
            copy (
                select 1 as row_id, '{snapshot_id}' as value
            ) to '{_sql_path(partition / "part.parquet")}' (format parquet)
            """
        )

    parquet_glob = _sql_path(tmp_path / "**" / "*.parquet")
    plan_rows = connection.execute(
        f"""
        explain analyze
        select *
        from (
            select *
            from read_parquet('{parquet_glob}', hive_partitioning=true)
            where 1 = 1
                and snapshot_id in ('snapshot-a')
        )
        """
    ).fetchall()
    plan = "\n".join(str(value) for row in plan_rows for value in row)

    assert "File Filters:" in plan
    assert "Scanning Files: 1/2" in plan
    assert "Total Files Read: 1" in plan

    assert connection.execute(
        f"select count(distinct snapshot_id) from read_parquet('{parquet_glob}', "
        "hive_partitioning=true)"
    ).fetchone() == (2,)
