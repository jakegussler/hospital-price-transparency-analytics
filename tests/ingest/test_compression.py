"""Tests for hpt.ingest.compression — decompress_file and helpers."""

from __future__ import annotations

import gzip
import io
import zipfile
from pathlib import Path

import fsspec
import pytest

from hpt.ingest.compression import (
    _pick_mrf_member,
    decompress_file,
    materialize_for_parse,
)
from hpt.ingest.detect import Compression

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _local_fs() -> fsspec.AbstractFileSystem:
    return fsspec.filesystem("local")


def _write_gz(path: Path, content: bytes) -> None:
    with gzip.open(path, "wb") as fh:
        fh.write(content)


def _write_zip(path: Path, members: dict[str, bytes]) -> None:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, data in members.items():
            zf.writestr(name, data)
    path.write_bytes(buf.getvalue())


# ---------------------------------------------------------------------------
# Gzip
# ---------------------------------------------------------------------------


class TestDecompressGzip:
    def test_strips_gz_extension(self, tmp_path):
        src = tmp_path / "mrf.json.gz"
        _write_gz(src, b'{"hospital": "test"}')

        result = decompress_file(str(src), _local_fs(), Compression.GZIP)

        assert result.endswith("mrf.json")

    def test_removes_original(self, tmp_path):
        src = tmp_path / "mrf.json.gz"
        _write_gz(src, b"content")

        decompress_file(str(src), _local_fs(), Compression.GZIP)

        assert not src.exists()

    def test_content_correct(self, tmp_path):
        src = tmp_path / "data.json.gz"
        original = b'{"key": "value"}'
        _write_gz(src, original)

        dest_str = decompress_file(str(src), _local_fs(), Compression.GZIP)
        dest = Path(dest_str)

        assert dest.read_bytes() == original

    def test_dest_extension_preserved(self, tmp_path):
        src = tmp_path / "mrf.csv.gz"
        _write_gz(src, b"col1,col2\nval1,val2\n")

        result = decompress_file(str(src), _local_fs(), Compression.GZIP)

        assert result.endswith("mrf.csv")


class TestMaterializeGzipForParse:
    def test_preserves_original_gzip(self, tmp_path):
        src = tmp_path / "mrf.csv.gz"
        _write_gz(src, b"col1,col2\nval1,val2\n")

        result = materialize_for_parse(
            str(src),
            _local_fs(),
            Compression.GZIP,
            str(tmp_path / ".tmp" / "parser_input"),
        )

        assert src.exists()
        assert Path(result).name == "parser_input.csv"
        assert Path(result).read_bytes() == b"col1,col2\nval1,val2\n"


# ---------------------------------------------------------------------------
# Zip
# ---------------------------------------------------------------------------


class TestDecompressZip:
    def test_single_member_extracted(self, tmp_path):
        src = tmp_path / "archive.zip"
        _write_zip(src, {"charges.json": b'{"data": 1}'})

        result = decompress_file(str(src), _local_fs(), Compression.ZIP)

        assert Path(result).name == "charges.json"

    def test_removes_original(self, tmp_path):
        src = tmp_path / "archive.zip"
        _write_zip(src, {"charges.json": b'{"data": 1}'})

        decompress_file(str(src), _local_fs(), Compression.ZIP)

        assert not src.exists()

    def test_content_correct(self, tmp_path):
        src = tmp_path / "archive.zip"
        original = b'{"hospital_name": "Test"}'
        _write_zip(src, {"mrf.json": original})

        dest_str = decompress_file(str(src), _local_fs(), Compression.ZIP)

        assert Path(dest_str).read_bytes() == original

    def test_multiple_members_picks_mrf_extension(self, tmp_path):
        src = tmp_path / "archive.zip"
        _write_zip(
            src,
            {
                "charges.json": b'{"data": 1}',
                "readme.txt": b"README",
            },
        )

        result = decompress_file(str(src), _local_fs(), Compression.ZIP)

        assert Path(result).name == "charges.json"

    def test_empty_archive_raises(self, tmp_path):
        src = tmp_path / "empty.zip"
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w"):
            pass
        src.write_bytes(buf.getvalue())

        with pytest.raises(ValueError, match="no files"):
            decompress_file(str(src), _local_fs(), Compression.ZIP)

    def test_ambiguous_mrf_members_raises(self, tmp_path):
        src = tmp_path / "ambiguous.zip"
        _write_zip(
            src,
            {
                "charges_a.json": b'{"data": 1}',
                "charges_b.json": b'{"data": 2}',
            },
        )

        with pytest.raises(ValueError, match="cannot determine"):
            decompress_file(str(src), _local_fs(), Compression.ZIP)


class TestMaterializeZipForParse:
    def test_preserves_original_zip(self, tmp_path):
        src = tmp_path / "archive.zip"
        original = b'{"hospital_name": "Test"}'
        _write_zip(src, {"nested/mrf.json": original})

        result = materialize_for_parse(
            str(src),
            _local_fs(),
            Compression.ZIP,
            str(tmp_path / ".tmp" / "parser_input"),
        )

        assert src.exists()
        assert Path(result).name == "parser_input.json"
        assert Path(result).read_bytes() == original

    def test_gunzips_zip_member_for_parser(self, tmp_path):
        src = tmp_path / "archive.zip"
        gz_payload = io.BytesIO()
        with gzip.GzipFile(fileobj=gz_payload, mode="wb") as fh:
            fh.write(b"col1,col2\nval1,val2\n")
        _write_zip(src, {"mrf.csv.gz": gz_payload.getvalue()})

        result = materialize_for_parse(
            str(src),
            _local_fs(),
            Compression.ZIP,
            str(tmp_path / ".tmp" / "parser_input"),
        )

        assert src.exists()
        assert Path(result).name == "parser_input.csv"
        assert Path(result).read_bytes() == b"col1,col2\nval1,val2\n"


# ---------------------------------------------------------------------------
# _pick_mrf_member
# ---------------------------------------------------------------------------


class TestPickMrfMember:
    def test_single_member_always_chosen(self):
        assert _pick_mrf_member(["random.xyz"], "archive.zip") == "random.xyz"

    def test_multiple_picks_mrf_extension(self):
        members = ["readme.txt", "charges.json", "logo.png"]
        assert _pick_mrf_member(members, "archive.zip") == "charges.json"

    def test_csv_extension_picked(self):
        members = ["readme.txt", "charges.csv"]
        assert _pick_mrf_member(members, "archive.zip") == "charges.csv"

    def test_ndjson_extension_picked(self):
        members = ["readme.txt", "charges.ndjson"]
        assert _pick_mrf_member(members, "archive.zip") == "charges.ndjson"

    def test_ambiguous_raises(self):
        members = ["a.json", "b.json"]
        with pytest.raises(ValueError, match="cannot determine"):
            _pick_mrf_member(members, "archive.zip")

    def test_no_mrf_candidate_raises(self):
        members = ["readme.txt", "logo.png"]
        with pytest.raises(ValueError, match="cannot determine"):
            _pick_mrf_member(members, "archive.zip")


# ---------------------------------------------------------------------------
# Unsupported compression type
# ---------------------------------------------------------------------------


class TestUnsupportedCompression:
    def test_none_compression_raises(self, tmp_path):
        src = tmp_path / "file.json"
        src.write_bytes(b"{}")

        with pytest.raises(ValueError, match="Unsupported compression"):
            decompress_file(str(src), _local_fs(), Compression.NONE)
