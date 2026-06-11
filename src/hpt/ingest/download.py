"""Stream MRF files from publisher URLs with SHA-256 change detection."""

from __future__ import annotations

import hashlib
import logging
import posixpath
import re
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from urllib.parse import urlparse

import httpx

from hpt.ingest.client import build_httpx_client
from hpt.ingest.config import DownloadConfig
from hpt.ingest.detect import detect_format
from hpt.ingest.snapshot import SnapshotManager, SnapshotRecord
from hpt.ingest.storage import BronzeStorage
from hpt.logging.log_helpers import (
    log_download_chunk,
    log_transfer_summary,
    log_url_event,
    sanitize_url,
)
from hpt.registry.models import HospitalSource

logger = logging.getLogger(__name__)

CHUNK_SIZE = 256 * 1024  # 256 KiB

_build_client = build_httpx_client


class Outcome(str, Enum):
    DOWNLOADED = "downloaded"
    UNCHANGED = "unchanged"
    FAILED = "failed"
    DRY_RUN = "dry_run"


@dataclass
class DownloadResult:
    hospital_id: str
    outcome: Outcome
    file_hash: str | None = None
    bytes_transferred: int = 0
    duration_s: float = 0.0
    snapshot: SnapshotRecord | None = None
    error: str | None = None
    final_path: str | None = None
    http_status: int | None = None
    response_headers: dict[str, str] | None = None
    hash_changed: bool | None = None
    compression: str | None = None
    content_format: str | None = None
    started_at: datetime | None = None
    ended_at: datetime | None = None
    stage_statuses: dict[str, str] | None = None
    stage_elapsed_s: dict[str, float] | None = None
    resolved_snapshot_id: str | None = None
    resolved_source_file_name: str | None = None

_CONTENT_TYPE_TO_EXT: dict[str, str] = {
    "text/csv": ".csv",
    "application/json": ".json",
    "application/zip": ".zip",
    "application/gzip": ".gz",
    "application/x-gzip": ".gz",
    "application/x-zip-compressed": ".zip",
}


def _filename_from_url(url: str) -> str:
    path = urlparse(url).path
    name = posixpath.basename(path)
    return name or "mrf_download"


def _filename_from_response(url: str, resp: httpx.Response) -> str:
    """Resolve the best filename from response headers, falling back to the URL path.

    Resolution order:
    1. Content-Disposition filename parameter
    2. URL path basename
    3. Content-Type → extension appended to the URL-derived stem
    """
    cd = resp.headers.get("content-disposition", "")
    if cd:
        match = re.search(r'filename[^;=\n]*=\s*["\']?([^;\n"\']+)', cd, re.IGNORECASE)
        if match:
            candidate = posixpath.basename(match.group(1).strip())
            if candidate:
                return candidate

    name = _filename_from_url(url)

    if "." not in posixpath.basename(name):
        ct = resp.headers.get("content-type", "").split(";")[0].strip().lower()
        ext = _CONTENT_TYPE_TO_EXT.get(ct, "")
        if ext:
            name = f"{name}{ext}"

    return name


def download_hospital(
    hospital: HospitalSource,
    storage: BronzeStorage,
    snapshots: SnapshotManager,
    client: httpx.Client,
    *,
    dry_run: bool = False,
    force: bool = False,
) -> DownloadResult:
    """Download a single hospital's MRF file.

    Returns a DownloadResult describing what happened.

    *force* re-downloads regardless of registry state but the hash comparison
    still determines whether a new snapshot is written.
    """
    hid = hospital.hospital_id
    url = str(hospital.mrf_source.url)
    t0 = time.monotonic()
    started_at = datetime.now(UTC)
    stage_statuses: dict[str, str] = {}
    stage_elapsed_s: dict[str, float] = {}
    response_headers: dict[str, str] = {}
    http_status: int | None = None
    safe_url = sanitize_url(url)
    log_url_event(
        logger,
        hid,
        url,
        "download_start",
        dry_run=dry_run,
        force=force,
    )
    logger.debug(
        "download_parameters",
        extra={
            "hospital_id": hid,
            "chunk_size": CHUNK_SIZE,
            "url": safe_url,
        },
    )

    if dry_run:
        logger.info("dry_run", extra={"hospital_id": hid, "url": safe_url})
        return DownloadResult(
            hospital_id=hid,
            outcome=Outcome.DRY_RUN,
            started_at=started_at,
            ended_at=datetime.now(UTC),
            stage_statuses=stage_statuses,
            stage_elapsed_s=stage_elapsed_s,
        )

    tmp = storage.temp_path(hid)
    sha = hashlib.sha256()
    nbytes = 0
    chunk_index = 0

    try:
        storage.makedirs(posixpath.dirname(tmp))

        filename = "mrf_download"
        transfer_started = time.monotonic()
        try:
            with client.stream("GET", url) as resp:
                http_status = resp.status_code
                response_headers = {
                    key: value
                    for key in ("content-length", "last-modified", "etag")
                    if (value := resp.headers.get(key)) is not None
                }
                resp.raise_for_status()
                filename = _filename_from_response(url, resp)
                logger.debug(
                    "filename_resolved",
                    extra={
                        "hospital_id": hid,
                        "filename": filename,
                        "content_type": resp.headers.get("content-type"),
                    },
                )
                with storage.open(tmp, "wb") as fh:
                    for chunk in resp.iter_raw():
                        fh.write(chunk)
                        sha.update(chunk)
                        nbytes += len(chunk)
                        chunk_index += 1
                        if chunk_index == 1 or chunk_index % 100 == 0:
                            log_download_chunk(
                                logger,
                                hid,
                                chunk_index=chunk_index,
                                chunk_bytes=len(chunk),
                                total_bytes=nbytes,
                            )
        except Exception:
            stage_statuses["request_transfer"] = "failed"
            raise
        else:
            stage_statuses["request_transfer"] = "success"
        finally:
            stage_elapsed_s["request_transfer"] = time.monotonic() - transfer_started

        file_hash = sha.hexdigest()
        duration = time.monotonic() - t0

        compare_started = time.monotonic()
        current_snapshot = snapshots.get_current_snapshot(hid)
        stage_statuses["hash_comparison"] = "success"
        stage_elapsed_s["hash_comparison"] = time.monotonic() - compare_started
        if current_snapshot is not None and current_snapshot.file_hash == file_hash:
            storage.rm(tmp)
            log_transfer_summary(
                logger,
                hid,
                nbytes=nbytes,
                duration_s=duration,
                file_hash=file_hash,
                event="unchanged",
            )
            return DownloadResult(
                hospital_id=hid,
                outcome=Outcome.UNCHANGED,
                file_hash=file_hash,
                bytes_transferred=nbytes,
                duration_s=duration,
                resolved_snapshot_id=current_snapshot.snapshot_id,
                resolved_source_file_name=current_snapshot.source_file_name,
                http_status=http_status,
                response_headers=response_headers,
                hash_changed=False,
                started_at=started_at,
                ended_at=datetime.now(UTC),
                stage_statuses=stage_statuses,
                stage_elapsed_s=stage_elapsed_s,
            )

        ingested_at = datetime.now(UTC)
        dest = storage.raw_path(
            hid, filename, ingested_at=ingested_at, file_hash=file_hash
        )
        commit_started = time.monotonic()
        storage.mv(tmp, dest)
        stage_statuses["raw_commit"] = "success"
        stage_elapsed_s["raw_commit"] = time.monotonic() - commit_started

        format_started = time.monotonic()
        fmt = detect_format(dest, storage.fs)
        stage_statuses["format_detection"] = "success"
        stage_elapsed_s["format_detection"] = time.monotonic() - format_started
        logger.debug(
            "format_detected",
            extra={
                "hospital_id": hid,
                "compression": fmt.compression.value,
                "content_format": fmt.content_format.value,
            },
        )

        snapshot_started = time.monotonic()
        snapshot = snapshots.write_snapshot(
            hospital_id=hid,
            source_url=url,
            source_file_name=filename,
            file_hash=file_hash,
            ingested_at=ingested_at,
        )
        stage_statuses["snapshot_write"] = "success"
        stage_elapsed_s["snapshot_write"] = time.monotonic() - snapshot_started

        log_transfer_summary(
            logger,
            hid,
            nbytes=nbytes,
            duration_s=duration,
            file_hash=file_hash,
            event="downloaded",
            snapshot_id=snapshot.snapshot_id,
            final_path=posixpath.basename(dest),
        )
        return DownloadResult(
            hospital_id=hid,
            outcome=Outcome.DOWNLOADED,
            file_hash=file_hash,
            bytes_transferred=nbytes,
            duration_s=duration,
            snapshot=snapshot,
            final_path=dest,
            http_status=http_status,
            response_headers=response_headers,
            hash_changed=True,
            compression=fmt.compression.value,
            content_format=fmt.content_format.value,
            started_at=started_at,
            ended_at=datetime.now(UTC),
            stage_statuses=stage_statuses,
            stage_elapsed_s=stage_elapsed_s,
        )

    except httpx.HTTPStatusError as exc:
        storage.rm(tmp)
        duration = time.monotonic() - t0
        error_msg = f"HTTP {exc.response.status_code} from {safe_url}"
        logger.error(
            "failed: %s",
            error_msg,
            extra={
                "hospital_id": hid,
                "url": safe_url,
                "status_code": exc.response.status_code,
                "bytes_transferred": nbytes,
                "duration_s": round(duration, 2),
            },
        )
        return DownloadResult(
            hospital_id=hid,
            outcome=Outcome.FAILED,
            bytes_transferred=nbytes,
            duration_s=duration,
            error=error_msg,
            http_status=exc.response.status_code,
            response_headers=response_headers,
            started_at=started_at,
            ended_at=datetime.now(UTC),
            stage_statuses=stage_statuses,
            stage_elapsed_s=stage_elapsed_s,
        )
    except httpx.RequestError as exc:
        storage.rm(tmp)
        duration = time.monotonic() - t0
        error_msg = f"{type(exc).__name__} requesting {safe_url}: {exc}"
        logger.error(
            "failed: %s",
            error_msg,
            extra={
                "hospital_id": hid,
                "url": safe_url,
                "bytes_transferred": nbytes,
                "duration_s": round(duration, 2),
            },
        )
        return DownloadResult(
            hospital_id=hid,
            outcome=Outcome.FAILED,
            bytes_transferred=nbytes,
            duration_s=duration,
            error=error_msg,
            http_status=http_status,
            response_headers=response_headers,
            started_at=started_at,
            ended_at=datetime.now(UTC),
            stage_statuses=stage_statuses,
            stage_elapsed_s=stage_elapsed_s,
        )
    except Exception as exc:
        storage.rm(tmp)
        duration = time.monotonic() - t0
        error_msg = f"{type(exc).__name__}: {exc}"
        logger.exception(
            "failed: unexpected error for %s — %s",
            hid,
            error_msg,
            extra={
                "hospital_id": hid,
                "url": safe_url,
                "bytes_transferred": nbytes,
                "duration_s": round(duration, 2),
            },
        )
        return DownloadResult(
            hospital_id=hid,
            outcome=Outcome.FAILED,
            bytes_transferred=nbytes,
            duration_s=duration,
            error=error_msg,
            http_status=http_status,
            response_headers=response_headers,
            started_at=started_at,
            ended_at=datetime.now(UTC),
            stage_statuses=stage_statuses,
            stage_elapsed_s=stage_elapsed_s,
        )


def download_all(
    hospitals: list[HospitalSource],
    storage: BronzeStorage,
    snapshots: SnapshotManager,
    cfg: DownloadConfig,
) -> list[DownloadResult]:
    """Iterate the provided hospital targets and download each MRF."""
    logger.info(
        "download_targets_start",
        extra={
            "hospital_count": len(hospitals),
            "dry_run": cfg.dry_run,
            "force": cfg.force,
        },
    )
    client = _build_client(cfg.client)
    results: list[DownloadResult] = []
    try:
        for hospital in hospitals:
            result = download_hospital(
                hospital,
                storage,
                snapshots,
                client,
                dry_run=cfg.dry_run,
                force=cfg.force,
            )
            results.append(result)
    finally:
        client.close()
    logger.info("download_targets_complete", extra={"hospital_count": len(results)})
    return results
