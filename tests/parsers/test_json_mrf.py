"""Tests for hpt.parsers.json_mrf — JsonMrfParser and helper functions."""

from __future__ import annotations

import gzip
import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import polars as pl
import pytest

from hpt.parsers.json_mrf import (
    BATCH_SIZE,
    JsonMrfParser,
    _df,
    _iso,
    _to_float,
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
    location_names: list[str] | None = None,
    hospital_address: list[str] | None = None,
    type_2_npi: list[str] | None = None,
    modifier_information: list[dict[str, Any]] | None = None,
    standard_charge_information: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "hospital_name": hospital_name,
        "last_updated_on": "2025-01-01",
        "version": "3.0.0",
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
        "standard_charge_information": [_VALID_SCI] if standard_charge_information is None else standard_charge_information,
    }


def _write_mrf(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data))


def _write_mrf_with_bom(path: Path, data: dict[str, Any]) -> None:
    path.write_bytes(b"\xef\xbb\xbf" + json.dumps(data).encode("utf-8"))


def _make_parser(quarantine_root: Path) -> JsonMrfParser:
    return JsonMrfParser(
        hospital_config=_HOSPITAL_CONFIG,
        snapshot_meta=_SNAPSHOT_META,
        quarantine_root=quarantine_root,
    )


# ---------------------------------------------------------------------------
# Helper function unit tests
# ---------------------------------------------------------------------------


class TestToFloat:
    def test_decimal(self):
        assert _to_float(Decimal("1.5")) == 1.5

    def test_none(self):
        assert _to_float(None) is None

    def test_int(self):
        result = _to_float(42)
        assert result == 42.0
        assert isinstance(result, float)

    def test_float_passthrough(self):
        assert _to_float(3.14) == 3.14


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
        assert drug_df["unit"][0] == 10.0
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
        assert payer_df["standard_charge_dollar"][0] == 150.0

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
