"""Offline e2e coverage for ingest -> Bronze -> dbt validation -> dbt Silver."""

from __future__ import annotations

import importlib.util
import shutil
import sys
from datetime import UTC, date, datetime
from pathlib import Path
from types import ModuleType

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from hpt.cli import export_hospitals_seed_logic, ingest_logic, run_dbt_logic
from hpt.registry.seed_export import get_default_hospitals_seed_path
from hpt.utils.paths import to_storage_uri

PROJECT_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_ROOT = PROJECT_ROOT / "tests" / "fixtures" / "e2e"
FIXTURE_BUILDER = PROJECT_ROOT / "scripts" / "build_e2e_fixtures.py"

EXPECTED_BRONZE_COUNTS = {
    "hospital_mrf_snapshots": 3,
    "hospital_locations": 3,
    "type2_npi": 2,
    "csv_charge_rows": 5,
    "standard_charge_info": 2,
    "code_information": 2,
    "standard_charges": 2,
    "payers_information": 2,
}

EXPECTED_SILVER_COUNTS = {
    "main.slv_base__hospital_snapshots": 3,
    "main.slv_base__charge_items": 6,
    "main.slv_base__standard_charges": 6,
    "main.slv_base__payer_rates": 7,
}


@pytest.mark.e2e
def test_offline_fixture_pipeline(tmp_path, monkeypatch):
    fixtures = _load_fixture_builder()
    raw_store = tmp_path / "raw_store"
    bronze_root = tmp_path / "bronze"
    quarantine_root = tmp_path / "quarantine"
    audit_root = tmp_path / "audit"
    reference_root = tmp_path / "reference" / "bronze"
    duckdb_path = tmp_path / "hpt.duckdb"
    duckdb_temp_directory = tmp_path / "duckdb_temp"

    shutil.copytree(FIXTURE_ROOT / "raw", raw_store / "raw")
    shutil.copytree(FIXTURE_ROOT / "metadata", raw_store / "metadata")
    _write_reference_fixture(reference_root)

    monkeypatch.setenv("HPT_RAW_STORAGE_BASE_URI", to_storage_uri(raw_store))
    monkeypatch.setenv("HPT_BRONZE_ROOT", str(bronze_root))
    monkeypatch.setenv("HPT_QUARANTINE_ROOT", str(quarantine_root))
    monkeypatch.setenv("HPT_AUDIT_ROOT", str(audit_root))
    monkeypatch.setenv("HPT_REFERENCE_ROOT", str(reference_root))
    monkeypatch.setenv("HPT_DUCKDB_PATH", str(duckdb_path))
    monkeypatch.setenv("HPT_DUCKDB_TEMP_DIRECTORY", str(duckdb_temp_directory))

    hospitals_seed = get_default_hospitals_seed_path(PROJECT_ROOT)
    original_seed = hospitals_seed.read_text(encoding="utf-8")
    snapshot_ids = ",".join(fixtures.FIXTURE_SNAPSHOT_IDS)
    hospital_ids = ",".join(fixtures.FIXTURE_HOSPITAL_IDS)

    try:
        assert (
            export_hospitals_seed_logic(
                registry_path=FIXTURE_ROOT / "registry.yml",
                output_path=hospitals_seed,
            )
            == 0
        )
        assert (
            ingest_logic(
                hospital_ids=hospital_ids,
                registry_path=FIXTURE_ROOT / "registry.yml",
                log_level="WARNING",
            )
            == 0
        )

        assert _bronze_counts(bronze_root) == EXPECTED_BRONZE_COUNTS

        assert (
            run_dbt_logic(
                snapshot_ids=snapshot_ids,
                command="build",
                selector="validation",
                seeds=True,
                log_level="WARNING",
            )
            == 0
        )
        assert (
            run_dbt_logic(
                snapshot_ids=snapshot_ids,
                command="build",
                selector="silver",
                seeds=True,
                log_level="WARNING",
            )
            == 0
        )

        with duckdb.connect(
            str(duckdb_path), config={"temp_directory": str(duckdb_temp_directory)}
        ) as con:
            assert _table_counts(con, EXPECTED_SILVER_COUNTS) == EXPECTED_SILVER_COUNTS
            assert (
                con.execute(
                    """
                select count(*)
                from main.slv_base__payer_rates pr
                left join main.slv_base__standard_charges sc
                    on pr.silver_standard_charge_id = sc.silver_standard_charge_id
                where sc.silver_standard_charge_id is null
                """
                ).fetchone()[0]
                == 0
            )
            assert (
                con.execute(
                    """
                select count(*)
                from main.slv_base__standard_charges sc
                left join main.slv_base__charge_items ci
                    on sc.silver_charge_item_id = ci.silver_charge_item_id
                where ci.silver_charge_item_id is null
                """
                ).fetchone()[0]
                == 0
            )
    finally:
        hospitals_seed.write_text(original_seed, encoding="utf-8")


def _load_fixture_builder() -> ModuleType:
    spec = importlib.util.spec_from_file_location("build_e2e_fixtures", FIXTURE_BUILDER)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not import fixture builder: {FIXTURE_BUILDER}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _write_reference_fixture(reference_root: Path) -> None:
    """Write the smallest offline MS-DRG reference table dbt can stage."""
    output_dir = reference_root / "ms_drg" / "release_date=2024-10-01"
    output_dir.mkdir(parents=True)
    table = pa.table(
        {
            "code_type": ["ms-drg"],
            "code": ["470"],
            "description": ["Major hip and knee joint replacement"],
            "code_edition": ["FY2025"],
            "effective_start": [date(2024, 10, 1)],
            "effective_end": [date(2025, 9, 30)],
            "source": ["CMS"],
            "license": ["public-domain"],
            "source_url": [
                "https://www.cms.gov/medicare/payment/prospective-payment-systems/acute-inpatient-pps/fy-2025-ipps-final-rule-home-page"
            ],
            "retrieved_at": [datetime(2025, 1, 1, tzinfo=UTC)],
            "mdc": ["08"],
            "drg_type": ["SURG"],
            "relative_weight": [1.9107],
            "relative_weight_uncapped": [1.9107],
            "geometric_mean_los": [1.8],
            "arithmetic_mean_los": [2.3],
            "post_acute_drg": [True],
            "special_pay_drg": [False],
        }
    )
    pq.write_table(table, output_dir / "part-000.parquet")


def _bronze_counts(bronze_root: Path) -> dict[str, int]:
    with duckdb.connect() as con:
        return {
            table_name: con.execute(
                """
                select count(*)
                from read_parquet(?, hive_partitioning=true, union_by_name=true)
                """,
                [str(bronze_root / table_name / "**" / "*.parquet")],
            ).fetchone()[0]
            for table_name in EXPECTED_BRONZE_COUNTS
        }


def _table_counts(con: duckdb.DuckDBPyConnection, expected: dict[str, int]) -> dict[str, int]:
    return {
        table_name: con.execute(f"select count(*) from {table_name}").fetchone()[0]
        for table_name in expected
    }
