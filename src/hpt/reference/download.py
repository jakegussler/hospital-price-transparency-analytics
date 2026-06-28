"""Download and unpack external reference-data artifacts."""

from __future__ import annotations

import io
import logging
import zipfile
from pathlib import Path

import httpx

from hpt.reference.registry import ReferenceSource

logger = logging.getLogger(__name__)


def ensure_reference_member(source: ReferenceSource, raw_root: Path) -> Path:
    """Download and extract a source archive when the target member is absent."""
    raw_dir = raw_root / source.name / source.release_date
    raw_dir.mkdir(parents=True, exist_ok=True)
    member_path = raw_dir / source.member
    if member_path.exists():
        logger.info("reference_raw_cached path=%s", member_path)
        return member_path

    logger.info("reference_download_start source=%s url=%s", source.key, source.url)
    headers = {"User-Agent": "hpt-pipeline/0.1 (+reference-loader)"}
    with httpx.Client(follow_redirects=True, timeout=120.0, headers=headers) as client:
        resp = client.get(source.url)
        resp.raise_for_status()

    (raw_dir / Path(source.url).name).write_bytes(resp.content)
    with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
        zf.extract(source.member, raw_dir)

    logger.info(
        "reference_download_complete source=%s path=%s bytes=%d",
        source.key,
        member_path,
        len(resp.content),
    )
    return member_path
