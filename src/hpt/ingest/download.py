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

from hpt.ingest.config import IngestConfig
from hpt.ingest.snapshot import SnapshotManager, SnapshotRecord
from hpt.ingest.storage import BronzeStorage
from hpt.registry.models import HospitalSource

logger = logging.getLogger(__name__)

CHUNK_SIZE = 256 * 1024  # 256 KiB


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

    if dry_run:
        logger.info("dry_run", extra={"hospital_id": hid, "url": url})
        return DownloadResult(hospital_id=hid, outcome=Outcome.DRY_RUN)

    tmp = storage.temp_path(hid)
    sha = hashlib.sha256()
    nbytes = 0

    try:
        storage.makedirs(posixpath.dirname(tmp))

        filename = "mrf_download"
        with client.stream("GET", url) as resp:
            resp.raise_for_status()
            filename = _filename_from_response(url, resp)
            with storage.open(tmp, "wb") as fh:
                for chunk in resp.iter_raw():
                    fh.write(chunk)
                    sha.update(chunk)
                    nbytes += len(chunk)

        file_hash = sha.hexdigest()
        duration = time.monotonic() - t0

        current_hash = snapshots.current_hash(hid)
        if current_hash == file_hash:
            storage.rm(tmp)
            logger.info(
                "unchanged",
                extra={"hospital_id": hid, "file_hash": file_hash, "bytes": nbytes},
            )
            return DownloadResult(
                hospital_id=hid,
                outcome=Outcome.UNCHANGED,
                file_hash=file_hash,
                bytes_transferred=nbytes,
                duration_s=duration,
            )

        ingested_at = datetime.now(UTC)
        dest = storage.raw_path(
            hid, filename, ingested_at=ingested_at, file_hash=file_hash
        )
        storage.mv(tmp, dest)

        snapshot = snapshots.write_snapshot(
            hospital_id=hid,
            source_url=url,
            source_file_name=filename,
            file_hash=file_hash,
            ingested_at=ingested_at,
        )

        logger.info(
            "downloaded",
            extra={
                "hospital_id": hid,
                "file_hash": file_hash,
                "bytes": nbytes,
                "duration_s": round(duration, 2),
                "snapshot_id": snapshot.snapshot_id,
            },
        )
        return DownloadResult(
            hospital_id=hid,
            outcome=Outcome.DOWNLOADED,
            file_hash=file_hash,
            bytes_transferred=nbytes,
            duration_s=duration,
            snapshot=snapshot,
        )

    except httpx.HTTPStatusError as exc:
        storage.rm(tmp)
        duration = time.monotonic() - t0
        error_msg = f"HTTP {exc.response.status_code} from {url}"
        logger.error(
            "failed: %s",
            error_msg,
            extra={
                "hospital_id": hid,
                "url": url,
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
        )
    except httpx.RequestError as exc:
        storage.rm(tmp)
        duration = time.monotonic() - t0
        error_msg = f"{type(exc).__name__} requesting {url}: {exc}"
        logger.error(
            "failed: %s",
            error_msg,
            extra={
                "hospital_id": hid,
                "url": url,
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
                "url": url,
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
        )


def download_all(
    hospitals: list[HospitalSource],
    storage: BronzeStorage,
    snapshots: SnapshotManager,
    cfg: IngestConfig,
    *,
    dry_run: bool = False,
    force: bool = False,
) -> list[DownloadResult]:
    """Iterate the full registry and download each hospital's MRF."""
    client = _build_client(cfg)
    results: list[DownloadResult] = []
    try:
        for hospital in hospitals:
            result = download_hospital(
                hospital, storage, snapshots, client, dry_run=dry_run, force=force
            )
            results.append(result)
    finally:
        client.close()
    return results
