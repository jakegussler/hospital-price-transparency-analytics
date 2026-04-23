"""Type-2 SCD snapshot metadata manager backed by per-hospital Parquet files."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
import logging

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
        ("is_current_snapshot", pa.bool_()),
        ("valid_from", pa.timestamp("us", tz="UTC")),
        ("valid_to", pa.timestamp("us", tz="UTC")),
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
    is_current_snapshot: bool = True
    valid_from: datetime = field(default_factory=lambda: datetime.now(UTC))
    valid_to: datetime | None = None

    def to_table(self) -> pa.Table:
        return pa.table(
            {
                "snapshot_id": [self.snapshot_id],
                "hospital_id": [self.hospital_id],
                "source_url": [self.source_url],
                "source_file_name": [self.source_file_name],
                "file_hash": [self.file_hash],
                "ingested_at": [self.ingested_at],
                "is_current_snapshot": [self.is_current_snapshot],
                "valid_from": [self.valid_from],
                "valid_to": [self.valid_to],
            },
            schema=SNAPSHOT_SCHEMA,
        )


class SnapshotManager:
    """Reads and writes snapshot Parquet files through a BronzeStorage instance."""

    def __init__(self, storage: BronzeStorage) -> None:
        self._storage = storage

    def get_current_snapshot(self, hospital_id: str) -> SnapshotRecord | None:
        """Return the current (is_current_snapshot=True) record, or None."""
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

        for fpath in files:
            if not fpath.endswith(".parquet"):
                continue
            with self._storage.open(fpath, "rb") as fh:
                table = pq.read_table(fh, schema=SNAPSHOT_SCHEMA)
            for row in table.to_pydict()["is_current_snapshot"]:
                if row is True:
                    d = {col: table.column(col).to_pylist()[0] for col in table.column_names}
                    logger.debug(
                        "snapshot_current_found",
                        extra={"hospital_id": hospital_id, "snapshot_id": d["snapshot_id"]},
                    )
                    return SnapshotRecord(**d)
        return None

    def write_snapshot(
        self,
        hospital_id: str,
        source_url: str,
        source_file_name: str,
        file_hash: str,
        ingested_at: datetime,
    ) -> SnapshotRecord:
        """Create a new current snapshot and expire the previous one (Type-2)."""
        now = ingested_at

        prev = self.get_current_snapshot(hospital_id)
        if prev is not None:
            prev.is_current_snapshot = False
            prev.valid_to = now
            self._write_record(prev)
            logger.info(
                "snapshot_expired",
                extra={
                    "hospital_id": hospital_id,
                    "snapshot_id": prev.snapshot_id,
                    "valid_to": now.isoformat(),
                },
            )

        record = SnapshotRecord(
            snapshot_id=str(uuid.uuid4()),
            hospital_id=hospital_id,
            source_url=source_url,
            source_file_name=source_file_name,
            file_hash=file_hash,
            ingested_at=now,
            is_current_snapshot=True,
            valid_from=now,
            valid_to=None,
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
        """Convenience: return just the file_hash of the current snapshot."""
        snap = self.get_current_snapshot(hospital_id)
        return snap.file_hash if snap else None

    # -- internals -------------------------------------------------------------

    def _write_record(self, record: SnapshotRecord) -> None:
        path = self._storage.metadata_path(record.hospital_id, record.snapshot_id)
        self._storage.makedirs(self._storage.metadata_path(record.hospital_id))
        table = record.to_table()
        with self._storage.open(path, "wb") as fh:
            pq.write_table(table, fh)
