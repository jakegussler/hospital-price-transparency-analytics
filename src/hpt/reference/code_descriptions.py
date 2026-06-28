"""Parse and persist green-light code-description reference data.

The first source is the CMS MS-DRG list (IPPS Final Rule Table 5): public-domain,
small, and the highest-signal source for making inpatient charges human-readable.
The loader is source-faithful — it captures the published code, title, grouper
context, and relative weight, and stamps each row with the ``code_edition`` and
provenance so downstream as-of joins can align an MRF snapshot's vintage with the
right edition.
"""

from __future__ import annotations

import datetime as dt
import logging
import re
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from hpt.reference.config import ReferenceStorageConfig
from hpt.reference.download import ensure_reference_member
from hpt.reference.registry import ReferenceSource, load_reference_sources
from hpt.reference.schema import pyarrow_fields

logger = logging.getLogger(__name__)

# Common provenance/lineage columns carried by every reference table.
_LINEAGE_FIELDS = [
    ("code_type", pa.string()),
    ("code", pa.string()),
    ("description", pa.string()),
    ("code_edition", pa.string()),
    ("effective_start", pa.date32()),
    ("effective_end", pa.date32()),
    ("source", pa.string()),
    ("license", pa.string()),
    ("source_url", pa.string()),
    ("retrieved_at", pa.timestamp("us", tz="UTC")),
]

REFERENCE_SOURCES: dict[str, ReferenceSource] = load_reference_sources()


def _to_float(value: str) -> float | None:
    try:
        return float(value.strip().replace(",", ""))
    except (ValueError, AttributeError):
        return None


def parse_ms_drg_table5(text: str) -> list[dict]:
    """Parse the tab-delimited IPPS Table 5 into per-MS-DRG description rows.

    The file carries a two-line title block, then a header row beginning with
    ``MS-DRG``, then one tab-delimited row per DRG. Only rows whose first field
    is a 1-3 digit DRG number are kept; codes are zero-padded to the 3-digit
    ``match_code`` width Silver uses for the DRG family.
    """
    lines = text.splitlines()
    header_idx = next(
        (i for i, line in enumerate(lines) if line.lstrip('"').strip().startswith("MS-DRG")),
        None,
    )
    if header_idx is None:
        raise ValueError("Could not locate the MS-DRG header row in Table 5 text")

    rows: list[dict] = []
    for line in lines[header_idx + 1 :]:
        if not line.strip():
            continue
        parts = line.split("\t")
        if len(parts) < 6:
            continue
        code = parts[0].strip().strip('"')
        if not re.fullmatch(r"\d{1,3}", code):
            continue
        title = parts[5].strip().strip('"').replace("\x97", "-").replace("\x96", "-")
        rows.append(
            {
                "code": code.zfill(3),
                "description": title,
                "post_acute_drg": parts[1].strip().lower() == "yes",
                "special_pay_drg": parts[2].strip().lower() == "yes",
                "mdc": parts[3].strip() or None,
                "drg_type": parts[4].strip() or None,
                "relative_weight_uncapped": _to_float(parts[6]) if len(parts) > 6 else None,
                "relative_weight": _to_float(parts[7]) if len(parts) > 7 else None,
                "geometric_mean_los": _to_float(parts[8]) if len(parts) > 8 else None,
                "arithmetic_mean_los": _to_float(parts[9]) if len(parts) > 9 else None,
            }
        )
    if not rows:
        raise ValueError("Parsed zero MS-DRG rows from Table 5 text")
    return rows


_PARSERS = {"ms_drg_table5": parse_ms_drg_table5}


def _build_table(source: ReferenceSource, rows: list[dict], retrieved_at: dt.datetime) -> pa.Table:
    source_fields = pyarrow_fields(source.field_types)
    schema = pa.schema(_LINEAGE_FIELDS + source_fields)
    n = len(rows)
    columns: dict[str, list] = {
        "code_type": [source.code_type] * n,
        "code": [r["code"] for r in rows],
        "description": [r["description"] for r in rows],
        "code_edition": [source.code_edition] * n,
        "effective_start": [source.effective_start] * n,
        "effective_end": [source.effective_end] * n,
        "source": [source.source] * n,
        "license": [source.license] * n,
        "source_url": [source.url] * n,
        "retrieved_at": [retrieved_at] * n,
    }
    for fname, _ in source_fields:
        columns[fname] = [r.get(fname) for r in rows]
    return pa.table(columns, schema=schema)


def load_reference(
    source_name: str,
    *,
    reference_root: Path | None = None,
    raw_root: Path | None = None,
    retrieved_at: dt.datetime | None = None,
) -> Path:
    """Download, parse, and write one reference source to Bronze Parquet.

    Returns the path of the written Parquet part. Idempotent: re-running with the
    same release overwrites the partition in place.
    """
    if source_name not in REFERENCE_SOURCES:
        raise KeyError(f"Unknown reference source: {source_name!r}")
    source = REFERENCE_SOURCES[source_name]
    storage = ReferenceStorageConfig.from_env(reference_root=reference_root, raw_root=raw_root)
    retrieved_at = retrieved_at or dt.datetime.now(dt.UTC)

    member_path = ensure_reference_member(source, storage.raw_root)
    text = member_path.read_text(encoding="latin-1")
    try:
        parser = _PARSERS[source.parser]
    except KeyError as exc:
        raise KeyError(
            f"Unknown parser {source.parser!r} for reference source {source_name!r}"
        ) from exc
    rows = parser(text)
    table = _build_table(source, rows, retrieved_at)

    out_dir = storage.reference_root / source.name / f"release_date={source.release_date}"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "part-000.parquet"
    pq.write_table(table, out_path)
    logger.info(
        "reference_written source=%s rows=%d path=%s edition=%s",
        source_name,
        len(rows),
        out_path,
        source.code_edition,
    )
    return out_path
