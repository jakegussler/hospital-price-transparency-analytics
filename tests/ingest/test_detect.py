"""Tests for hpt.ingest.detect — detect_format."""

from __future__ import annotations

import gzip
import io
import struct
import zipfile
from pathlib import Path

import fsspec
import pytest

from hpt.ingest.detect import (
    Compression,
    ContentFormat,
    FormatInfo,
    detect_format,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write(path: Path, content: bytes) -> None:
    path.write_bytes(content)


def _local_fs() -> fsspec.AbstractFileSystem:
    return fsspec.filesystem("local")


# ---------------------------------------------------------------------------
# Compression detection via magic bytes
# ---------------------------------------------------------------------------


class TestCompressionDetection:
    def test_gzip_magic_bytes(self, tmp_path):
        p = tmp_path / "file.dat"
        # Write real gzip magic header
        _write(p, b"\x1f\x8b" + b"\x00" * 6)
        result = detect_format(str(p), _local_fs())
        assert result.compression == Compression.GZIP

    def test_zip_magic_bytes(self, tmp_path):
        p = tmp_path / "file.dat"
        _write(p, b"\x50\x4b\x03\x04" + b"\x00" * 4)
        result = detect_format(str(p), _local_fs())
        assert result.compression == Compression.ZIP

    def test_no_compression_for_plain_text(self, tmp_path):
        p = tmp_path / "file.json"
        _write(p, b'{"hospital_name": "Test"}')
        result = detect_format(str(p), _local_fs())
        assert result.compression == Compression.NONE


# ---------------------------------------------------------------------------
# Content format detection — uncompressed files
# ---------------------------------------------------------------------------


class TestContentFormatUncompressed:
    def test_json_opening_brace(self, tmp_path):
        p = tmp_path / "mrf.json"
        _write(p, b'{"hospital_name": "Test"}')
        result = detect_format(str(p), _local_fs())
        assert result.content_format == ContentFormat.JSON
        assert result.compression == Compression.NONE

    def test_json_leading_bracket(self, tmp_path):
        p = tmp_path / "mrf.json"
        _write(p, b"[1, 2, 3]")
        result = detect_format(str(p), _local_fs())
        assert result.content_format == ContentFormat.JSON

    def test_json_with_leading_whitespace(self, tmp_path):
        p = tmp_path / "mrf.json"
        _write(p, b"   {}")
        result = detect_format(str(p), _local_fs())
        assert result.content_format == ContentFormat.JSON

    def test_csv_by_extension(self, tmp_path):
        p = tmp_path / "charges.csv"
        _write(p, b"hospital_name,version\nFoo,3.0.0\n")
        result = detect_format(str(p), _local_fs())
        assert result.content_format == ContentFormat.CSV
        assert result.compression == Compression.NONE

    def test_unknown_binary_no_extension(self, tmp_path):
        p = tmp_path / "charges.dat"
        _write(p, b"\x00\x01\x02\x03\x04\x05\x06\x07")
        result = detect_format(str(p), _local_fs())
        assert result.content_format == ContentFormat.UNKNOWN
        assert result.compression == Compression.NONE


# ---------------------------------------------------------------------------
# Content format detection — compressed files (extension-based fallback)
# ---------------------------------------------------------------------------


class TestContentFormatCompressed:
    def test_json_extension_for_gz(self, tmp_path):
        p = tmp_path / "mrf.json.gz"
        _write(p, b"\x1f\x8b" + b"\x00" * 6)
        result = detect_format(str(p), _local_fs())
        assert result.compression == Compression.GZIP
        assert result.content_format == ContentFormat.JSON

    def test_csv_extension_for_gz(self, tmp_path):
        p = tmp_path / "charges.csv.gz"
        _write(p, b"\x1f\x8b" + b"\x00" * 6)
        result = detect_format(str(p), _local_fs())
        assert result.compression == Compression.GZIP
        assert result.content_format == ContentFormat.CSV

    def test_unknown_extension_for_gz(self, tmp_path):
        p = tmp_path / "data.dat.gz"
        _write(p, b"\x1f\x8b" + b"\x00" * 6)
        result = detect_format(str(p), _local_fs())
        assert result.compression == Compression.GZIP
        assert result.content_format == ContentFormat.UNKNOWN

    def test_zip_with_unknown_extension(self, tmp_path):
        p = tmp_path / "archive.zip"
        _write(p, b"\x50\x4b\x03\x04" + b"\x00" * 4)
        result = detect_format(str(p), _local_fs())
        assert result.compression == Compression.ZIP
        # zip extension not recognized for content → UNKNOWN
        assert result.content_format == ContentFormat.UNKNOWN


# ---------------------------------------------------------------------------
# FormatInfo is a frozen dataclass
# ---------------------------------------------------------------------------


class TestFormatInfo:
    def test_equality(self):
        a = FormatInfo(Compression.GZIP, ContentFormat.JSON)
        b = FormatInfo(Compression.GZIP, ContentFormat.JSON)
        assert a == b

    def test_immutable(self):
        fi = FormatInfo(Compression.NONE, ContentFormat.CSV)
        with pytest.raises(Exception):
            fi.compression = Compression.GZIP  # type: ignore[misc]
