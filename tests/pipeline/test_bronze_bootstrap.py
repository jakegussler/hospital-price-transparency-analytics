"""Tests for dbt Bronze source schema sentinels."""

from __future__ import annotations

from pathlib import Path

import polars as pl
import pyarrow.parquet as pq
import pytest
import yaml

from hpt.parsers.schemas import BRONZE_BOOTSTRAP_SCHEMAS
from hpt.pipeline.bronze_bootstrap import (
    BOOTSTRAP_FILE_NAME,
    BOOTSTRAP_SNAPSHOT_ID,
    ensure_bronze_source_bootstrap,
)

duckdb = pytest.importorskip("duckdb", reason="DuckDB is required for Bronze bootstrap tests")

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SOURCE_DEFINITIONS = PROJECT_ROOT / "transform" / "models" / "staging" / "_bronze_sources.yml"


def _write_real_snapshot_metadata(bronze_root: Path) -> None:
    path = bronze_root / "hospital_mrf_snapshots" / "snapshot_id=real-snapshot"
    path.mkdir(parents=True)
    pl.DataFrame(
        [{"snapshot_id": "real-snapshot"}],
        schema={"snapshot_id": pl.Utf8},
    ).write_parquet(path / "part-000.parquet")


def _sentinel(bronze_root: Path, table_name: str) -> Path:
    return (
        bronze_root
        / table_name
        / f"snapshot_id={BOOTSTRAP_SNAPSHOT_ID}"
        / BOOTSTRAP_FILE_NAME
    )


def _write_source_definitions(path: Path, table_names: list[str]) -> None:
    path.write_text(
        yaml.safe_dump(
            {
                "version": 2,
                "sources": [
                    {
                        "name": "bronze",
                        "tables": [{"name": name} for name in table_names],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )


def test_bootstrap_creates_every_declared_zero_row_source_and_binds_csv(
    tmp_path: Path,
) -> None:
    bronze_root = tmp_path / "bronze"
    _write_real_snapshot_metadata(bronze_root)

    result = ensure_bronze_source_bootstrap(bronze_root, SOURCE_DEFINITIONS)

    assert set(result.created) == set(BRONZE_BOOTSTRAP_SCHEMAS)
    assert result.updated == ()
    assert result.unchanged == ()
    for table_name, schema in BRONZE_BOOTSTRAP_SCHEMAS.items():
        sentinel = _sentinel(bronze_root, table_name)
        table = pq.ParquetFile(sentinel).read()
        assert table.num_rows == 0
        assert table.schema.equals(pl.DataFrame(schema=schema).to_arrow().schema)

    csv_sentinel = _sentinel(bronze_root, "csv_charge_rows")
    assert {"code_1", "code_1_type"} <= set(pq.read_schema(csv_sentinel).names)

    connection = duckdb.connect()
    for table_name in BRONZE_BOOTSTRAP_SCHEMAS:
        pattern = bronze_root / table_name / "**" / "*.parquet"
        relation = (
            f"read_parquet('{pattern}', hive_partitioning=true, union_by_name=true)"
        )
        assert connection.sql(
            f"select count(*) from {relation} where snapshot_id = '{BOOTSTRAP_SNAPSHOT_ID}'"
        ).fetchone() == (0,)
    csv_pattern = bronze_root / "csv_charge_rows" / "**" / "*.parquet"
    assert connection.sql(
        f"select columns('^code_[0-9]+(_type)?$') "
        f"from read_parquet('{csv_pattern}', hive_partitioning=true, union_by_name=true)"
    ).fetchall() == []
    assert connection.sql(
        f"select distinct snapshot_id from read_parquet('{csv_pattern}', "
        "hive_partitioning=true, union_by_name=true)"
    ).fetchall() == []


def test_bootstrap_is_idempotent_and_repairs_stale_or_corrupt_sentinels(
    tmp_path: Path,
) -> None:
    bronze_root = tmp_path / "bronze"
    _write_real_snapshot_metadata(bronze_root)
    ensure_bronze_source_bootstrap(bronze_root, SOURCE_DEFINITIONS)

    unchanged = ensure_bronze_source_bootstrap(bronze_root, SOURCE_DEFINITIONS)
    assert set(unchanged.unchanged) == set(BRONZE_BOOTSTRAP_SCHEMAS)

    stale = _sentinel(bronze_root, "csv_charge_rows")
    pl.DataFrame(schema={"snapshot_id": pl.Utf8}).write_parquet(stale)
    corrupt = _sentinel(bronze_root, "drug_information")
    corrupt.write_text("not parquet", encoding="utf-8")

    repaired = ensure_bronze_source_bootstrap(bronze_root, SOURCE_DEFINITIONS)
    assert set(repaired.updated) == {"csv_charge_rows", "drug_information"}
    assert pq.read_schema(stale).equals(
        pl.DataFrame(schema=BRONZE_BOOTSTRAP_SCHEMAS["csv_charge_rows"]).to_arrow().schema
    )


def test_bootstrap_refuses_corpus_without_real_snapshot_metadata(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="No non-bootstrap hospital_mrf_snapshots"):
        ensure_bronze_source_bootstrap(tmp_path / "bronze", SOURCE_DEFINITIONS)


@pytest.mark.parametrize(
    ("table_names", "match"),
    [
        (["hospital_mrf_snapshots", "hospital_mrf_snapshots"], "Duplicate declared"),
        (["hospital_mrf_snapshots", "unknown_table"], "registry mismatch"),
    ],
)
def test_bootstrap_rejects_invalid_source_declarations(
    tmp_path: Path,
    table_names: list[str],
    match: str,
) -> None:
    bronze_root = tmp_path / "bronze"
    _write_real_snapshot_metadata(bronze_root)
    source_definitions = tmp_path / "sources.yml"
    _write_source_definitions(source_definitions, table_names)

    with pytest.raises(ValueError, match=match):
        ensure_bronze_source_bootstrap(bronze_root, source_definitions)


def test_bootstrap_rejects_malformed_source_declarations(tmp_path: Path) -> None:
    bronze_root = tmp_path / "bronze"
    _write_real_snapshot_metadata(bronze_root)
    source_definitions = tmp_path / "sources.yml"
    source_definitions.write_text("not_sources: true\n", encoding="utf-8")

    with pytest.raises(ValueError, match="Malformed Bronze source definitions"):
        ensure_bronze_source_bootstrap(bronze_root, source_definitions)
