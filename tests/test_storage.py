"""Tests for BronzeStorage: Hive paths, collision suffix, fsspec round-trip."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from hpt.ingest.storage import BronzeStorage


@pytest.fixture()
def storage(tmp_path):
    return BronzeStorage(f"file://{tmp_path}")


class TestRawPath:
    def test_basic_path_layout(self, storage, tmp_path):
        ts = datetime(2025, 6, 15, tzinfo=UTC)
        path = storage.raw_path("test-hospital", "charges.csv", ingested_at=ts)
        assert "raw/hospital_id=test-hospital/ingested_at=2025-06-15/charges.csv" in path

    def test_default_ingested_at_is_today(self, storage):
        path = storage.raw_path("h1", "file.json")
        today = datetime.now(UTC).strftime("%Y-%m-%d")
        assert f"ingested_at={today}" in path

    def test_collision_suffix_when_file_exists(self, storage, tmp_path):
        ts = datetime(2025, 6, 15, tzinfo=UTC)
        first = storage.raw_path("h1", "charges.csv", ingested_at=ts, file_hash="aabbccddee11")
        storage.makedirs(first.rsplit("/", 1)[0])
        with storage.open(first, "wb") as f:
            f.write(b"first version")

        second = storage.raw_path("h1", "charges.csv", ingested_at=ts, file_hash="112233445566")
        assert "charges__112233445566.csv" in second
        assert second != first

    def test_no_collision_when_dir_empty(self, storage):
        ts = datetime(2025, 6, 15, tzinfo=UTC)
        path = storage.raw_path("h1", "charges.csv", ingested_at=ts, file_hash="aabb")
        assert path.endswith("charges.csv")


class TestTempPath:
    def test_temp_path_contains_hospital_id(self, storage):
        tmp = storage.temp_path("my-hospital")
        assert "my-hospital" in tmp
        assert ".tmp" in tmp

    def test_temp_paths_are_unique(self, storage):
        a = storage.temp_path("h1")
        b = storage.temp_path("h1")
        assert a != b


class TestMetadataPath:
    def test_directory_path(self, storage):
        p = storage.metadata_path("h1")
        assert "metadata/hospital_mrf_snapshots/hospital_id=h1" in p

    def test_file_path(self, storage):
        p = storage.metadata_path("h1", "abc-123")
        assert p.endswith("abc-123.parquet")


class TestFsspecRoundTrip:
    def test_write_and_read(self, storage):
        path = storage.temp_path("rt")
        storage.makedirs(path.rsplit("/", 1)[0])
        with storage.open(path, "wb") as f:
            f.write(b"hello world")

        with storage.open(path, "rb") as f:
            assert f.read() == b"hello world"

    def test_mv(self, storage):
        src = storage.temp_path("mv-test")
        storage.makedirs(src.rsplit("/", 1)[0])
        with storage.open(src, "wb") as f:
            f.write(b"data")

        dst = storage.temp_path("mv-dest")
        storage.mv(src, dst)

        assert not storage.exists(src)
        with storage.open(dst, "rb") as f:
            assert f.read() == b"data"

    def test_rm_nonexistent_is_noop(self, storage):
        storage.rm("/nonexistent/path/file.txt")

    def test_ls_nonexistent_returns_empty(self, storage):
        assert storage.ls("/nonexistent/dir") == []
