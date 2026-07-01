from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from hpt.presentation.evidence_export import (
    EVIDENCE_EXPORTS,
    EvidenceExportError,
    export_evidence_artifact,
)

duckdb = pytest.importorskip("duckdb")


def _create_source_database(
    path: Path, *, omit: str | None = None, empty_required: bool = False
) -> None:
    with duckdb.connect(str(path)) as con:
        con.execute("create schema main_gold")
        for spec in EVIDENCE_EXPORTS:
            if spec.source_table == omit:
                continue
            row_count = 0 if empty_required and spec.require_nonzero else 1
            con.execute(
                f"""
                create table main_gold.{spec.source_table} as
                select
                    range::integer as id,
                    '{spec.public_name}'::varchar as public_name
                from range({row_count})
                """
            )
        con.execute(
            """
            create table main_gold.gld_fct__rate_observations as
            select 1 as should_not_export
            """
        )


def test_export_writes_only_allowlisted_parquet_and_metadata(tmp_path: Path) -> None:
    source = tmp_path / "warehouse.duckdb"
    target = tmp_path / "evidence_data"
    _create_source_database(source)

    row_counts = export_evidence_artifact(
        source_duckdb=source,
        target_dir=target,
        replace=True,
        exported_at=datetime(2026, 6, 29, tzinfo=UTC),
        compute_source_hash=False,
    )

    expected_names = {spec.public_name for spec in EVIDENCE_EXPORTS}
    assert row_counts == {name: 1 for name in expected_names}
    assert {path.name for path in target.glob("*.parquet")} == {
        *(f"{name}.parquet" for name in expected_names),
        "public_metadata.parquet",
    }
    assert not (target / "gld_fct__rate_observations.parquet").exists()

    with duckdb.connect() as con:
        metadata = con.execute(
            "select public_table_name, row_count, corpus_label from read_parquet(?) order by 1",
            [str(target / "public_metadata.parquet")],
        ).fetchall()
    assert metadata == [(name, 1, "Nashville metro") for name in sorted(expected_names)]


def test_export_replace_swaps_generated_data_directory(tmp_path: Path) -> None:
    source = tmp_path / "warehouse.duckdb"
    target = tmp_path / "evidence_data"
    target.mkdir()
    (target / "stale.parquet").write_text("stale", encoding="utf-8")
    _create_source_database(source)

    export_evidence_artifact(
        source_duckdb=source,
        target_dir=target,
        replace=True,
        compute_source_hash=False,
    )

    assert not (target / "stale.parquet").exists()
    assert (target / "hospital_overview.parquet").exists()


def test_export_refuses_nonempty_target_without_replace(tmp_path: Path) -> None:
    source = tmp_path / "warehouse.duckdb"
    target = tmp_path / "evidence_data"
    target.mkdir()
    (target / "stale.parquet").write_text("stale", encoding="utf-8")
    _create_source_database(source)

    with pytest.raises(EvidenceExportError, match="Pass --replace"):
        export_evidence_artifact(
            source_duckdb=source,
            target_dir=target,
            compute_source_hash=False,
        )

    assert (target / "stale.parquet").exists()


def test_export_fails_when_required_mart_is_missing(tmp_path: Path) -> None:
    source = tmp_path / "warehouse.duckdb"
    target = tmp_path / "evidence_data"
    _create_source_database(source, omit="gld_bi__featured_services")

    with pytest.raises(EvidenceExportError, match="gld_bi__featured_services"):
        export_evidence_artifact(
            source_duckdb=source,
            target_dir=target,
            replace=True,
            compute_source_hash=False,
        )


def test_export_fails_when_required_mart_is_empty(tmp_path: Path) -> None:
    source = tmp_path / "warehouse.duckdb"
    target = tmp_path / "evidence_data"
    _create_source_database(source, empty_required=True)

    with pytest.raises(EvidenceExportError, match="zero rows"):
        export_evidence_artifact(
            source_duckdb=source,
            target_dir=target,
            replace=True,
            compute_source_hash=False,
        )
