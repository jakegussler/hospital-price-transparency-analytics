"""Tests for shared CSV header parsing helpers."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from hpt.parsers.csv_header import (
    build_tall_column_map,
    build_wide_column_catalog,
    discover_code_columns,
    get_charge_reader,
    parse_csv_header,
)

_SNAPSHOT_META = {
    "snapshot_id": "snap-001",
    "hospital_id": "test-hosp",
    "source_url": "https://example.com/mrf.csv",
    "source_file_name": "mrf.csv",
    "source_format": "csv_tall",
    "file_hash": "abc123",
    "ingested_at": datetime(2025, 1, 1, tzinfo=UTC),
    "is_current_snapshot": True,
    "valid_from": datetime(2025, 1, 1, tzinfo=UTC),
    "valid_to": None,
    "schema_version": "3.0.0",
}

_ATTESTATION_TEXT = (
    "To the best of its knowledge and belief, the hospital attests that the"
    " standard charge information includes all applicable standard charge"
    " information as required by 45 CFR 180.50."
)


def _write_csv(path: Path, lines: list[str]) -> None:
    path.write_text("\n".join(lines), encoding="utf-8")


def test_parse_csv_header_extracts_snapshot_fields(tmp_path):
    path = tmp_path / "sample.csv"
    _write_csv(
        path,
        [
            (
                "hospital_name,last_updated_on,version,location_name,hospital_address,"
                f'license_number|TN,type_2_npi,"{_ATTESTATION_TEXT}",attester_name'
            ),
            (
                "General Hospital,2025-01-01,3.0.0,Main Campus|North Campus,"
                "123 Main St|456 North St,12345,1234567890|0987654321,true,Jane Smith"
            ),
            "description,payer_name,plan_name",
            "X-Ray,Aetna,PPO",
        ],
    )

    snapshot_record, locations, npis, provisions = parse_csv_header(
        path, _SNAPSHOT_META
    )
    assert snapshot_record["reported_hospital_name"] == "General Hospital"
    assert snapshot_record["reported_state"] == "TN"
    assert snapshot_record["license_number"] == "12345"
    assert snapshot_record["attestation"] == _ATTESTATION_TEXT
    assert snapshot_record["confirm_attestation"] == "true"
    assert len(locations) == 2
    assert locations[0]["location_name"] == "Main Campus"
    assert locations[1]["hospital_address"] == "456 North St"
    assert len(npis) == 2
    assert npis[1]["npi"] == "0987654321"
    # Optional column absent -> no general contract provision rows.
    assert provisions == []


def test_parse_csv_header_emits_general_contract_provisions(tmp_path):
    path = tmp_path / "sample.csv"
    _write_csv(
        path,
        [
            "hospital_name,last_updated_on,version,general_contract_provisions",
            "General Hospital,2025-01-01,3.0.0,Stop-loss applies over $100k",
            "description,payer_name,plan_name",
            "X-Ray,Aetna,PPO",
        ],
    )

    _, _, _, provisions = parse_csv_header(path, _SNAPSHOT_META)
    assert len(provisions) == 1
    assert provisions[0]["snapshot_id"] == "snap-001"
    assert provisions[0]["provision_ordinal"] == 0
    assert provisions[0]["payer_name"] is None
    assert provisions[0]["plan_name"] is None
    assert provisions[0]["provisions"] == "Stop-loss applies over $100k"


def test_parse_csv_header_blank_provisions_still_emits_row(tmp_path):
    path = tmp_path / "sample.csv"
    _write_csv(
        path,
        [
            "hospital_name,last_updated_on,version,general_contract_provisions",
            "General Hospital,2025-01-01,3.0.0,",
            "description,payer_name,plan_name",
            "X-Ray,Aetna,PPO",
        ],
    )

    _, _, _, provisions = parse_csv_header(path, _SNAPSHOT_META)
    # Present-but-blank column emits a row so dbt can flag the missing value.
    assert len(provisions) == 1
    assert provisions[0]["provisions"] is None


def test_get_charge_reader_positions_at_row_4(tmp_path):
    path = tmp_path / "sample.csv"
    _write_csv(
        path,
        [
            "hospital_name,last_updated_on",
            "General Hospital,2025-01-01",
            "description,payer_name,plan_name",
            "Row1,Aetna,PPO",
            "Row2,Cigna,HMO",
        ],
    )

    reader, headers, handle = get_charge_reader(path)
    try:
        assert headers == ["description", "payer_name", "plan_name"]
        first_row = next(reader)
        assert first_row == ["Row1", "Aetna", "PPO"]
    finally:
        handle.close()


def test_get_charge_reader_falls_back_to_cp1252(tmp_path):
    path = tmp_path / "cp1252.csv"
    path.write_bytes(
        b"\n".join(
            [
                b"hospital_name,last_updated_on",
                b"General Hospital,2025-01-01",
                b"description,payer_name,plan_name",
                b"NEEDLE-\xe1,Aetna,PPO",
            ]
        )
    )

    reader, headers, handle = get_charge_reader(path)
    try:
        assert headers == ["description", "payer_name", "plan_name"]
        first_row = next(reader)
        assert first_row[0].encode("cp1252") == b"NEEDLE-\xe1"
        assert first_row[1:] == ["Aetna", "PPO"]
    finally:
        handle.close()


def test_discover_code_columns_and_tall_map():
    headers = [
        "description",
        "code|1",
        "code|1|type",
        "code|2",
        "code|2|type",
        "standard_charge|gross",
    ]

    max_codes, code_map = discover_code_columns(headers)
    assert max_codes == 2
    assert code_map["code_1"] == 1
    assert code_map["code_2_type"] == 4

    tall_max_codes, tall_map = build_tall_column_map(headers)
    assert tall_max_codes == 2
    assert tall_map["description"] == 0
    assert tall_map["standard_charge_gross"] == 5


def test_build_wide_column_catalog_groups_payer_columns():
    headers = [
        "description",
        "code|1",
        "code|1|type",
        "setting",
        "standard_charge|Aetna|PPO|negotiated_dollar",
        "standard_charge|Aetna|PPO|methodology",
        "standard_charge|Cigna|HMO|negotiated_dollar",
        "additional_payer_notes|Cigna|HMO",
    ]

    max_codes, catalog = build_wide_column_catalog(headers)
    assert max_codes == 1
    assert catalog.fixed_columns["description"] == 0
    assert catalog.fixed_columns["code_1"] == 1
    assert len(catalog.payer_groups) == 2

    groups = {(g.payer_name, g.plan_name): g for g in catalog.payer_groups}
    assert groups[("Aetna", "PPO")].columns["standard_charge_negotiated_dollar"] == 4
    assert groups[("Aetna", "PPO")].columns["methodology"] == 5
    assert groups[("Cigna", "HMO")].columns["standard_charge_negotiated_dollar"] == 6
    assert catalog.additional_payer_notes_cols[("Cigna", "HMO")] == 7

