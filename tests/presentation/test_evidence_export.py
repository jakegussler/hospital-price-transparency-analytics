from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from hpt.presentation.evidence_export import (
    EVIDENCE_EXPORTS,
    EvidenceExportError,
    assert_evidence_readiness,
    check_evidence_readiness,
    export_evidence_artifact,
)

duckdb = pytest.importorskip("duckdb")


def _create_source_database(
    path: Path, *, omit: str | None = None, row_counts: dict[str, int] | None = None
) -> None:
    row_counts = row_counts or {}
    with duckdb.connect(str(path)) as con:
        con.execute("create schema main_gold")
        for spec in EVIDENCE_EXPORTS:
            if spec.source_table == omit:
                continue
            row_count = row_counts.get(spec.public_name, 1)
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


def _read_parquet_row_count(path: Path) -> int:
    with duckdb.connect() as con:
        return int(con.execute("select count(*) from read_parquet(?)", [str(path)]).fetchone()[0])


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


def test_export_allows_empty_allowlisted_marts(tmp_path: Path) -> None:
    source = tmp_path / "warehouse.duckdb"
    target = tmp_path / "evidence_data"
    _create_source_database(
        source,
        row_counts={
            "featured_services": 0,
            "hospital_service_rankings": 0,
        },
    )

    row_counts = export_evidence_artifact(
        source_duckdb=source,
        target_dir=target,
        replace=True,
        compute_source_hash=False,
    )

    assert row_counts["featured_services"] == 0
    assert row_counts["hospital_service_rankings"] == 0
    assert _read_parquet_row_count(target / "featured_services.parquet") == 0


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


def test_evidence_readiness_reports_empty_demo_marts(tmp_path: Path) -> None:
    source = tmp_path / "warehouse.duckdb"
    _create_source_database(
        source,
        row_counts={
            "hospital_overview": 1,
            "service_market_explorer": 3,
            "featured_services": 0,
        },
    )

    issues = check_evidence_readiness(source_duckdb=source)

    assert [(issue.public_name, issue.row_count, issue.min_rows) for issue in issues] == [
        ("featured_services", 0, 1)
    ]
    with pytest.raises(EvidenceExportError, match="Evidence readiness checks failed"):
        assert_evidence_readiness(source_duckdb=source)


def test_evidence_readiness_passes_when_demo_marts_have_rows(tmp_path: Path) -> None:
    source = tmp_path / "warehouse.duckdb"
    _create_source_database(source)

    assert check_evidence_readiness(source_duckdb=source) == []
    assert_evidence_readiness(source_duckdb=source)


def _create_dictionary_yml(path: Path, *, omit: str | None = None) -> None:
    lines = ["version: 2", "", "models:"]
    for spec in EVIDENCE_EXPORTS:
        if spec.source_table == omit:
            continue
        lines.extend(
            [
                f"  - name: {spec.source_table}",
                "    description: >",
                f"      Test description for {spec.public_name}.",
                "      Grain: test rows.",
                "    columns:",
                "      - name: id",
                "        description: Test id column.",
                "      - name: public_name",
                "        description: Test public name column.",
            ]
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_export_writes_data_dictionary_and_metadata_build_id(tmp_path: Path) -> None:
    source = tmp_path / "warehouse.duckdb"
    target = tmp_path / "evidence_data"
    dictionary_yml = tmp_path / "_gold_bi_models.yml"
    _create_source_database(source)
    _create_dictionary_yml(dictionary_yml)

    export_evidence_artifact(
        source_duckdb=source,
        target_dir=target,
        replace=True,
        compute_source_hash=False,
        build_id="abc1234",
        dictionary_yml=dictionary_yml,
    )

    dictionary_path = target / "public_data_dictionary.parquet"
    assert dictionary_path.exists()

    with duckdb.connect() as con:
        documented_tables = {
            row[0]
            for row in con.execute(
                "select distinct public_table_name from read_parquet(?)",
                [str(dictionary_path)],
            ).fetchall()
        }
        table_description = con.execute(
            """
            select table_description
            from read_parquet(?)
            where public_table_name = 'hospital_overview'
            limit 1
            """,
            [str(dictionary_path)],
        ).fetchone()[0]
        build_ids = {
            row[0]
            for row in con.execute(
                "select distinct build_id from read_parquet(?)",
                [str(target / "public_metadata.parquet")],
            ).fetchall()
        }

    expected_tables = {spec.public_name for spec in EVIDENCE_EXPORTS} | {
        "public_metadata",
        "public_data_dictionary",
    }
    assert documented_tables == expected_tables
    assert "Grain: test rows." in table_description
    assert build_ids == {"abc1234"}


def test_export_fails_when_dictionary_model_is_missing(tmp_path: Path) -> None:
    source = tmp_path / "warehouse.duckdb"
    target = tmp_path / "evidence_data"
    dictionary_yml = tmp_path / "_gold_bi_models.yml"
    _create_source_database(source)
    _create_dictionary_yml(dictionary_yml, omit="gld_bi__market_summary")

    with pytest.raises(EvidenceExportError, match="gld_bi__market_summary"):
        export_evidence_artifact(
            source_duckdb=source,
            target_dir=target,
            replace=True,
            compute_source_hash=False,
            dictionary_yml=dictionary_yml,
        )

    assert not target.exists()


def test_export_fails_when_dictionary_yml_does_not_exist(tmp_path: Path) -> None:
    source = tmp_path / "warehouse.duckdb"
    target = tmp_path / "evidence_data"
    _create_source_database(source)

    with pytest.raises(EvidenceExportError, match="does not exist"):
        export_evidence_artifact(
            source_duckdb=source,
            target_dir=target,
            replace=True,
            compute_source_hash=False,
            dictionary_yml=tmp_path / "missing.yml",
        )


def test_export_writes_downloads_bundle(tmp_path: Path) -> None:
    source = tmp_path / "warehouse.duckdb"
    target = tmp_path / "evidence_data"
    downloads = tmp_path / "static" / "downloads"
    dictionary_yml = tmp_path / "_gold_bi_models.yml"
    _create_source_database(source)
    _create_dictionary_yml(dictionary_yml)

    export_evidence_artifact(
        source_duckdb=source,
        target_dir=target,
        replace=True,
        compute_source_hash=False,
        build_id="abc1234",
        dictionary_yml=dictionary_yml,
        downloads_dir=downloads,
    )

    for spec in EVIDENCE_EXPORTS:
        assert (downloads / f"{spec.public_name}.parquet").exists()
        assert (downloads / f"{spec.public_name}.csv").exists()
    assert (downloads / "public_data_dictionary.parquet").exists()
    assert (downloads / "public_data_dictionary.csv").exists()

    readme = (downloads / "README.md").read_text(encoding="utf-8")
    assert "Nashville metro" in readme
    assert "abc1234" in readme
    assert "not legal-compliance findings" in readme

    with duckdb.connect() as con:
        csv_rows = con.execute(
            "select count(*) from read_csv_auto(?)",
            [str(downloads / "hospital_overview.csv")],
        ).fetchone()[0]
        csv_names = dict(
            con.execute(
                "select public_table_name, csv_file_name from read_parquet(?)",
                [str(target / "public_metadata.parquet")],
            ).fetchall()
        )
    assert csv_rows == 1
    assert csv_names == {spec.public_name: f"{spec.public_name}.csv" for spec in EVIDENCE_EXPORTS}


def test_export_gzips_large_download_csvs(tmp_path: Path) -> None:
    source = tmp_path / "warehouse.duckdb"
    target = tmp_path / "evidence_data"
    downloads = tmp_path / "static" / "downloads"
    dictionary_yml = tmp_path / "_gold_bi_models.yml"
    _create_source_database(source)
    _create_dictionary_yml(dictionary_yml)

    export_evidence_artifact(
        source_duckdb=source,
        target_dir=target,
        replace=True,
        compute_source_hash=False,
        dictionary_yml=dictionary_yml,
        downloads_dir=downloads,
        csv_gzip_threshold_bytes=1,
    )

    for spec in EVIDENCE_EXPORTS:
        assert (downloads / f"{spec.public_name}.csv.gz").exists()
        assert not (downloads / f"{spec.public_name}.csv").exists()
    assert (downloads / "public_data_dictionary.csv.gz").exists()

    with duckdb.connect() as con:
        csv_names = dict(
            con.execute(
                "select public_table_name, csv_file_name from read_parquet(?)",
                [str(target / "public_metadata.parquet")],
            ).fetchall()
        )
        gz_rows = con.execute(
            "select count(*) from read_csv_auto(?)",
            [str(downloads / "hospital_overview.csv.gz")],
        ).fetchone()[0]
    assert csv_names == {
        spec.public_name: f"{spec.public_name}.csv.gz" for spec in EVIDENCE_EXPORTS
    }
    assert gz_rows == 1


def test_export_downloads_bundle_replaces_previous_bundle(tmp_path: Path) -> None:
    source = tmp_path / "warehouse.duckdb"
    target = tmp_path / "evidence_data"
    downloads = tmp_path / "static" / "downloads"
    dictionary_yml = tmp_path / "_gold_bi_models.yml"
    downloads.mkdir(parents=True)
    (downloads / "stale.csv").write_text("stale", encoding="utf-8")
    _create_source_database(source)
    _create_dictionary_yml(dictionary_yml)

    export_evidence_artifact(
        source_duckdb=source,
        target_dir=target,
        replace=True,
        compute_source_hash=False,
        dictionary_yml=dictionary_yml,
        downloads_dir=downloads,
    )

    assert not (downloads / "stale.csv").exists()
    assert (downloads / "hospital_overview.csv").exists()
