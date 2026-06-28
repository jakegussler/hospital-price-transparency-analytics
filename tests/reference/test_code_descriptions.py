"""Tests for the MS-DRG reference parser and loader output."""

from __future__ import annotations

import datetime as dt

import pyarrow.parquet as pq
import pytest

from hpt.reference.code_descriptions import (
    REFERENCE_SOURCES,
    load_reference,
    parse_ms_drg_table5,
)

# A faithful slice of IPPS Table 5: two title lines, a header row, then data.
SAMPLE = (
    '"TABLE 5.\x97LIST OF MS-DRGS, RELATIVE WEIGHTING FACTORS,\n'
    'AND MEAN LENGTH OF STAY\x97FY 2025 Final Rule"\t\t\t\t\t\t\t\t\t\n'
    "MS-DRG \tFY 2025 Final Post-Acute DRG\tFY 2025 Final Special Pay DRG\tMDC\tTYPE\t"
    "MS-DRG Title\tWeights - Before Cap\tWeights - 10% Cap Applied \tGeometric mean LOS\t"
    "Arithmetic mean LOS\n"
    "001\tNo\tNo\tPRE\tSURG\tHEART TRANSPLANT OR IMPLANT OF HEART ASSIST SYSTEM WITH MCC\t"
    "28.1664\t28.1664\t28.5\t38.5\n"
    "470\tYes\tNo\t08\tSURG\tMAJOR HIP AND KNEE JOINT REPLACEMENT OR REATTACHMENT OF LOWER "
    "EXTREMITY WITHOUT MCC\t1.8855\t1.8855\t1.7\t2.1\n"
    "\n"  # blank line is skipped
)


class TestParseMsDrgTable5:
    def test_row_count_and_skips_titles(self):
        rows = parse_ms_drg_table5(SAMPLE)
        assert len(rows) == 2

    def test_codes_zero_padded_to_three(self):
        rows = parse_ms_drg_table5(SAMPLE)
        assert rows[0]["code"] == "001"
        assert rows[1]["code"] == "470"

    def test_parses_fields(self):
        rows = {r["code"]: r for r in parse_ms_drg_table5(SAMPLE)}
        r = rows["470"]
        assert r["description"].startswith("MAJOR HIP AND KNEE JOINT REPLACEMENT")
        assert r["mdc"] == "08"
        assert r["drg_type"] == "SURG"
        assert r["relative_weight"] == 1.8855
        assert r["geometric_mean_los"] == 1.7
        assert r["post_acute_drg"] is True
        assert r["special_pay_drg"] is False

    def test_missing_header_raises(self):
        with pytest.raises(ValueError, match="header row"):
            parse_ms_drg_table5("no header here\n001\tfoo\n")

    def test_no_data_rows_raises(self):
        header = "MS-DRG \tA\tB\tMDC\tTYPE\tMS-DRG Title\tW1\tW2\tG\tA\n"
        with pytest.raises(ValueError, match="zero MS-DRG rows"):
            parse_ms_drg_table5(header)


class TestLoadReferenceWriter:
    def test_writes_parquet_with_lineage(self, tmp_path, monkeypatch):
        # Pre-seed the raw member so the loader does not hit the network.
        source = REFERENCE_SOURCES["ms-drg"]
        raw_root = tmp_path / "raw"
        member = raw_root / source.name / source.release_date / source.member
        member.parent.mkdir(parents=True, exist_ok=True)
        member.write_text(SAMPLE, encoding="latin-1")

        out = load_reference(
            "ms-drg",
            reference_root=tmp_path / "bronze",
            raw_root=raw_root,
            retrieved_at=dt.datetime(2026, 1, 1, tzinfo=dt.UTC),
        )
        table = pq.read_table(out)
        cols = set(table.column_names)
        assert {"code_type", "code", "description", "code_edition", "source_url"} <= cols
        as_dict = table.to_pydict()
        assert set(as_dict["code_type"]) == {"ms-drg"}
        assert set(as_dict["code_edition"]) == {"FY2025"}
        assert "470" in as_dict["code"]
