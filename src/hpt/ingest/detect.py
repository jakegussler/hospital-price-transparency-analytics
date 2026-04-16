"""Detect file format and compression for downloaded MRF files."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

import fsspec

_MAGIC_GZIP = b"\x1f\x8b"
_MAGIC_ZIP = b"\x50\x4b\x03\x04"


class Compression(str, Enum):
    NONE = "none"
    GZIP = "gzip"
    ZIP = "zip"


class ContentFormat(str, Enum):
    JSON = "json"
    CSV = "csv"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class FormatInfo:
    compression: Compression
    content_format: ContentFormat


def detect_format(path: str, fs: fsspec.AbstractFileSystem) -> FormatInfo:
    """Detect the compression and content format of *path* using magic bytes.

    Reads only the first 8 bytes so it works efficiently on large files.
    Content format detection applies to the uncompressed content — for
    compressed files it falls back to extension-based sniffing.
    """
    with fs.open(path, "rb") as fh:
        header = fh.read(8)

    if header[:2] == _MAGIC_GZIP:
        compression = Compression.GZIP
    elif header[:4] == _MAGIC_ZIP:
        compression = Compression.ZIP
    else:
        compression = Compression.NONE

    content_format = _sniff_content_format(header, path, compression)
    return FormatInfo(compression=compression, content_format=content_format)


def _sniff_content_format(
    header: bytes, path: str, compression: Compression
) -> ContentFormat:
    """Infer content format from raw header bytes, falling back to extension."""
    if compression == Compression.NONE:
        stripped = header.lstrip()
        if stripped and stripped[0:1] in (b"{", b"["):
            return ContentFormat.JSON

    lower = path.lower()
    if lower.endswith(".json") or lower.endswith(".json.gz"):
        return ContentFormat.JSON
    if lower.endswith(".csv") or lower.endswith(".csv.gz"):
        return ContentFormat.CSV

    return ContentFormat.UNKNOWN
