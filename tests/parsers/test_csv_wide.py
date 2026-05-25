"""Tests for hpt.parsers.csv_wide."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from hpt.parsers.csv_wide import CsvWideParser

_SNAPSHOT_META = {
    "snapshot_id": "snap-001",
    "hospital_id": "test-hosp",
    "source_url": "https://example.com/mrf.csv",
    "source_file_name": "mrf.csv",
    "source_format": "csv_wide",
    "file_hash": "abc123",
    "ingested_at": datetime(2025, 1, 1, tzinfo=UTC),
    "is_current_snapshot": True,
    "valid_from": datetime(2025, 1, 1, tzinfo=UTC),
    "valid_to": None,
    "schema_version": "3.0.0",
}

_HOSPITAL_CONFIG = {"hospital_id": "test-hosp"}
_ATTESTATION_TEXT = "To the best of its knowledge and belief this file is complete."


def _write_csv(path: Path, lines: list[str]) -> None:
    path.write_text("\n".join(lines), encoding="utf-8")


def _make_parser(tmp_path: Path) -> CsvWideParser:
    return CsvWideParser(
        hospital_config=_HOSPITAL_CONFIG,
        snapshot_meta=_SNAPSHOT_META,
        quarantine_root=tmp_path / "quarantine",
    )


def test_csv_wide_parse_unpivots_payer_columns(tmp_path):
    path = tmp_path / "wide.csv"
    _write_csv(
        path,
        [
            (
                "hospital_name,last_updated_on,version,location_name,hospital_address,"
                f"license_number|TN,type_2_npi,{_ATTESTATION_TEXT},attester_name"
            ),
            (
                "General Hospital,2025-01-01,3.0.0,Main Campus,123 Main St,"
                "12345,1234567890,true,Jane Smith"
            ),
            (
                "description,code|1,code|1|type,setting,standard_charge|gross,"
                "standard_charge|Aetna|PPO|negotiated_dollar,"
                "standard_charge|Aetna|PPO|methodology,"
                "standard_charge|Cigna|HMO|negotiated_dollar,"
                "additional_payer_notes|Cigna|HMO"
            ),
            "X-Ray,99213,CPT,outpatient,200,150,fee schedule,125,Manual contract",
        ],
    )

    parser = _make_parser(tmp_path)
    batches = list(parser.parse(path))
    charge_df = batches[1]["csv_charge_rows"].sort("payer_name")

    assert len(charge_df) == 2
    assert charge_df["row_ordinal"][0] == 0
    assert charge_df["row_ordinal"][1] == 0
    assert charge_df["payer_name"][0] == "Aetna"
    assert charge_df["payer_name"][1] == "Cigna"
    assert charge_df["plan_name"][0] == "PPO"
    assert charge_df["plan_name"][1] == "HMO"
    assert charge_df["standard_charge_negotiated_dollar"][0] == 150.0
    assert charge_df["standard_charge_negotiated_dollar"][1] == 125.0
    assert charge_df["methodology"][0] == "fee schedule"
    assert charge_df["additional_payer_notes"][1] == "Manual contract"
    assert charge_df["source_format"][0] == "csv_wide"
