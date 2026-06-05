"""Tests for SnapshotManager: append-only writes, latest-by-recency resolution.

Snapshot currentness is owned by dbt, which derives it from ``valid_from``
recency. Python only appends immutable records and resolves "the latest
snapshot" so ingest knows which file to parse and download can dedupe by hash.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pyarrow.parquet as pq
import pytest

from hpt.ingest.snapshot import SnapshotManager
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
        assert snap.valid_from == ts
        assert snap.ingested_at == ts
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


class TestLatestResolution:
    def test_latest_snapshot_wins(self, manager):
        t1 = datetime(2025, 6, 1, 12, 0, tzinfo=UTC)
        t2 = datetime(2025, 6, 2, 12, 0, tzinfo=UTC)

        manager.write_snapshot(
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

    def test_prior_snapshot_left_untouched(self, manager, storage):
        """Writes are append-only: a new snapshot never rewrites the old file."""
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
        # The first record is unchanged and carries no stored currentness flag.
        assert row["valid_from"][0] == t1
        assert row["file_hash"][0] == "hash_v1"
        assert "is_current_snapshot" not in row
        assert "valid_to" not in row

    def test_three_snapshots_latest_is_resolved(self, manager):
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
