"""Wire :mod:`hpt.ingest` metadata through the correct parser into Bronze Parquet.

This is the single entrypoint used by the CLI to translate a downloaded
MRF file into the Bronze layer. It:

1. Resolves the local file for a snapshot record.
2. Runs :func:`hpt.ingest.mrf_sniffer.sniff_schema` to identify layout and
   version.
3. Dispatches to the format-specific parser (only JSON is implemented
   today; CSV parsers raise :class:`NotImplementedError`).
4. Streams parser batches through :class:`hpt.loaders.parquet.BronzeWriter`.
"""

from __future__ import annotations

import logging
import posixpath
from pathlib import Path
from typing import Any

from hpt.ingest.mrf_sniffer import Layout, sniff_schema
from hpt.ingest.snapshot import SnapshotRecord
from hpt.ingest.storage import BronzeStorage
from hpt.loaders.parquet import BronzeWriter
from hpt.parsers.base import BaseParser
from hpt.parsers.json_mrf import JsonMrfParser

logger = logging.getLogger(__name__)

_LAYOUT_TO_SOURCE_FORMAT: dict[Layout, str] = {
    Layout.JSON: "json",
    Layout.CSV_TALL: "csv_tall",
    Layout.CSV_WIDE: "csv_wide",
}


def ingest_snapshot(
    snapshot: SnapshotRecord,
    hospital_config: dict[str, Any],
    storage: BronzeStorage,
    bronze_root: Path,
    quarantine_root: Path,
) -> dict[str, Any]:
    """Parse a downloaded MRF and write the Bronze layer for it.

    Returns a small summary dict for logging by the caller.
    """
    local_path = resolve_local_path(snapshot, storage)
    logger.info(
        "ingest_start",
        extra={
            "snapshot_id": snapshot.snapshot_id,
            "hospital_id": snapshot.hospital_id,
            "local_path": str(local_path),
        },
    )

    schema_info = sniff_schema(str(local_path), storage.fs)

    source_format = _LAYOUT_TO_SOURCE_FORMAT.get(schema_info.layout)
    if source_format is None:
        raise ValueError(
            f"Cannot ingest snapshot {snapshot.snapshot_id}: unknown layout "
            f"{schema_info.layout!r} for {local_path}"
        )

    snapshot_meta = _snapshot_meta(snapshot, source_format, schema_info.version)
    parser = _build_parser(
        schema_info.layout,
        hospital_config=hospital_config,
        snapshot_meta=snapshot_meta,
        quarantine_root=quarantine_root,
    )

    with BronzeWriter(bronze_root, snapshot.snapshot_id) as writer:
        for batch in parser.parse(local_path):
            writer.write_batch(batch)

    logger.info(
        "ingest_complete",
        extra={
            "snapshot_id": snapshot.snapshot_id,
            "hospital_id": snapshot.hospital_id,
            "source_format": source_format,
            "schema_version": schema_info.version,
        },
    )
    return {
        "snapshot_id": snapshot.snapshot_id,
        "hospital_id": snapshot.hospital_id,
        "source_format": source_format,
        "schema_version": schema_info.version,
        "local_path": str(local_path),
    }


def resolve_local_path(
    snapshot: SnapshotRecord, storage: BronzeStorage
) -> Path:
    """Locate the downloaded MRF file for *snapshot* under the raw partition.

    :class:`~hpt.ingest.snapshot.SnapshotRecord` does not persist the on-disk
    path because decompression may rename the file after the record was
    written. We resolve it now by listing the partition directory and
    matching either by filename stem or by the short hash suffix injected
    by :meth:`BronzeStorage._collision_safe_name`.
    """
    date_str = snapshot.ingested_at.strftime("%Y-%m-%d")
    partition_dir = posixpath.join(
        storage._base_uri,  # type: ignore[attr-defined]
        "raw",
        f"hospital_id={snapshot.hospital_id}",
        f"ingested_at={date_str}",
    )
    # BronzeStorage.ls returns protocol-stripped paths; we reconstruct
    # via the storage base URI so fsspec can re-open them.
    files = [p for p in storage.ls(partition_dir) if not p.endswith("/")]

    if not files:
        raise FileNotFoundError(
            f"No files found for snapshot {snapshot.snapshot_id} in "
            f"{partition_dir}"
        )

    # Prefer the exact filename match, then the hash-suffixed variant,
    # then (as a last resort) the only file in a single-file partition.
    candidates = [p for p in files if posixpath.basename(p) == snapshot.source_file_name]
    if not candidates:
        hash_suffix = snapshot.file_hash[:12]
        candidates = [p for p in files if hash_suffix in posixpath.basename(p)]
    if not candidates:
        # Decompression may have stripped an extension; match by stem.
        stem = snapshot.source_file_name.split(".")[0]
        candidates = [
            p for p in files if posixpath.basename(p).startswith(stem)
        ]
    if not candidates and len(files) == 1:
        candidates = files
    if not candidates:
        raise FileNotFoundError(
            f"Could not identify the raw file for snapshot "
            f"{snapshot.snapshot_id} among {files}"
        )
    return Path(candidates[0])


def _snapshot_meta(
    snapshot: SnapshotRecord,
    source_format: str,
    schema_version: str | None,
) -> dict[str, Any]:
    """Project a SnapshotRecord into the dict shape expected by parsers."""
    return {
        "snapshot_id": snapshot.snapshot_id,
        "hospital_id": snapshot.hospital_id,
        "source_url": snapshot.source_url,
        "source_file_name": snapshot.source_file_name,
        "source_format": source_format,
        "file_hash": snapshot.file_hash,
        "ingested_at": snapshot.ingested_at,
        "is_current_snapshot": snapshot.is_current_snapshot,
        "valid_from": snapshot.valid_from,
        "valid_to": snapshot.valid_to,
        "schema_version": schema_version,
    }


def _build_parser(
    layout: Layout,
    *,
    hospital_config: dict[str, Any],
    snapshot_meta: dict[str, Any],
    quarantine_root: Path,
) -> BaseParser:
    if layout == Layout.JSON:
        return JsonMrfParser(
            hospital_config=hospital_config,
            snapshot_meta=snapshot_meta,
            quarantine_root=quarantine_root,
        )
    if layout in (Layout.CSV_TALL, Layout.CSV_WIDE):
        raise NotImplementedError(
            f"{layout.value} ingestion has not been implemented yet"
        )
    raise ValueError(f"Unsupported layout: {layout!r}")
