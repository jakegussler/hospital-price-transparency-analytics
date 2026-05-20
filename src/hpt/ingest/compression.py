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


def materialize_for_parse(
    path: str,
    fs: fsspec.AbstractFileSystem,
    compression: Compression,
    temp_base_path: str,
) -> str:
    """Copy compressed MRF content to a parser-ready temp file without touching raw.

    ``decompress_file`` is intentionally destructive for legacy download-time
    behavior. Ingest uses this helper so the raw publisher artifact remains
    byte-for-byte intact while parsers still receive a normal filesystem path.
    """
    if compression == Compression.GZIP:
        dest = _temp_path_with_suffix(temp_base_path, _gzip_output_suffix(path))
        _copy_gzip(path, dest, fs)
        return dest
    if compression == Compression.ZIP:
        return _materialize_zip_member(path, fs, temp_base_path)
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

    _copy_gzip(src, dest, fs)

    if not fs.exists(dest):
        raise RuntimeError(f"Decompressed file not found at expected path: {dest}")

    fs.rm(src)
    logger.info("decompressed gzip %s → %s", src, dest)
    return dest


def _copy_gzip(src: str, dest: str, fs: fsspec.AbstractFileSystem) -> None:
    """Write the decompressed bytes from gzip *src* to *dest*."""
    fs.makedirs(posixpath.dirname(dest), exist_ok=True)
    with fs.open(src, "rb") as compressed:
        with gzip.GzipFile(fileobj=compressed) as gz:
            with fs.open(dest, "wb") as out:
                while True:
                    chunk = gz.read(_CHUNK_SIZE)
                    if not chunk:
                        break
                    out.write(chunk)


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


def _materialize_zip_member(
    src: str,
    fs: fsspec.AbstractFileSystem,
    temp_base_path: str,
) -> str:
    """Extract the selected MRF member from *src* into a parser-ready temp file."""
    with fs.open(src, "rb") as f:
        data = f.read()

    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        members = [m for m in zf.namelist() if not m.endswith("/")]
        if not members:
            raise ValueError(f"Zip archive contains no files: {src}")

        target = _pick_mrf_member(members, src)
        dest = _temp_path_with_suffix(temp_base_path, _member_output_suffix(target))
        fs.makedirs(posixpath.dirname(dest), exist_ok=True)
        with zf.open(target, "r") as member:
            if target.lower().endswith(".gz"):
                with gzip.GzipFile(fileobj=member) as gz:
                    with fs.open(dest, "wb") as out:
                        while True:
                            chunk = gz.read(_CHUNK_SIZE)
                            if not chunk:
                                break
                            out.write(chunk)
            else:
                with fs.open(dest, "wb") as out:
                    while True:
                        chunk = member.read(_CHUNK_SIZE)
                        if not chunk:
                            break
                        out.write(chunk)

    if not fs.exists(dest):
        raise RuntimeError(f"Materialized ZIP member not found at expected path: {dest}")
    logger.info("materialized zip member %s from %s → %s", target, src, dest)
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


def _gzip_output_suffix(path: str) -> str:
    basename = posixpath.basename(path).lower()
    if basename.endswith(".gz"):
        basename = basename[:-3]
    return _suffix_from_name(basename)


def _member_output_suffix(member_name: str) -> str:
    basename = posixpath.basename(member_name).lower()
    if basename.endswith(".gz"):
        basename = basename[:-3]
    return _suffix_from_name(basename)


def _suffix_from_name(name: str) -> str:
    for suffix in (".json", ".csv", ".ndjson"):
        if name.endswith(suffix):
            return suffix
    return ""


def _temp_path_with_suffix(temp_base_path: str, suffix: str) -> str:
    if suffix and not temp_base_path.lower().endswith(suffix):
        return f"{temp_base_path}{suffix}"
    return temp_base_path
