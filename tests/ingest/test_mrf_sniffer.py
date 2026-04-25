"""Tests for :mod:`hpt.ingest.mrf_sniffer` against the CMS reference fixtures."""

from __future__ import annotations

import gzip
from pathlib import Path

import fsspec
import pytest

from hpt.ingest.detect import Compression
from hpt.ingest.mrf_sniffer import (
    Layout,
    SchemaInfo,
    _classify_csv_layout,
    _extract_csv_version,
    _open_stream,
    sniff_schema,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
CMS_REF = REPO_ROOT / "docs" / "cms_reference" / "hospital-price-transparency"

JSON_V3 = CMS_REF / "examples" / "JSON" / "v3_json_format_example.json"
JSON_V2 = CMS_REF / "archive" / "examples" / "JSON" / "V2.0.0_JSON_Format_Example.json"

CSV_TALL_V2 = (
    CMS_REF / "archive" / "documentation" / "CSV" / "templates"
    / "V2.0.0_Tall_CSV_Format_Template.csv"
)
CSV_WIDE_V2 = (
    CMS_REF / "archive" / "documentation" / "CSV" / "templates"
    / "V2.0.0_Wide_CSV_Format_Template.csv"
)
CSV_TALL_V3 = (
    CMS_REF / "examples" / "CSV" / "Tall Format Examples"
    / "V3.0.0_Tall_CSV_Format_Example.csv"
)
CSV_WIDE_V3 = (
    CMS_REF / "documentation" / "CSV" / "templates"
    / "V3.0.0_Wide_CSV_Format_Template.csv"
)


@pytest.fixture()
def local_fs() -> fsspec.AbstractFileSystem:
    return fsspec.filesystem("local")


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        (JSON_V3, SchemaInfo(layout=Layout.JSON, version="3.0.0")),
        (JSON_V2, SchemaInfo(layout=Layout.JSON, version="2.0.0")),
        (CSV_TALL_V2, SchemaInfo(layout=Layout.CSV_TALL, version="2.0.0")),
        (CSV_WIDE_V2, SchemaInfo(layout=Layout.CSV_WIDE, version="2.0.0")),
        (CSV_TALL_V3, SchemaInfo(layout=Layout.CSV_TALL, version="3.0.0")),
        (CSV_WIDE_V3, SchemaInfo(layout=Layout.CSV_WIDE, version="3.0.0")),
    ],
    ids=["json-v3", "json-v2", "csv-tall-v2", "csv-wide-v2", "csv-tall-v3", "csv-wide-v3"],
)
def test_sniff_reference_fixtures(
    local_fs: fsspec.AbstractFileSystem, path: Path, expected: SchemaInfo
) -> None:
    assert path.exists(), f"missing fixture: {path}"
    assert sniff_schema(str(path), local_fs) == expected


def test_sniff_gzipped_json(tmp_path: Path, local_fs: fsspec.AbstractFileSystem) -> None:
    dest = tmp_path / "mrf.json.gz"
    with gzip.open(dest, "wb") as fh:
        fh.write(JSON_V3.read_bytes())

    assert sniff_schema(str(dest), local_fs) == SchemaInfo(
        layout=Layout.JSON, version="3.0.0"
    )


def test_sniff_gzipped_csv(tmp_path: Path, local_fs: fsspec.AbstractFileSystem) -> None:
    dest = tmp_path / "mrf.csv.gz"
    with gzip.open(dest, "wb") as fh:
        fh.write(CSV_TALL_V3.read_bytes())

    assert sniff_schema(str(dest), local_fs) == SchemaInfo(
        layout=Layout.CSV_TALL, version="3.0.0"
    )


def test_sniff_csv_falls_back_to_cp1252(
    tmp_path: Path, local_fs: fsspec.AbstractFileSystem
) -> None:
    dest = tmp_path / "mrf.csv"
    dest.write_bytes(
        b"\n".join(
            [
                b"hospital_name,last_updated_on,version",
                b"General Hospital-\xe1,2025-01-01,3.0.0",
                b"description,payer_name,plan_name",
                b"X-Ray,Aetna,PPO",
            ]
        )
    )

    assert sniff_schema(str(dest), local_fs) == SchemaInfo(
        layout=Layout.CSV_TALL, version="3.0.0"
    )


def test_short_csv_returns_unknown(
    tmp_path: Path, local_fs: fsspec.AbstractFileSystem
) -> None:
    dest = tmp_path / "short.csv"
    dest.write_text("hospital_name,version\nFoo,3.0.0\n")
    assert sniff_schema(str(dest), local_fs) == SchemaInfo(
        layout=Layout.UNKNOWN, version=None
    )


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


def test_sniff_schema_unknown_content(
    tmp_path: Path, local_fs: fsspec.AbstractFileSystem
) -> None:
    """Binary file with no JSON/CSV markers and no recognized extension → UNKNOWN."""
    dest = tmp_path / "data.bin"
    dest.write_bytes(b"\x00\x01\x02\x03\x04\x05\x06\x07")
    result = sniff_schema(str(dest), local_fs)
    assert result == SchemaInfo(layout=Layout.UNKNOWN, version=None)


def test_open_stream_raises_for_zip_compression(
    tmp_path: Path, local_fs: fsspec.AbstractFileSystem
) -> None:
    """_open_stream raises ValueError for ZIP (must be extracted first)."""
    dest = tmp_path / "archive.zip"
    dest.write_bytes(b"PK\x03\x04")
    with pytest.raises(ValueError, match="Zip archives must be extracted"):
        with _open_stream(str(dest), local_fs, Compression.ZIP):
            pass


def test_classify_csv_layout_unknown_when_no_signature() -> None:
    """Headers with neither payer_name nor 4-segment standard_charge| → UNKNOWN."""
    headers = ["description", "code", "gross_charge"]
    assert _classify_csv_layout(headers) == Layout.UNKNOWN


def test_classify_csv_layout_tall_by_payer_name() -> None:
    headers = ["description", "payer_name", "plan_name", "standard_charge"]
    assert _classify_csv_layout(headers) == Layout.CSV_TALL


def test_classify_csv_layout_wide_by_pipe_column() -> None:
    headers = ["description", "standard_charge|Aetna|PPO|negotiated_dollar"]
    assert _classify_csv_layout(headers) == Layout.CSV_WIDE


def test_extract_csv_version_missing_from_headers() -> None:
    """No 'version' column in meta headers → None."""
    headers = ["hospital_name", "last_updated_on"]
    values = ["Test Hospital", "2025-01-01"]
    assert _extract_csv_version(headers, values) is None


def test_extract_csv_version_index_out_of_bounds() -> None:
    """'version' header at index beyond values list → None."""
    headers = ["hospital_name", "version"]
    values = ["Test Hospital"]  # index 1 is missing
    assert _extract_csv_version(headers, values) is None
