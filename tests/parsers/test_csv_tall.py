"""Tests for hpt.parsers.csv_tall."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import polars as pl

from hpt.parsers.csv_tall import CsvTallParser

_SNAPSHOT_META = {
    "snapshot_id": "snap-001",
    "hospital_id": "test-hosp",
    "source_url": "https://example.com/mrf.csv",
    "source_file_name": "mrf.csv",
    "source_format": "csv_tall",
    "file_hash": "abc123",
    "ingested_at": datetime(2025, 1, 1, tzinfo=UTC),
    "valid_from": datetime(2025, 1, 1, tzinfo=UTC),
    "schema_version": "3.0.0",
}

_HOSPITAL_CONFIG = {"hospital_id": "test-hosp"}
_ATTESTATION_TEXT = "To the best of its knowledge and belief this file is complete."


def _write_csv(path: Path, lines: list[str]) -> None:
    path.write_text("\n".join(lines), encoding="utf-8")


def _make_parser(tmp_path: Path) -> CsvTallParser:
    return CsvTallParser(
        hospital_config=_HOSPITAL_CONFIG,
        snapshot_meta=_SNAPSHOT_META,
        quarantine_root=tmp_path / "quarantine",
    )


def test_csv_tall_parse_emits_header_then_charge_rows(tmp_path):
    path = tmp_path / "tall.csv"
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
                "description,code|1,code|1|type,setting,billing_class,"
                "standard_charge|gross,standard_charge|negotiated_dollar,"
                "payer_name,plan_name,count"
            ),
            "X-Ray,99213,CPT,outpatient,facility,200,150,Aetna,PPO,0",
            "MRI,72148,CPT,inpatient,facility,500,400,Cigna,HMO,11",
        ],
    )

    parser = _make_parser(tmp_path)
    batches = list(parser.parse(path))

    header_batch = batches[0]
    assert header_batch["hospital_mrf_snapshots"]["reported_hospital_name"][0] == "General Hospital"
    assert header_batch["hospital_locations"]["location_name"][0] == "Main Campus"

    charge_df = batches[1]["csv_charge_rows"]
    assert len(charge_df) == 2
    assert charge_df["row_ordinal"][0] == 0
    assert charge_df["row_ordinal"][1] == 1
    assert charge_df["code_1"][0] == "99213"
    assert charge_df["code_1_type"][1] == "CPT"
    assert charge_df["standard_charge_gross"][0] == "200"
    assert charge_df["standard_charge_negotiated_dollar"][1] == "400"
    assert charge_df["standard_charge_gross"].dtype == pl.Utf8
    assert charge_df["source_format"][0] == "csv_tall"


def test_csv_tall_parse_falls_back_to_cp1252(tmp_path):
    path = tmp_path / "tall_cp1252.csv"
    path.write_bytes(
        b"\n".join(
            [
                (
                    b"hospital_name,last_updated_on,version,location_name,"
                    b"hospital_address,license_number|TN,type_2_npi"
                ),
                b"General Hospital,2025-01-01,3.0.0,Main Campus,123 Main St,12345,1234567890",
                (
                    b"description,code|1,code|1|type,setting,billing_class,"
                    b"standard_charge|gross,standard_charge|negotiated_dollar,"
                    b"payer_name,plan_name,count"
                ),
                b"NEEDLE-\xe1,99213,CPT,outpatient,facility,200,150,Aetna,PPO,0",
            ]
        )
    )

    parser = _make_parser(tmp_path)
    batches = list(parser.parse(path))
    charge_df = batches[1]["csv_charge_rows"]

    assert len(charge_df) == 1
    assert charge_df["description"][0].encode("cp1252") == b"NEEDLE-\xe1"
    assert charge_df["payer_name"][0] == "Aetna"


def test_csv_tall_preserves_malformed_numeric_as_raw_text(tmp_path):
    path = tmp_path / "tall_bad_number.csv"
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
                "description,code|1,code|1|type,setting,billing_class,"
                "standard_charge|gross,standard_charge|negotiated_dollar,"
                "payer_name,plan_name,count"
            ),
            "X-Ray,99213,CPT,outpatient,facility,not-a-number,150,Aetna,PPO,0",
        ],
    )

    parser = _make_parser(tmp_path)
    batches = list(parser.parse(path))

    charge_df = batches[1]["csv_charge_rows"]
    # Bronze is source-faithful: malformed numeric cells survive as raw text
    # rather than being coerced to null during parsing.
    assert charge_df["standard_charge_gross"].dtype == pl.Utf8
    assert charge_df["standard_charge_gross"][0] == "not-a-number"
    assert charge_df["standard_charge_negotiated_dollar"][0] == "150"
