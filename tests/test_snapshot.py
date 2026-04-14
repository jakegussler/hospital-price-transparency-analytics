"""Tests for SnapshotManager: Type-2 SCD transitions."""

from __future__ import annotations

from datetime import UTC, datetime

import pyarrow.parquet as pq
import pytest

from hpt.ingest.snapshot import SnapshotManager, SnapshotRecord
from hpt.ingest.storage import BronzeStorage


@pytest.fixture()
def storage(tmp_path):
    return BronzeStorage(f"file://{tmp_path}")


@pytest.fixture()
def manager(storage):
    return SnapshotManager(storage)


class TestFirstSnapshot:
    def test_no_current_initially(self, manager):
        assert manager.get_current_snapshot("h1") is None
        assert manager.current_hash("h1") is None

    def test_write_first_snapshot(self, manager):
        ts = datetime(2025, 6, 1, 12, 0, tzinfo=UTC)
        snap = manager.write_snapshot(
            hospital_id="h1",
            source_url="https://example.com/a.csv",
            source_file_name="a.csv",
            file_hash="aaa111",
            ingested_at=ts,
        )
        assert snap.is_current_snapshot is True
        assert snap.valid_from == ts
        assert snap.valid_to is None
        assert snap.hospital_id == "h1"
        assert snap.file_hash == "aaa111"

    def test_current_hash_after_write(self, manager):
        ts = datetime(2025, 6, 1, 12, 0, tzinfo=UTC)
        manager.write_snapshot(
            hospital_id="h1",
            source_url="https://example.com/a.csv",
            source_file_name="a.csv",
            file_hash="aaa111",
            ingested_at=ts,
        )
        assert manager.current_hash("h1") == "aaa111"


class TestType2Transition:
    def test_new_snapshot_expires_old(self, manager):
        t1 = datetime(2025, 6, 1, 12, 0, tzinfo=UTC)
        t2 = datetime(2025, 6, 2, 12, 0, tzinfo=UTC)

        snap1 = manager.write_snapshot(
            hospital_id="h1",
            source_url="https://example.com/a.csv",
            source_file_name="a.csv",
            file_hash="hash_v1",
            ingested_at=t1,
        )

        snap2 = manager.write_snapshot(
            hospital_id="h1",
            source_url="https://example.com/a.csv",
            source_file_name="a.csv",
            file_hash="hash_v2",
            ingested_at=t2,
        )

        current = manager.get_current_snapshot("h1")
        assert current is not None
        assert current.snapshot_id == snap2.snapshot_id
        assert current.file_hash == "hash_v2"
        assert current.is_current_snapshot is True
        assert current.valid_to is None

    def test_expired_snapshot_has_valid_to(self, manager, storage):
        t1 = datetime(2025, 6, 1, 12, 0, tzinfo=UTC)
        t2 = datetime(2025, 6, 2, 12, 0, tzinfo=UTC)

        snap1 = manager.write_snapshot(
            hospital_id="h1",
            source_url="https://example.com/a.csv",
            source_file_name="a.csv",
            file_hash="hash_v1",
            ingested_at=t1,
        )

        manager.write_snapshot(
            hospital_id="h1",
            source_url="https://example.com/a.csv",
            source_file_name="a.csv",
            file_hash="hash_v2",
            ingested_at=t2,
        )

        old_path = storage.metadata_path("h1", snap1.snapshot_id)
        with storage.open(old_path, "rb") as fh:
            table = pq.read_table(fh)
        row = table.to_pydict()
        assert row["is_current_snapshot"][0] is False
        assert row["valid_to"][0] == t2

    def test_three_snapshots_only_last_is_current(self, manager):
        for i in range(3):
            manager.write_snapshot(
                hospital_id="h1",
                source_url="https://example.com/a.csv",
                source_file_name="a.csv",
                file_hash=f"hash_{i}",
                ingested_at=datetime(2025, 6, i + 1, tzinfo=UTC),
            )

        current = manager.get_current_snapshot("h1")
        assert current is not None
        assert current.file_hash == "hash_2"


class TestIsolation:
    def test_different_hospitals_independent(self, manager):
        ts = datetime(2025, 6, 1, 12, 0, tzinfo=UTC)
        manager.write_snapshot(
            hospital_id="h1",
            source_url="https://example.com/a.csv",
            source_file_name="a.csv",
            file_hash="hash_h1",
            ingested_at=ts,
        )
        manager.write_snapshot(
            hospital_id="h2",
            source_url="https://example.com/b.csv",
            source_file_name="b.csv",
            file_hash="hash_h2",
            ingested_at=ts,
        )

        assert manager.current_hash("h1") == "hash_h1"
        assert manager.current_hash("h2") == "hash_h2"
