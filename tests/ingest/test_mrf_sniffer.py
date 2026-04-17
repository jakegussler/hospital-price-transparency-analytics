"""Tests for :mod:`hpt.ingest.mrf_sniffer` against the CMS reference fixtures."""

from __future__ import annotations

import gzip
from pathlib import Path

import fsspec
import pytest

from hpt.ingest.mrf_sniffer import Layout, SchemaInfo, sniff_schema

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


def test_short_csv_returns_unknown(
    tmp_path: Path, local_fs: fsspec.AbstractFileSystem
) -> None:
    dest = tmp_path / "short.csv"
    dest.write_text("hospital_name,version\nFoo,3.0.0\n")
    assert sniff_schema(str(dest), local_fs) == SchemaInfo(
        layout=Layout.UNKNOWN, version=None
    )
