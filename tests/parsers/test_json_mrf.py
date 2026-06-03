"""Tests for hpt.parsers.json_mrf — JsonMrfParser and helper functions."""

from __future__ import annotations

import gzip
import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import polars as pl

from hpt.parsers.json_mrf import (
    BATCH_SIZE,
    JsonMrfParser,
    _df,
    _infer_record_schema_family,
    _iso,
    _to_text,
)
from hpt.parsers.schemas import BRONZE_SCHEMAS

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

_SNAPSHOT_META = {
    "snapshot_id": "snap-001",
    "hospital_id": "test-hosp",
    "source_url": "https://example.com/mrf.json",
    "source_file_name": "mrf.json",
    "source_format": "json",
    "file_hash": "abc123",
    "ingested_at": datetime(2025, 1, 1, tzinfo=UTC),
    "is_current_snapshot": True,
    "valid_from": datetime(2025, 1, 1, tzinfo=UTC),
    "valid_to": None,
    "schema_version": "3.0.0",
}

_HOSPITAL_CONFIG = {"hospital_id": "test-hosp"}

_VALID_PAYER = {
    "payer_name": "Aetna",
    "plan_name": "PPO",
    "methodology": "fee schedule",
    "standard_charge_dollar": 150.0,
}

_VALID_CHARGE = {
    "setting": "outpatient",
    "gross_charge": 200.0,
    "payers_information": [_VALID_PAYER],
    "minimum": 100.0,
    "maximum": 300.0,
}

_VALID_CODE = {"code": "CPT001", "type": "CPT"}

_VALID_SCI = {
    "description": "Chest X-Ray",
    "code_information": [_VALID_CODE],
    "standard_charges": [_VALID_CHARGE],
}

_VALID_MODIFIER = {
    "code": "26",
    "description": "Professional Component",
    "modifier_payer_information": [
        {"payer_name": "Aetna", "plan_name": "PPO", "description": "Modifier desc"}
    ],
    "setting": "outpatient",
}


def _minimal_mrf(
    *,
    hospital_name: str = "Test Hospital",
    version: str = "3.0.0",
    location_names: list[str] | None = None,
    hospital_address: list[str] | None = None,
    type_2_npi: list[str] | None = None,
    modifier_information: list[dict[str, Any]] | None = None,
    standard_charge_information: list[dict[str, Any]] | None = None,
    general_contract_provisions: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    mrf: dict[str, Any] = {
        "hospital_name": hospital_name,
        "last_updated_on": "2025-01-01",
        "version": version,
        "license_information": {"state": "FL", "license_number": "FL123"},
        "attestation": {
            "attestation": "I attest",
            "confirm_attestation": True,
            "attester_name": "Jane Doe",
        },
        "location_name": ["Main Campus"] if location_names is None else location_names,
        "hospital_address": ["123 Main St"] if hospital_address is None else hospital_address,
        "type_2_npi": [] if type_2_npi is None else type_2_npi,
        "modifier_information": [] if modifier_information is None else modifier_information,
        "standard_charge_information": (
            [_VALID_SCI]
            if standard_charge_information is None
            else standard_charge_information
        ),
    }
    # Mirror CMS physical layout: this root array appears after the charge array.
    if general_contract_provisions is not None:
        mrf["general_contract_provisions"] = general_contract_provisions
    return mrf


def _write_mrf(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data))


def _write_mrf_with_bom(path: Path, data: dict[str, Any]) -> None:
    path.write_bytes(b"\xef\xbb\xbf" + json.dumps(data).encode("utf-8"))


def _make_parser(
    quarantine_root: Path,
    snapshot_meta: dict[str, Any] | None = None,
) -> JsonMrfParser:
    return JsonMrfParser(
        hospital_config=_HOSPITAL_CONFIG,
        snapshot_meta=_SNAPSHOT_META if snapshot_meta is None else snapshot_meta,
        quarantine_root=quarantine_root,
    )


def _collect_table(
    batches: list[dict[str, pl.DataFrame]],
    table_name: str,
) -> pl.DataFrame:
    frames = [
        batch[table_name]
        for batch in batches
        if table_name in batch and not batch[table_name].is_empty()
    ]
    if not frames:
        return _df([], BRONZE_SCHEMAS[table_name])
    return pl.concat(frames, how="diagonal")


# ---------------------------------------------------------------------------
# Helper function unit tests
# ---------------------------------------------------------------------------


class TestToText:
    def test_decimal_preserves_plain_string(self):
        result = _to_text(Decimal("1.50"))
        assert result == "1.50"
        assert isinstance(result, str)

    def test_decimal_no_float_roundtrip(self):
        # A value that would lose precision via float keeps its exact digits.
        assert _to_text(Decimal("0.1")) == "0.1"

    def test_none(self):
        assert _to_text(None) is None

    def test_int(self):
        result = _to_text(42)
        assert result == "42"
        assert isinstance(result, str)

    def test_float(self):
        result = _to_text(3.14)
        assert result == "3.14"
        assert isinstance(result, str)


class TestIso:
    def test_with_datetime(self):
        dt = datetime(2025, 6, 1, 12, 0, 0, tzinfo=UTC)
        result = _iso(dt)
        assert result == dt.isoformat()

    def test_with_string(self):
        assert _iso("2025-01-01") == "2025-01-01"

    def test_with_none(self):
        assert _iso(None) is None


class TestDf:
    def test_empty_rows_returns_schema_only(self):
        schema = BRONZE_SCHEMAS["hospital_mrf_snapshots"]
        result = _df([], schema)
        assert result.is_empty()
        assert set(result.columns) == set(schema.keys())

    def test_rows_populated(self):
        schema = BRONZE_SCHEMAS["type2_npi"]
        rows = [{"snapshot_id": "s1", "npi": "1234567890", "npi_ordinal": 0}]
        result = _df(rows, schema)
        assert len(result) == 1
        assert result["npi"][0] == "1234567890"


# ---------------------------------------------------------------------------
# Header parsing
# ---------------------------------------------------------------------------


class TestHeaderBatch:
    def test_has_three_tables(self, tmp_path):
        mrf_path = tmp_path / "mrf.json"
        _write_mrf(mrf_path, _minimal_mrf())
        parser = _make_parser(tmp_path / "quarantine")

        batches = list(parser.parse(mrf_path))
        first = batches[0]

        assert "hospital_mrf_snapshots" in first
        assert "hospital_locations" in first
        assert "type2_npi" in first

    def test_parse_accepts_utf8_bom(self, tmp_path):
        mrf_path = tmp_path / "mrf.json"
        _write_mrf_with_bom(mrf_path, _minimal_mrf())
        parser = _make_parser(tmp_path / "quarantine")

        batches = list(parser.parse(mrf_path))

        assert batches[0]["hospital_mrf_snapshots"]["snapshot_id"][0] == "snap-001"
        assert len(batches[2]["standard_charge_info"]) == 1

    def test_snapshot_record_merges_meta_and_source(self, tmp_path):
        mrf_path = tmp_path / "mrf.json"
        _write_mrf(mrf_path, _minimal_mrf(hospital_name="City General"))
        parser = _make_parser(tmp_path / "quarantine")

        first = next(iter(parser.parse(mrf_path)))
        snap_df = first["hospital_mrf_snapshots"]

        assert snap_df["snapshot_id"][0] == "snap-001"
        assert snap_df["hospital_id"][0] == "test-hosp"
        assert snap_df["reported_hospital_name"][0] == "City General"
        assert snap_df["reported_state"][0] == "FL"
        assert snap_df["is_current_snapshot"][0] is True

    def test_v2_header_fields_populate_affirmation_and_locations(self, tmp_path):
        mrf_path = tmp_path / "mrf.json"
        snapshot_meta = {**_SNAPSHOT_META, "schema_version": "2.2.0"}
        v2_mrf = {
            "hospital_name": "Legacy Hospital",
            "last_updated_on": "2025-01-01",
            "version": "2.2.0",
            "license_information": {"state": "MI", "license_number": "MI123"},
            "affirmation": {
                "affirmation": "I affirm",
                "confirm_affirmation": True,
            },
            "hospital_location": ["Legacy Campus"],
            "hospital_address": ["100 Legacy Way"],
            "standard_charge_information": [_VALID_SCI],
        }
        _write_mrf(mrf_path, v2_mrf)
        parser = _make_parser(tmp_path / "quarantine", snapshot_meta=snapshot_meta)

        batches = list(parser.parse(mrf_path))
        snap_df = batches[0]["hospital_mrf_snapshots"]
        location_df = batches[0]["hospital_locations"]
        npi_df = batches[0]["type2_npi"]

        assert snap_df["schema_version"][0] == "2.2.0"
        assert snap_df["affirmation"][0] == "I affirm"
        assert snap_df["confirm_affirmation"][0] == "true"
        assert snap_df["attestation"][0] is None
        assert location_df["location_name"][0] == "Legacy Campus"
        assert npi_df.is_empty()

    def test_location_rows_aligned(self, tmp_path):
        mrf_path = tmp_path / "mrf.json"
        _write_mrf(
            mrf_path,
            _minimal_mrf(
                location_names=["Main", "North"],
                hospital_address=["100 A St", "200 B St"],
            ),
        )
        parser = _make_parser(tmp_path / "quarantine")

        first = next(iter(parser.parse(mrf_path)))
        loc_df = first["hospital_locations"]

        assert len(loc_df) == 2
        assert loc_df["location_name"][0] == "Main"
        assert loc_df["hospital_address"][0] == "100 A St"
        assert loc_df["location_name"][1] == "North"
        assert loc_df["hospital_address"][1] == "200 B St"

    def test_location_rows_names_only(self, tmp_path):
        mrf_path = tmp_path / "mrf.json"
        _write_mrf(
            mrf_path,
            _minimal_mrf(location_names=["Main"], hospital_address=[]),
        )
        parser = _make_parser(tmp_path / "quarantine")

        first = next(iter(parser.parse(mrf_path)))
        loc_df = first["hospital_locations"]

        assert len(loc_df) == 1
        assert loc_df["location_name"][0] == "Main"
        assert loc_df["hospital_address"][0] is None

    def test_location_rows_mismatched_lengths(self, tmp_path):
        mrf_path = tmp_path / "mrf.json"
        _write_mrf(
            mrf_path,
            _minimal_mrf(
                location_names=["A", "B", "C"],
                hospital_address=["1st St"],
            ),
        )
        parser = _make_parser(tmp_path / "quarantine")

        first = next(iter(parser.parse(mrf_path)))
        loc_df = first["hospital_locations"]

        assert len(loc_df) == 3
        assert loc_df["hospital_address"][0] == "1st St"
        assert loc_df["hospital_address"][1] is None
        assert loc_df["hospital_address"][2] is None

    def test_npi_rows_ordinals(self, tmp_path):
        mrf_path = tmp_path / "mrf.json"
        _write_mrf(
            mrf_path,
            _minimal_mrf(type_2_npi=["1234567890", "0987654321"]),
        )
        parser = _make_parser(tmp_path / "quarantine")

        first = next(iter(parser.parse(mrf_path)))
        npi_df = first["type2_npi"]

        assert len(npi_df) == 2
        assert npi_df["npi"][0] == "1234567890"
        assert npi_df["npi_ordinal"][0] == 0
        assert npi_df["npi"][1] == "0987654321"
        assert npi_df["npi_ordinal"][1] == 1


# ---------------------------------------------------------------------------
# Modifier parsing
# ---------------------------------------------------------------------------


class TestModifierParsing:
    def test_parse_modifiers_empty(self, tmp_path):
        mrf_path = tmp_path / "mrf.json"
        _write_mrf(mrf_path, _minimal_mrf(modifier_information=[]))
        parser = _make_parser(tmp_path / "quarantine")

        batches = list(parser.parse(mrf_path))
        modifier_batch = batches[1]  # second batch is always the modifier batch

        assert modifier_batch["modifiers"].is_empty()
        assert modifier_batch["modifier_payer_info"].is_empty()

    def test_parse_modifiers_single(self, tmp_path):
        mrf_path = tmp_path / "mrf.json"
        _write_mrf(mrf_path, _minimal_mrf(modifier_information=[_VALID_MODIFIER]))
        parser = _make_parser(tmp_path / "quarantine")

        batches = list(parser.parse(mrf_path))
        modifier_batch = batches[1]

        mods_df = modifier_batch["modifiers"]
        payer_df = modifier_batch["modifier_payer_info"]

        assert len(mods_df) == 1
        assert mods_df["code"][0] == "26"
        assert mods_df["setting"][0] == "outpatient"

        assert len(payer_df) == 1
        assert payer_df["payer_name"][0] == "Aetna"
        assert payer_df["plan_name"][0] == "PPO"

    def test_parse_modifiers_uses_modifier_information_root(self, tmp_path):
        mrf_path = tmp_path / "mrf.json"
        mrf = _minimal_mrf(modifier_information=[_VALID_MODIFIER])
        mrf["standard_charge_modifiers"] = [
            {
                "code": "WRONG",
                "description": "Not a CMS root source for modifier definitions",
                "modifier_payer_information": [],
            }
        ]
        _write_mrf(mrf_path, mrf)
        parser = _make_parser(tmp_path / "quarantine")

        batches = list(parser.parse(mrf_path))
        modifier_batch = batches[1]

        mods_df = modifier_batch["modifiers"]
        assert len(mods_df) == 1
        assert mods_df["code"].to_list() == ["26"]

    def test_parse_modifiers_invalid_quarantined(self, tmp_path):
        quarantine_root = tmp_path / "quarantine"
        mrf_path = tmp_path / "mrf.json"
        bad_modifier = {"code": "26"}  # missing required fields
        good_modifier = _VALID_MODIFIER
        _write_mrf(
            mrf_path,
            _minimal_mrf(modifier_information=[bad_modifier, good_modifier]),
        )
        parser = _make_parser(quarantine_root)
        list(parser.parse(mrf_path))

        q_file = quarantine_root / "snapshot_id=snap-001" / "modifier_information.jsonl"
        assert q_file.exists()
        lines = q_file.read_text().splitlines()
        assert len(lines) == 1

        record = json.loads(lines[0])
        assert record["section"] == "modifier_information"
        assert record["ordinal"] == 0
        assert "error" in record
        assert "raw" in record


# ---------------------------------------------------------------------------
# General contract provisions parsing
# ---------------------------------------------------------------------------


class TestGeneralContractProvisionsParsing:
    def test_absent_emits_no_rows(self, tmp_path):
        mrf_path = tmp_path / "mrf.json"
        _write_mrf(mrf_path, _minimal_mrf())
        parser = _make_parser(tmp_path / "quarantine")

        batches = list(parser.parse(mrf_path))
        df = _collect_table(batches, "general_contract_provisions")
        assert df.is_empty()

    def test_emitted_after_charge_array(self, tmp_path):
        mrf_path = tmp_path / "mrf.json"
        provisions = [
            {
                "payer_name": "Platform Health",
                "plan_name": "PPO",
                "provisions": "Stop-loss over $200k reimburses at 50% of charges.",
            },
            {
                "payer_name": "Region Health",
                "plan_name": "HMO",
                "provisions": "Outlier provision applies at the claim level.",
            },
        ]
        _write_mrf(
            mrf_path,
            _minimal_mrf(general_contract_provisions=provisions),
        )
        parser = _make_parser(tmp_path / "quarantine")

        batches = list(parser.parse(mrf_path))
        df = _collect_table(batches, "general_contract_provisions")

        assert len(df) == 2
        assert df["provision_ordinal"].to_list() == [0, 1]
        assert df["payer_name"].to_list() == ["Platform Health", "Region Health"]
        assert df["plan_name"].to_list() == ["PPO", "HMO"]
        assert df["provisions"][0].startswith("Stop-loss")
        # Lineage preserved.
        assert df["snapshot_id"].to_list() == ["snap-001", "snap-001"]

    def test_missing_provisions_field_still_emits_row(self, tmp_path):
        # Source-faithful: a provisions-less object is NOT quarantined; the dbt
        # validation layer flags general_contract_provisions_required_shape.
        mrf_path = tmp_path / "mrf.json"
        provisions = [{"payer_name": "Platform Health", "plan_name": "PPO"}]
        _write_mrf(
            mrf_path,
            _minimal_mrf(general_contract_provisions=provisions),
        )
        parser = _make_parser(tmp_path / "quarantine")

        batches = list(parser.parse(mrf_path))
        df = _collect_table(batches, "general_contract_provisions")

        assert len(df) == 1
        assert df["provisions"][0] is None
        assert df["payer_name"][0] == "Platform Health"
        # No quarantine file is written for the optional provisions pass.
        q_file = (
            tmp_path
            / "quarantine"
            / "snapshot_id=snap-001"
            / "general_contract_provisions.jsonl"
        )
        assert not q_file.exists()

    def test_payerless_provision_emits_row(self, tmp_path):
        mrf_path = tmp_path / "mrf.json"
        provisions = [{"provisions": "Aggregate carve-out applies."}]
        _write_mrf(
            mrf_path,
            _minimal_mrf(general_contract_provisions=provisions),
        )
        parser = _make_parser(tmp_path / "quarantine")

        batches = list(parser.parse(mrf_path))
        df = _collect_table(batches, "general_contract_provisions")

        assert len(df) == 1
        assert df["payer_name"][0] is None
        assert df["plan_name"][0] is None
        assert df["provisions"][0] == "Aggregate carve-out applies."


# ---------------------------------------------------------------------------
# Charge parsing
# ---------------------------------------------------------------------------


class TestChargeParsing:
    def test_parse_charges_basic(self, tmp_path):
        mrf_path = tmp_path / "mrf.json"
        _write_mrf(mrf_path, _minimal_mrf(standard_charge_information=[_VALID_SCI]))
        parser = _make_parser(tmp_path / "quarantine")

        batches = list(parser.parse(mrf_path))
        charge_batch = batches[2]  # first charge batch

        assert not charge_batch["standard_charge_info"].is_empty()
        assert not charge_batch["code_information"].is_empty()
        assert not charge_batch["standard_charges"].is_empty()
        assert not charge_batch["payers_information"].is_empty()

    def test_flatten_sci_no_drug_information(self, tmp_path):
        mrf_path = tmp_path / "mrf.json"
        sci_no_drug = {**_VALID_SCI, "drug_information": None}
        _write_mrf(mrf_path, _minimal_mrf(standard_charge_information=[sci_no_drug]))
        parser = _make_parser(tmp_path / "quarantine")

        batches = list(parser.parse(mrf_path))
        charge_batch = batches[2]

        assert charge_batch["drug_information"].is_empty()

    def test_flatten_sci_with_drug_information(self, tmp_path):
        mrf_path = tmp_path / "mrf.json"
        sci_with_drug = {
            "description": "Drug Item",
            "code_information": [{"code": "NDC001", "type": "NDC"}],
            "drug_information": {"unit": 10.0, "type": "ML"},
            "standard_charges": [_VALID_CHARGE],
        }
        _write_mrf(
            mrf_path, _minimal_mrf(standard_charge_information=[sci_with_drug])
        )
        parser = _make_parser(tmp_path / "quarantine")

        batches = list(parser.parse(mrf_path))
        charge_batch = batches[2]

        drug_df = charge_batch["drug_information"]
        assert len(drug_df) == 1
        # Bronze preserves the numeric source value as text; dbt staging casts it.
        assert drug_df["unit"][0] == "10.0"
        assert drug_df["unit"].dtype == pl.Utf8
        assert drug_df["type"][0] == "ML"

    def test_flatten_sci_modifier_codes(self, tmp_path):
        mrf_path = tmp_path / "mrf.json"
        charge_with_mods = {
            **_VALID_CHARGE,
            "modifier_code": ["26", "TC"],
        }
        sci = {**_VALID_SCI, "standard_charges": [charge_with_mods]}
        _write_mrf(mrf_path, _minimal_mrf(standard_charge_information=[sci]))
        parser = _make_parser(tmp_path / "quarantine")

        batches = list(parser.parse(mrf_path))
        charge_batch = batches[2]

        mod_df = charge_batch["standard_charge_modifiers"]
        assert len(mod_df) == 2
        assert mod_df["modifier_code"][0] == "26"
        assert mod_df["modifier_ordinal"][0] == 0
        assert mod_df["modifier_code"][1] == "TC"
        assert mod_df["modifier_ordinal"][1] == 1

    def test_flatten_sci_payers_information(self, tmp_path):
        mrf_path = tmp_path / "mrf.json"
        _write_mrf(mrf_path, _minimal_mrf(standard_charge_information=[_VALID_SCI]))
        parser = _make_parser(tmp_path / "quarantine")

        batches = list(parser.parse(mrf_path))
        charge_batch = batches[2]

        payer_df = charge_batch["payers_information"]
        assert len(payer_df) == 1
        assert payer_df["payer_name"][0] == "Aetna"
        assert payer_df["plan_name"][0] == "PPO"
        assert payer_df["methodology"][0] == "fee schedule"
        # Bronze preserves the numeric source value as text; dbt staging casts it.
        assert payer_df["standard_charge_dollar"][0] == "150.0"
        assert payer_df["standard_charge_dollar"].dtype == pl.Utf8

    def test_numeric_values_preserved_as_text(self, tmp_path):
        """Accepted numeric fields land in Bronze as strings regardless of the
        JSON source representation (string-quoted, integer, or fractional)."""
        mrf_path = tmp_path / "mrf.json"
        payer = {
            "payer_name": "Aetna",
            "plan_name": "PPO",
            "methodology": "fee schedule",
            # String-quoted numeric in source preserves its exact digits.
            "standard_charge_dollar": "150.00",
        }
        sci = {
            "description": "Chest X-Ray",
            "code_information": [_VALID_CODE],
            "standard_charges": [
                {
                    "setting": "outpatient",
                    # Integer source value preserved without a trailing ".0".
                    "gross_charge": 200,
                    "minimum": "100.5",
                    "maximum": 300,
                    "payers_information": [payer],
                }
            ],
        }
        _write_mrf(mrf_path, _minimal_mrf(standard_charge_information=[sci]))
        parser = _make_parser(tmp_path / "quarantine")

        batches = list(parser.parse(mrf_path))
        charges_df = _collect_table(batches[2:], "standard_charges")
        payer_df = _collect_table(batches[2:], "payers_information")

        assert charges_df["gross_charge"].dtype == pl.Utf8
        assert charges_df["gross_charge"][0] == "200"
        assert charges_df["minimum"][0] == "100.5"
        assert charges_df["maximum"][0] == "300"
        assert payer_df["standard_charge_dollar"].dtype == pl.Utf8
        assert payer_df["standard_charge_dollar"][0] == "150.00"

    def test_v2_2_algorithm_estimated_amount_ingests_without_mismatch(self, tmp_path):
        quarantine_root = tmp_path / "quarantine"
        mrf_path = tmp_path / "mrf.json"
        snapshot_meta = {**_SNAPSHOT_META, "schema_version": "2.2.0"}
        payer = {
            "payer_name": "Blue Cross",
            "plan_name": "PPO",
            "methodology": "other",
            "standard_charge_algorithm": "contract algorithm",
            "estimated_amount": 33.51,
            "additional_payer_notes": "algorithm available in contract",
        }
        sci = {
            "description": "Algorithm item",
            "code_information": [{"code": "10060", "type": "HCPCS"}],
            "standard_charges": [
                {
                    "setting": "both",
                    "minimum": 33.51,
                    "maximum": 33.51,
                    "payers_information": [payer],
                }
            ],
        }
        _write_mrf(
            mrf_path,
            _minimal_mrf(version="2.2.0", standard_charge_information=[sci]),
        )
        parser = _make_parser(quarantine_root, snapshot_meta=snapshot_meta)

        batches = list(parser.parse(mrf_path))
        charge_df = _collect_table(batches[2:], "standard_charge_info")
        payer_df = _collect_table(batches[2:], "payers_information")
        diagnostic_df = _collect_table(batches[2:], "json_record_parse_diagnostics")

        assert charge_df["reported_schema_family"][0] == "2.2"
        assert charge_df["parser_schema_family"][0] == "2.2"
        assert charge_df["schema_version_mismatch"][0] is False
        assert payer_df["estimated_amount"][0] == "33.51"
        assert diagnostic_df.is_empty()
        assert not (quarantine_root / "snapshot_id=snap-001").exists()

    def test_v3_reported_v2_2_shape_infers_record_family_and_flags_mismatch(
        self, tmp_path
    ):
        quarantine_root = tmp_path / "quarantine"
        mrf_path = tmp_path / "mrf.json"
        payer = {
            "payer_name": "Blue Cross",
            "plan_name": "PPO",
            "methodology": "other",
            "standard_charge_algorithm": "contract algorithm",
            "estimated_amount": 33.51,
            "additional_payer_notes": "algorithm available in contract",
        }
        sci = {
            "description": "Algorithm item",
            "code_information": [{"code": "10060", "type": "HCPCS"}],
            "standard_charges": [
                {
                    "setting": "both",
                    "minimum": 33.51,
                    "maximum": 33.51,
                    "payers_information": [payer],
                }
            ],
        }
        _write_mrf(mrf_path, _minimal_mrf(standard_charge_information=[sci]))
        parser = _make_parser(quarantine_root)

        batches = list(parser.parse(mrf_path))
        charge_df = _collect_table(batches[2:], "standard_charge_info")
        diagnostic_df = _collect_table(batches[2:], "json_record_parse_diagnostics")

        assert charge_df["reported_schema_family"][0] == "3.0"
        assert charge_df["parser_schema_family"][0] == "2.2"
        assert charge_df["schema_version_mismatch"][0] is True
        assert diagnostic_df.is_empty()
        assert not (quarantine_root / "snapshot_id=snap-001").exists()

    def test_value_level_violations_land_in_bronze_not_quarantine(self, tmp_path):
        quarantine_root = tmp_path / "quarantine"
        mrf_path = tmp_path / "mrf.json"
        payer = {
            "payer_name": "Blue Cross",
            "plan_name": "PPO",
            "methodology": "not a CMS methodology",
            "standard_charge_dollar": "not numeric",
            # Missing minimum/maximum is a dbt validation concern now.
        }
        sci = {
            "description": "Malformed but structural item",
            "code_information": [{"code": "10060", "type": "NOT_A_CODE_TYPE"}],
            "standard_charges": [
                {
                    "setting": "bad setting",
                    "gross_charge": -25,
                    "payers_information": [payer],
                }
            ],
        }
        _write_mrf(mrf_path, _minimal_mrf(standard_charge_information=[sci]))
        parser = _make_parser(quarantine_root)

        batches = list(parser.parse(mrf_path))
        code_df = _collect_table(batches[2:], "code_information")
        charges_df = _collect_table(batches[2:], "standard_charges")
        payer_df = _collect_table(batches[2:], "payers_information")
        diagnostic_df = _collect_table(batches[2:], "json_record_parse_diagnostics")

        assert code_df["type"][0] == "NOT_A_CODE_TYPE"
        assert charges_df["setting"][0] == "bad setting"
        assert charges_df["gross_charge"][0] == "-25"
        assert charges_df["minimum"][0] is None
        assert charges_df["maximum"][0] is None
        assert payer_df["methodology"][0] == "not a CMS methodology"
        assert payer_df["standard_charge_dollar"][0] == "not numeric"
        assert diagnostic_df.is_empty()
        assert not (quarantine_root / "snapshot_id=snap-001").exists()

    def test_invalid_charge_quarantined_valid_still_emitted(self, tmp_path):
        quarantine_root = tmp_path / "quarantine"
        mrf_path = tmp_path / "mrf.json"
        # Missing required fields code_information and standard_charges → ValidationError
        bad_sci = {"description": "Bad"}
        _write_mrf(
            mrf_path,
            _minimal_mrf(standard_charge_information=[bad_sci, _VALID_SCI]),
        )
        parser = _make_parser(quarantine_root)

        batches = list(parser.parse(mrf_path))
        # Valid charge item must appear somewhere in the charge batches
        charge_rows = sum(
            len(b.get("standard_charge_info", pl.DataFrame()))
            for b in batches[2:]
        )
        assert charge_rows >= 1

        q_file = (
            quarantine_root
            / "snapshot_id=snap-001"
            / "standard_charge_information.jsonl"
        )
        assert q_file.exists()

    def test_quarantine_jsonl_structure(self, tmp_path):
        quarantine_root = tmp_path / "quarantine"
        mrf_path = tmp_path / "mrf.json"
        # Missing required fields → ValidationError → quarantine
        bad_sci = {"description": "Bad"}
        _write_mrf(
            mrf_path,
            _minimal_mrf(standard_charge_information=[bad_sci]),
        )
        parser = _make_parser(quarantine_root)
        list(parser.parse(mrf_path))

        q_file = (
            quarantine_root
            / "snapshot_id=snap-001"
            / "standard_charge_information.jsonl"
        )
        record = json.loads(q_file.read_text().splitlines()[0])
        assert "section" in record
        assert "ordinal" in record
        assert "error" in record
        assert "raw" in record

    def test_structural_failures_emit_diagnostics(self, tmp_path):
        quarantine_root = tmp_path / "quarantine"
        mrf_path = tmp_path / "mrf.json"
        bad_sci = {"description": "Bad"}
        _write_mrf(
            mrf_path,
            _minimal_mrf(standard_charge_information=[bad_sci]),
        )
        parser = _make_parser(quarantine_root)

        batches = list(parser.parse(mrf_path))
        diagnostic_df = _collect_table(batches[2:], "json_record_parse_diagnostics")

        assert len(diagnostic_df) == 1
        assert diagnostic_df["section"][0] == "standard_charge_information"
        assert diagnostic_df["record_ordinal"][0] == 0
        assert diagnostic_df["parser_schema_family"][0] == "3.0"
        assert diagnostic_df["failure_count"][0] == 1
        assert "3.0" in json.loads(diagnostic_df["error_summary"][0])


# ---------------------------------------------------------------------------
# _infer_record_schema_family unit tests
# ---------------------------------------------------------------------------


def _sci_with_payers(*payers: dict) -> dict:
    """Build a minimal raw SCI dict with the given payer dicts."""
    return {
        "description": "Test",
        "code_information": [{"code": "CPT001", "type": "CPT"}],
        "standard_charges": [
            {
                "setting": "outpatient",
                "payers_information": list(payers),
            }
        ],
    }


_PAYER_WITH_V2_2_SIGNAL = {
    "payer_name": "Aetna",
    "plan_name": "PPO",
    "methodology": "other",
    "standard_charge_algorithm": "contract rate",
    "estimated_amount": 100.0,
}

_PAYER_WITH_V3_SIGNAL = {
    "payer_name": "BlueCross",
    "plan_name": "HMO",
    "methodology": "other",
    "standard_charge_algorithm": "contract rate",
    "count": 50,
    "median_amount": 120.0,
}

_PAYER_NO_SIGNAL = {
    "payer_name": "United",
    "plan_name": "PPO",
    "methodology": "fee schedule",
    "standard_charge_dollar": 200.0,
}


class TestInferRecordSchemaFamily:
    def test_pure_v2_2_signal_returns_2_2_no_conflict(self):
        raw = _sci_with_payers(_PAYER_WITH_V2_2_SIGNAL)
        family, conflicting = _infer_record_schema_family(raw, default_family="3.0")
        assert family == "2.2"
        assert conflicting is False

    def test_pure_v3_signal_returns_3_0_no_conflict(self):
        raw = _sci_with_payers(_PAYER_WITH_V3_SIGNAL)
        family, conflicting = _infer_record_schema_family(raw, default_family="2.2")
        assert family == "3.0"
        assert conflicting is False

    def test_no_signal_returns_default_family(self):
        # Payer with only fee-schedule fields carries no version discriminator.
        raw = _sci_with_payers(_PAYER_NO_SIGNAL)
        family, conflicting = _infer_record_schema_family(raw, default_family="3.0")
        assert family == "3.0"
        assert conflicting is False

    def test_no_signal_2_1_header_uses_header_fallback(self):
        # V2.1 has no discriminating fields; the header default propagates through.
        raw = _sci_with_payers(_PAYER_NO_SIGNAL)
        family, conflicting = _infer_record_schema_family(raw, default_family="2.1")
        assert family == "2.1"
        assert conflicting is False

    def test_both_signals_resolves_to_3_0_with_conflict_flag(self):
        # One payer emits a V2.2 field, another emits a V3.0 field — internally
        # inconsistent record. V3 wins; conflict flag is set.
        raw = _sci_with_payers(_PAYER_WITH_V2_2_SIGNAL, _PAYER_WITH_V3_SIGNAL)
        family, conflicting = _infer_record_schema_family(raw, default_family="3.0")
        assert family == "3.0"
        assert conflicting is True

    def test_both_signals_single_payer_resolves_to_3_0_with_conflict_flag(self):
        # A single payer with both estimated_amount and count simultaneously.
        payer = {
            **_PAYER_WITH_V2_2_SIGNAL,
            "count": 10,
            "median_amount": 110.0,
        }
        raw = _sci_with_payers(payer)
        family, conflicting = _infer_record_schema_family(raw, default_family="3.0")
        assert family == "3.0"
        assert conflicting is True

    def test_non_dict_item_returns_default_family(self):
        family, conflicting = _infer_record_schema_family("not a dict", default_family="3.0")
        assert family == "3.0"
        assert conflicting is False

    def test_percentile_only_signal_detects_v3(self):
        payer = {
            "payer_name": "Cigna",
            "plan_name": "PPO",
            "methodology": "other",
            "standard_charge_percentage": 80.0,
            "10th_percentile": 90.0,
            "90th_percentile": 150.0,
        }
        raw = _sci_with_payers(payer)
        family, conflicting = _infer_record_schema_family(raw, default_family="2.2")
        assert family == "3.0"
        assert conflicting is False


# ---------------------------------------------------------------------------
# Conflicting-version-signals integration tests
# ---------------------------------------------------------------------------


class TestConflictingVersionSignalsIntegration:
    def test_conflicting_signals_flagged_in_bronze_not_quarantined(self, tmp_path):
        """A record with both V2.2 and V3.0 signals resolves to 3.0 and sets the
        conflicting_version_signals column without being quarantined."""
        quarantine_root = tmp_path / "quarantine"
        mrf_path = tmp_path / "mrf.json"
        conflicting_sci = {
            "description": "Conflicting item",
            "code_information": [{"code": "CPT001", "type": "CPT"}],
            "standard_charges": [
                {
                    "setting": "outpatient",
                    "payers_information": [
                        _PAYER_WITH_V2_2_SIGNAL,
                        _PAYER_WITH_V3_SIGNAL,
                    ],
                }
            ],
        }
        _write_mrf(mrf_path, _minimal_mrf(standard_charge_information=[conflicting_sci]))
        parser = _make_parser(quarantine_root)

        batches = list(parser.parse(mrf_path))
        charge_df = _collect_table(batches[2:], "standard_charge_info")
        diagnostic_df = _collect_table(batches[2:], "json_record_parse_diagnostics")

        assert charge_df["parser_schema_family"][0] == "3.0"
        assert charge_df["conflicting_version_signals"][0] is True
        assert charge_df["schema_version_mismatch"][0] is False
        assert diagnostic_df.is_empty()
        assert not (quarantine_root / "snapshot_id=snap-001").exists()

    def test_non_conflicting_record_has_false_flag(self, tmp_path):
        """A clean V2.2 record reported under a V3 header has schema_version_mismatch
        set but conflicting_version_signals is False."""
        quarantine_root = tmp_path / "quarantine"
        mrf_path = tmp_path / "mrf.json"
        v2_2_sci = {
            "description": "V2.2 item",
            "code_information": [{"code": "CPT001", "type": "CPT"}],
            "standard_charges": [
                {
                    "setting": "outpatient",
                    "payers_information": [_PAYER_WITH_V2_2_SIGNAL],
                }
            ],
        }
        _write_mrf(mrf_path, _minimal_mrf(standard_charge_information=[v2_2_sci]))
        parser = _make_parser(quarantine_root)  # snapshot_meta has version=3.0.0

        batches = list(parser.parse(mrf_path))
        charge_df = _collect_table(batches[2:], "standard_charge_info")

        assert charge_df["parser_schema_family"][0] == "2.2"
        assert charge_df["schema_version_mismatch"][0] is True
        assert charge_df["conflicting_version_signals"][0] is False


# ---------------------------------------------------------------------------
# Batch accumulation
# ---------------------------------------------------------------------------


class TestBatchAccumulation:
    def test_flushes_at_batch_size(self, tmp_path):
        mrf_path = tmp_path / "mrf.json"
        charges = [_VALID_SCI] * (BATCH_SIZE + 1)
        _write_mrf(mrf_path, _minimal_mrf(standard_charge_information=charges))
        parser = _make_parser(tmp_path / "quarantine")

        batches = list(parser.parse(mrf_path))
        # Header + modifier + at least 2 charge batches
        charge_batches = batches[2:]
        assert len(charge_batches) >= 2


# ---------------------------------------------------------------------------
# Gzip support
# ---------------------------------------------------------------------------


class TestGzipSupport:
    def test_parse_gzipped_json(self, tmp_path):
        plain_path = tmp_path / "mrf.json"
        gz_path = tmp_path / "mrf.json.gz"
        data = _minimal_mrf()
        _write_mrf(plain_path, data)
        with gzip.open(gz_path, "wb") as fh:
            fh.write(plain_path.read_bytes())

        quarantine = tmp_path / "quarantine"
        parser_plain = _make_parser(quarantine)
        parser_gz = _make_parser(quarantine)

        plain_batches = list(parser_plain.parse(plain_path))
        gz_batches = list(parser_gz.parse(gz_path))

        snap_plain = plain_batches[0]["hospital_mrf_snapshots"]
        snap_gz = gz_batches[0]["hospital_mrf_snapshots"]
        assert snap_plain["reported_hospital_name"][0] == snap_gz["reported_hospital_name"][0]
        assert len(plain_batches) == len(gz_batches)
