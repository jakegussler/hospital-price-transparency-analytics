"""Append-only snapshot metadata manager backed by per-hospital Parquet files.

Snapshot *currentness* (which snapshot is the live one, when each version was
superseded) is owned entirely by dbt, which derives it from ``valid_from``
recency in the Bronze ``hospital_mrf_snapshots`` table. Python only records
immutable facts about each downloaded file and resolves "the latest snapshot"
by recency so ingest knows which file to parse and download can dedupe by hash.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field, fields
from datetime import UTC, datetime

import pyarrow as pa
import pyarrow.parquet as pq

from hpt.ingest.storage import BronzeStorage

logger = logging.getLogger(__name__)

SNAPSHOT_SCHEMA = pa.schema(
    [
        ("snapshot_id", pa.string()),
        ("hospital_id", pa.string()),
        ("source_url", pa.string()),
        ("source_file_name", pa.string()),
        ("file_hash", pa.string()),
        ("ingested_at", pa.timestamp("us", tz="UTC")),
        ("valid_from", pa.timestamp("us", tz="UTC")),
    ]
)


@dataclass
class SnapshotRecord:
    snapshot_id: str
    hospital_id: str
    source_url: str
    source_file_name: str
    file_hash: str
    ingested_at: datetime
    valid_from: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_table(self) -> pa.Table:
        return pa.table(
            {
                "snapshot_id": [self.snapshot_id],
                "hospital_id": [self.hospital_id],
                "source_url": [self.source_url],
                "source_file_name": [self.source_file_name],
                "file_hash": [self.file_hash],
                "ingested_at": [self.ingested_at],
                "valid_from": [self.valid_from],
            },
            schema=SNAPSHOT_SCHEMA,
        )


class SnapshotManager:
    """Reads and writes snapshot Parquet files through a BronzeStorage instance."""

    def __init__(self, storage: BronzeStorage) -> None:
        self._storage = storage

    def get_current_snapshot(self, hospital_id: str) -> SnapshotRecord | None:
        """Return the latest snapshot for *hospital_id*, or None.

        "Current" means the most recently valid snapshot, resolved by
        ``valid_from`` recency (ties broken by ``ingested_at`` then
        ``snapshot_id``). Currentness is no longer persisted as a flag; dbt
        derives it independently from the same recency ordering in Bronze.
        """
        meta_dir = self._storage.metadata_path(hospital_id)
        files = self._storage.ls(meta_dir)
        logger.debug(
            "snapshot_scan_start",
            extra={
                "hospital_id": hospital_id,
                "metadata_path": meta_dir,
                "file_count": len(files),
            },
        )
        if not files:
            return None

        best: SnapshotRecord | None = None
        best_key: tuple[datetime, datetime, str] | None = None
        for fpath in files:
            if not fpath.endswith(".parquet"):
                continue
            with self._storage.open(fpath, "rb") as fh:
                table = pq.read_table(fh)
            record = self._record_from_table(table)
            if record is None:
                continue
            key = (record.valid_from, record.ingested_at, record.snapshot_id)
            if best_key is None or key > best_key:
                best, best_key = record, key

        if best is not None:
            logger.debug(
                "snapshot_current_found",
                extra={"hospital_id": hospital_id, "snapshot_id": best.snapshot_id},
            )
        return best

    def write_snapshot(
        self,
        hospital_id: str,
        source_url: str,
        source_file_name: str,
        file_hash: str,
        ingested_at: datetime,
    ) -> SnapshotRecord:
        """Append a new snapshot record. Prior snapshots are left untouched.

        This is append-only: currentness is derived downstream from
        ``valid_from`` recency, so there is no previous record to expire here.
        """
        record = SnapshotRecord(
            snapshot_id=str(uuid.uuid4()),
            hospital_id=hospital_id,
            source_url=source_url,
            source_file_name=source_file_name,
            file_hash=file_hash,
            ingested_at=ingested_at,
            valid_from=ingested_at,
        )
        self._write_record(record)
        logger.info(
            "snapshot_written",
            extra={
                "hospital_id": hospital_id,
                "snapshot_id": record.snapshot_id,
                "source_file_name": source_file_name,
            },
        )
        return record

    def current_hash(self, hospital_id: str) -> str | None:
        """Convenience: return just the file_hash of the latest snapshot."""
        snap = self.get_current_snapshot(hospital_id)
        return snap.file_hash if snap else None

    # -- internals -------------------------------------------------------------

    @staticmethod
    def _record_from_table(table: pa.Table) -> SnapshotRecord | None:
        """Build a SnapshotRecord from the first row, ignoring legacy columns.

        Older metadata files may still carry retired columns (for example the
        former ``is_current_snapshot`` / ``valid_to`` SCD fields); those are
        dropped here so historical metadata remains readable.
        """
        if table.num_rows == 0:
            return None
        known = {f.name for f in fields(SnapshotRecord)}
        data = {
            name: table.column(name).to_pylist()[0] for name in table.column_names if name in known
        }
        return SnapshotRecord(**data)

    def _write_record(self, record: SnapshotRecord) -> None:
        path = self._storage.metadata_path(record.hospital_id, record.snapshot_id)
        self._storage.makedirs(self._storage.metadata_path(record.hospital_id))
        table = record.to_table()
        with self._storage.open(path, "wb") as fh:
            pq.write_table(table, fh)
