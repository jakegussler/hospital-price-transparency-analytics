"""Sniff the HPT schema variant and version of a downloaded MRF file.

Given a path to a (possibly gzipped) MRF, this module identifies the layout
(JSON, CSV "tall", or CSV "wide") and extracts the CMS template version string
so downstream parsers can be dispatched correctly.

The sniffer reads only what it needs:

* For JSON we stream with :mod:`ijson` until the top-level ``version`` key is
  found — large files are never loaded into memory.
* For CSV we parse only the first three rows, which contain the meta-header,
  meta-values (including the version), and the data-row column headers.
"""

from __future__ import annotations

import csv
import gzip
import io
import logging
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from enum import Enum
from typing import IO

import fsspec
import ijson

from hpt.ingest.detect import Compression, ContentFormat, FormatInfo, detect_format
from hpt.logging.log_helpers import log_schema_sniff

logger = logging.getLogger(__name__)


class Layout(str, Enum):
    """High-level MRF layout family."""

    JSON = "json"
    CSV_TALL = "csv_tall"
    CSV_WIDE = "csv_wide"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class SchemaInfo:
    """Result of sniffing an MRF file."""

    layout: Layout
    version: str | None


def sniff_schema(
    path: str,
    fs: fsspec.AbstractFileSystem,
    format_info: FormatInfo | None = None,
) -> SchemaInfo:
    """Identify the MRF layout and version for *path*.

    Parameters
    ----------
    path:
        Path to the MRF on the given filesystem. May be gzipped.
    fs:
        The fsspec filesystem *path* lives on.
    format_info:
        Optional pre-computed :class:`FormatInfo`. When omitted, the compression
        and content format are sniffed from the file header via
        :func:`hpt.ingest.detect.detect_format`.
    """
    if format_info is None:
        format_info = detect_format(path, fs)

    logger.debug(
        "sniff_schema_start",
        extra={
            "path": path,
            "compression": format_info.compression.value,
            "content_format": format_info.content_format.value,
        },
    )

    if format_info.content_format == ContentFormat.JSON:
        info = _sniff_json(path, fs, format_info.compression)
        log_schema_sniff(
            logger,
            path_basename=path.rsplit("/", 1)[-1],
            layout=info.layout.value,
            version=info.version,
            compression=format_info.compression.value,
            content_format=format_info.content_format.value,
        )
        return info
    if format_info.content_format == ContentFormat.CSV:
        info = _sniff_csv(path, fs, format_info.compression)
        log_schema_sniff(
            logger,
            path_basename=path.rsplit("/", 1)[-1],
            layout=info.layout.value,
            version=info.version,
            compression=format_info.compression.value,
            content_format=format_info.content_format.value,
        )
        return info

    logger.warning("Unknown content format for %s; cannot sniff schema", path)
    return SchemaInfo(layout=Layout.UNKNOWN, version=None)


# ---------------------------------------------------------------------------
# JSON
# ---------------------------------------------------------------------------


# Prefixes that indicate ijson has moved past the top-level header block into
# the bulk standard-charge payload. If we reach one of these without finding a
# ``version`` key, further scanning won't help.
_JSON_BULK_PREFIXES = frozenset(
    {"standard_charge_information", "standard_charge_information.item"}
)


def _sniff_json(
    path: str, fs: fsspec.AbstractFileSystem, compression: Compression
) -> SchemaInfo:
    """Stream the JSON MRF with ijson to locate the top-level ``version``."""
    try:
        with _open_stream(path, fs, compression) as stream:
            for prefix, event, value in ijson.parse(stream):
                if prefix == "version" and event in ("string", "number"):
                    logger.debug(
                        "json_version_found",
                        extra={"path": path, "version_prefix": prefix},
                    )
                    return SchemaInfo(layout=Layout.JSON, version=str(value))
                if prefix in _JSON_BULK_PREFIXES:
                    logger.debug(
                        "json_version_not_found_before_bulk",
                        extra={"path": path, "bulk_prefix": prefix},
                    )
                    break
    except ijson.JSONError as exc:
        logger.warning("ijson failed to parse %s: %s", path, exc)

    return SchemaInfo(layout=Layout.JSON, version=None)


# ---------------------------------------------------------------------------
# CSV
# ---------------------------------------------------------------------------


def _sniff_csv(
    path: str, fs: fsspec.AbstractFileSystem, compression: Compression
) -> SchemaInfo:
    """Parse the first three rows of the CSV MRF to infer layout and version."""
    with _open_stream(path, fs, compression) as stream:
        text = io.TextIOWrapper(stream, encoding="utf-8-sig", newline="")
        reader = csv.reader(text)
        try:
            meta_headers = next(reader)
            meta_values = next(reader)
            data_headers = next(reader)
        except StopIteration:
            logger.warning("CSV %s has fewer than 3 rows; cannot sniff schema", path)
            return SchemaInfo(layout=Layout.UNKNOWN, version=None)

    version = _extract_csv_version(meta_headers, meta_values)
    layout = _classify_csv_layout(data_headers)
    logger.debug(
        "csv_sniff_details",
        extra={
            "path": path,
            "meta_header_count": len(meta_headers),
            "data_header_count": len(data_headers),
            "layout": layout.value,
        },
    )
    return SchemaInfo(layout=layout, version=version)


def _extract_csv_version(headers: list[str], values: list[str]) -> str | None:
    """Return the value paired with the ``version`` meta-header, if present."""
    for idx, header in enumerate(headers):
        if header.strip().lower() == "version":
            if idx >= len(values):
                return None
            value = values[idx].strip()
            return value or None
    return None


def _classify_csv_layout(data_headers: list[str]) -> Layout:
    """Distinguish CSV tall from wide based on the row-3 data headers.

    Tall files always expose standalone ``payer_name`` / ``plan_name`` columns.
    Wide files never do — payer/plan identifiers are embedded into composite
    column names such as ``standard_charge|<payer>|<plan>|negotiated_dollar``.
    """
    normalized = {h.strip().lower() for h in data_headers if h.strip()}
    if "payer_name" in normalized:
        return Layout.CSV_TALL

    # Wide signature: a standard_charge column whose header carries extra
    # pipe-separated segments for payer and plan (e.g. 4 segments total).
    for header in data_headers:
        lowered = header.strip().lower()
        if lowered.startswith("standard_charge|") and lowered.count("|") >= 3:
            return Layout.CSV_WIDE

    return Layout.UNKNOWN


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@contextmanager
def _open_stream(
    path: str, fs: fsspec.AbstractFileSystem, compression: Compression
) -> Iterator[IO[bytes]]:
    """Yield a binary stream for *path*, transparently decompressing gzip."""
    if compression == Compression.ZIP:
        raise ValueError(
            "Zip archives must be extracted before sniffing; received a .zip path: "
            f"{path!r}"
        )

    raw = fs.open(path, "rb")
    try:
        if compression == Compression.GZIP:
            gz = gzip.GzipFile(fileobj=raw)
            try:
                yield gz
            finally:
                gz.close()
        else:
            yield raw
    finally:
        raw.close()
