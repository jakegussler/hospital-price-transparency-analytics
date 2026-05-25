from __future__ import annotations

import logging
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit


def sanitize_url(url: str) -> str:
    """Return a URL stripped of query/fragment components."""
    parts = urlsplit(url)
    if parts.scheme and parts.netloc:
        return f"{parts.scheme}://{parts.netloc}{parts.path}"
    return parts.path or url


def log_url_event(
    logger: logging.Logger,
    hospital_id: str,
    url: str,
    event: str,
    *,
    level: int = logging.INFO,
    **extra: Any,
) -> None:
    safe_url = sanitize_url(url)
    parsed = urlsplit(safe_url)
    logger.log(
        level,
        event,
        extra={
            "hospital_id": hospital_id,
            "url": safe_url,
            "url_host": parsed.netloc,
            "url_path": parsed.path,
            **extra,
        },
    )


def log_transfer_summary(
    logger: logging.Logger,
    hospital_id: str,
    nbytes: int,
    duration_s: float,
    file_hash: str | None,
    *,
    event: str,
    snapshot_id: str | None = None,
    level: int = logging.INFO,
    **extra: Any,
) -> None:
    payload: dict[str, Any] = {
        "hospital_id": hospital_id,
        "bytes": nbytes,
        "duration_s": round(duration_s, 2),
        **extra,
    }
    if file_hash:
        payload["file_hash"] = file_hash
    if snapshot_id:
        payload["snapshot_id"] = snapshot_id
    logger.log(level, event, extra=payload)


def log_download_chunk(
    logger: logging.Logger,
    hospital_id: str,
    chunk_index: int,
    chunk_bytes: int,
    total_bytes: int,
) -> None:
    logger.debug(
        "download_chunk",
        extra={
            "hospital_id": hospital_id,
            "chunk_index": chunk_index,
            "chunk_bytes": chunk_bytes,
            "bytes": total_bytes,
        },
    )


def log_ingest_phase(
    logger: logging.Logger,
    phase: str,
    snapshot_id: str,
    hospital_id: str,
    *,
    level: int = logging.INFO,
    **fields: Any,
) -> None:
    logger.log(
        level,
        phase,
        extra={"snapshot_id": snapshot_id, "hospital_id": hospital_id, **fields},
    )


def log_schema_sniff(
    logger: logging.Logger,
    path_basename: str,
    layout: str,
    version: str | None,
    *,
    compression: str | None = None,
    content_format: str | None = None,
    level: int = logging.INFO,
) -> None:
    extra: dict[str, Any] = {
        "path": path_basename,
        "layout": layout,
        "schema_version": version,
    }
    if compression is not None:
        extra["compression"] = compression
    if content_format is not None:
        extra["content_format"] = content_format
    logger.log(level, "schema_sniffed", extra=extra)


def log_bronze_part_roll(
    logger: logging.Logger,
    snapshot_id: str,
    table_name: str,
    part_index: int,
    row_threshold: int,
) -> None:
    logger.info(
        "bronze_part_rolled",
        extra={
            "snapshot_id": snapshot_id,
            "table_name": table_name,
            "part_index": part_index,
            "row_threshold": row_threshold,
        },
    )


def log_registry_loaded(
    logger: logging.Logger, path: Path, n_hospitals: int
) -> None:
    logger.info(
        "registry_loaded",
        extra={"path": str(path), "hospital_count": n_hospitals},
    )
