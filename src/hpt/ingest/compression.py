"""Decompress MRF files from gzip or zip archives."""

from __future__ import annotations

import gzip
import io
import logging
import posixpath
import zipfile

import fsspec

from hpt.ingest.detect import Compression

logger = logging.getLogger(__name__)

_CHUNK_SIZE = 256 * 1024  # 256 KiB

# Extensions that identify a likely MRF content file inside a zip archive.
_MRF_EXTENSIONS = (".json", ".csv", ".json.gz", ".ndjson")


def decompress_file(
    path: str,
    fs: fsspec.AbstractFileSystem,
    compression: Compression,
) -> str:
    """Decompress the file at *path*, remove the original, and return the new path.

    The decompressed file is written into the same directory as *path*.

    Raises
    ------
    ValueError
        If the archive is malformed, empty, or contains ambiguous content.
    """
    if compression == Compression.GZIP:
        return _decompress_gzip(path, fs)
    if compression == Compression.ZIP:
        return _decompress_zip(path, fs)
    raise ValueError(f"Unsupported compression type: {compression!r}")


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


def _decompress_gzip(src: str, fs: fsspec.AbstractFileSystem) -> str:
    """Decompress a gzip file, returning the path of the extracted file."""
    basename = posixpath.basename(src)
    # Strip the .gz suffix, preserving any inner extension (e.g. foo.json.gz → foo.json).
    stem = basename[:-3] if basename.lower().endswith(".gz") else basename
    dest = posixpath.join(posixpath.dirname(src), stem)

    with fs.open(src, "rb") as compressed:
        with gzip.GzipFile(fileobj=compressed) as gz:
            with fs.open(dest, "wb") as out:
                while True:
                    chunk = gz.read(_CHUNK_SIZE)
                    if not chunk:
                        break
                    out.write(chunk)

    if not fs.exists(dest):
        raise RuntimeError(f"Decompressed file not found at expected path: {dest}")

    fs.rm(src)
    logger.info("decompressed gzip %s → %s", src, dest)
    return dest


def _decompress_zip(src: str, fs: fsspec.AbstractFileSystem) -> str:
    """Extract a zip archive, returning the path of the extracted MRF file."""
    with fs.open(src, "rb") as f:
        data = f.read()

    dest_dir = posixpath.dirname(src)

    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        members = [m for m in zf.namelist() if not m.endswith("/")]
        if not members:
            raise ValueError(f"Zip archive contains no files: {src}")

        target = _pick_mrf_member(members, src)
        extracted_name = posixpath.basename(target)
        dest = posixpath.join(dest_dir, extracted_name)

        with fs.open(dest, "wb") as out:
            out.write(zf.read(target))

    if not fs.exists(dest):
        raise RuntimeError(f"Extracted file not found at expected path: {dest}")

    fs.rm(src)
    logger.info("decompressed zip %s → %s", src, dest)
    return dest


def _pick_mrf_member(members: list[str], archive_path: str) -> str:
    """Return the single member to extract from *members*.

    If there is only one file, it is always chosen. When there are multiple
    files, the first member whose extension matches a known MRF format is
    selected. Raises ``ValueError`` when the result is ambiguous.
    """
    if len(members) == 1:
        return members[0]

    candidates = [m for m in members if m.lower().endswith(_MRF_EXTENSIONS)]
    if len(candidates) == 1:
        return candidates[0]

    raise ValueError(
        f"Zip archive {archive_path!r} contains {len(members)} members and "
        f"{len(candidates)} MRF candidates — cannot determine which to extract. "
        f"Members: {members}"
    )
