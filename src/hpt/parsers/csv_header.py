"""Shared CSV header and column-mapping helpers for Tall/Wide parsers."""

from __future__ import annotations

import codecs
import csv
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, TextIO

import polars as pl

from hpt.parsers.helpers import _df, _iso
from hpt.parsers.schemas import BRONZE_SCHEMAS

ATTESTATION_PREFIX = "To the best of its knowledge and belief"
CSV_ENCODINGS = ("utf-8-sig", "cp1252")
_ENCODING_DETECT_CHUNK_SIZE = 256 * 1024

TALL_COLUMN_MAP: dict[str, str] = {
    "description": "description",
    "setting": "setting",
    "billing_class": "billing_class",
    "drug_unit_of_measurement": "drug_unit_of_measurement",
    "drug_type_of_measurement": "drug_type_of_measurement",
    "standard_charge|gross": "standard_charge_gross",
    "standard_charge|discounted_cash": "standard_charge_discounted_cash",
    "standard_charge|min": "standard_charge_min",
    "standard_charge|max": "standard_charge_max",
    "standard_charge|negotiated_dollar": "standard_charge_negotiated_dollar",
    "standard_charge|negotiated_percentage": "standard_charge_negotiated_percentage",
    "standard_charge|negotiated_algorithm": "standard_charge_negotiated_algorithm",
    "standard_charge|methodology": "methodology",
    "modifiers": "modifiers",
    "payer_name": "payer_name",
    "plan_name": "plan_name",
    "additional_generic_notes": "additional_generic_notes",
    "additional_payer_notes": "additional_payer_notes",
    "median_amount": "median_amount",
    "10th_percentile": "tenth_percentile",
    "90th_percentile": "ninetieth_percentile",
    "count": "count",
}

_WIDE_STANDARD_CHARGE_SUFFIX_MAP: dict[str, str] = {
    "negotiated_dollar": "standard_charge_negotiated_dollar",
    "negotiated_percentage": "standard_charge_negotiated_percentage",
    "negotiated_algorithm": "standard_charge_negotiated_algorithm",
    "methodology": "methodology",
    "median_amount": "median_amount",
    "10th_percentile": "tenth_percentile",
    "90th_percentile": "ninetieth_percentile",
    "count": "count",
}


@dataclass
class PayerColumnGroup:
    payer_name: str
    plan_name: str
    columns: dict[str, int] = field(default_factory=dict)


@dataclass
class WideColumnCatalog:
    fixed_columns: dict[str, int]
    code_columns: dict[str, int]
    payer_groups: list[PayerColumnGroup]
    additional_payer_notes_cols: dict[tuple[str, str], int]


def parse_csv_header(
    file_path: Path,
    snapshot_meta: dict[str, Any],
) -> tuple[
    dict[str, Any],
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
]:
    """Parse rows 1-2 and return snapshot + child-table rows."""
    with open_csv_text(file_path) as f:
        reader = csv.reader(f)
        try:
            row1 = next(reader)
            row2 = next(reader)
        except StopIteration as exc:
            msg = f"CSV file has fewer than 2 rows: {file_path}"
            raise ValueError(msg) from exc

    keys = [k.strip() for k in row1]
    values = [v.strip() for v in row2]
    header = {
        key: (values[i] if i < len(values) else "")
        for i, key in enumerate(keys)
    }

    snapshot_record = build_snapshot_record(header, snapshot_meta)
    location_rows = _build_location_rows(header, snapshot_meta["snapshot_id"])
    npi_rows = _build_npi_rows(header, snapshot_meta["snapshot_id"])
    provision_rows = _build_general_contract_provision_rows(
        header, snapshot_meta["snapshot_id"]
    )
    return snapshot_record, location_rows, npi_rows, provision_rows


def get_charge_reader(file_path: Path) -> tuple[csv.reader, list[str], TextIO]:
    """Return a csv.reader positioned at row 4 and the row-3 headers."""
    f = open_csv_text(file_path)
    reader = csv.reader(f)
    try:
        next(reader)  # row 1
        next(reader)  # row 2
        charge_headers = next(reader)  # row 3
    except StopIteration as exc:
        f.close()
        msg = f"CSV file has fewer than 3 rows: {file_path}"
        raise ValueError(msg) from exc
    return reader, charge_headers, f


def open_csv_text(file_path: Path) -> TextIO:
    """Open a publisher CSV with a conservative UTF-8 then CP-1252 fallback."""
    return open(file_path, newline="", encoding=detect_csv_encoding(file_path))


def detect_csv_encoding(file_path: Path) -> str:
    """Return the encoding to use for CSV text reads.

    Most CMS files are UTF-8, but some publisher CSVs contain Windows-1252
    bytes deep in the charge rows. We validate the full stream before returning
    a reader so decoding does not fail halfway through ingestion.
    """
    stat = file_path.stat()
    return _detect_csv_encoding_cached(
        str(file_path),
        stat.st_mtime_ns,
        stat.st_size,
    )


@lru_cache(maxsize=128)
def _detect_csv_encoding_cached(path: str, mtime_ns: int, size: int) -> str:
    del mtime_ns, size  # Included in the cache key to invalidate changed files.
    decoder = codecs.getincrementaldecoder("utf-8-sig")()
    try:
        with open(path, "rb") as f:
            while chunk := f.read(_ENCODING_DETECT_CHUNK_SIZE):
                decoder.decode(chunk)
            decoder.decode(b"", final=True)
    except UnicodeDecodeError:
        return "cp1252"
    return "utf-8-sig"


def build_snapshot_record(
    header: dict[str, str],
    snapshot_meta: dict[str, Any],
) -> dict[str, Any]:
    """Merge pipeline metadata with CSV-derived row-1/row-2 fields."""
    attestation = _extract_attestation(header)
    license_info = _extract_license_fields(header)
    return {
        "snapshot_id": snapshot_meta["snapshot_id"],
        "hospital_id": snapshot_meta.get("hospital_id"),
        "reported_hospital_name": _none_if_blank(header.get("hospital_name")),
        "source_url": snapshot_meta.get("source_url"),
        "source_file_name": snapshot_meta.get("source_file_name"),
        "source_format": snapshot_meta.get("source_format"),
        "file_hash": snapshot_meta.get("file_hash"),
        "ingested_at": _iso(snapshot_meta.get("ingested_at")),
        "published_last_updated_on": _none_if_blank(header.get("last_updated_on")),
        "schema_version": _none_if_blank(header.get("version"))
        or snapshot_meta.get("schema_version"),
        "is_current_snapshot": bool(snapshot_meta.get("is_current_snapshot", True)),
        "valid_from": _iso(snapshot_meta.get("valid_from")),
        "valid_to": _iso(snapshot_meta.get("valid_to")),
        "attestation": attestation["attestation"],
        "confirm_attestation": attestation["confirm_attestation"],
        "attester_name": _none_if_blank(header.get("attester_name")),
        "reported_state": license_info["reported_state"],
        "license_number": license_info["license_number"],
    }


def build_header_batch(
    snapshot_record: dict[str, Any],
    location_rows: list[dict[str, Any]],
    npi_rows: list[dict[str, Any]],
    provision_rows: list[dict[str, Any]] | None = None,
) -> dict[str, pl.DataFrame]:
    """Build the first parser batch containing shared Bronze tables."""
    return {
        "hospital_mrf_snapshots": _df(
            [snapshot_record], BRONZE_SCHEMAS["hospital_mrf_snapshots"]
        ),
        "hospital_locations": _df(
            location_rows, BRONZE_SCHEMAS["hospital_locations"]
        ),
        "type2_npi": _df(npi_rows, BRONZE_SCHEMAS["type2_npi"]),
        "general_contract_provisions": _df(
            provision_rows or [],
            BRONZE_SCHEMAS["general_contract_provisions"],
        ),
    }


def discover_code_columns(headers: list[str]) -> tuple[int, dict[str, int]]:
    """Return max code ordinal and mapping of code column names to indices."""
    code_map: dict[str, int] = {}
    max_code = 0
    for idx, header in enumerate(headers):
        normalized = header.strip().lower()
        parts = normalized.split("|")
        if len(parts) == 2 and parts[0] == "code" and parts[1].isdigit():
            ordinal = int(parts[1])
            if ordinal > 0:
                code_map[f"code_{ordinal}"] = idx
                max_code = max(max_code, ordinal)
            continue
        if (
            len(parts) == 3
            and parts[0] == "code"
            and parts[1].isdigit()
            and parts[2] == "type"
        ):
            ordinal = int(parts[1])
            if ordinal > 0:
                code_map[f"code_{ordinal}_type"] = idx
                max_code = max(max_code, ordinal)
    return max_code, code_map


def build_tall_column_map(headers: list[str]) -> tuple[int, dict[str, int]]:
    """Build output-column -> source-index map for CSV Tall data rows."""
    max_codes, code_columns = discover_code_columns(headers)
    mapping = dict(code_columns)
    for idx, header in enumerate(headers):
        normalized = header.strip().lower()
        mapped = TALL_COLUMN_MAP.get(normalized)
        if mapped is not None:
            mapping[mapped] = idx
    return max_codes, mapping


def build_wide_column_catalog(headers: list[str]) -> tuple[int, WideColumnCatalog]:
    """Build fixed and payer column catalog for Wide unpivot parsing."""
    max_codes, code_columns = discover_code_columns(headers)
    fixed_columns: dict[str, int] = dict(code_columns)
    payer_groups: dict[tuple[str, str], PayerColumnGroup] = {}
    additional_notes_cols: dict[tuple[str, str], int] = {}

    for idx, header in enumerate(headers):
        raw = header.strip()
        normalized = raw.lower()
        if normalized in TALL_COLUMN_MAP:
            mapped = TALL_COLUMN_MAP[normalized]
            if mapped in {"payer_name", "plan_name"}:
                continue
            fixed_columns[mapped] = idx
            continue

        parts = raw.split("|")
        if len(parts) == 4 and parts[0].lower() == "standard_charge":
            payer_name = parts[1].strip()
            plan_name = parts[2].strip()
            suffix = parts[3].strip().lower()
            bronze_col = _WIDE_STANDARD_CHARGE_SUFFIX_MAP.get(suffix)
            if bronze_col is None:
                continue
            key = (payer_name, plan_name)
            group = payer_groups.setdefault(
                key, PayerColumnGroup(payer_name=payer_name, plan_name=plan_name)
            )
            group.columns[bronze_col] = idx
            continue

        if len(parts) == 3 and parts[0].lower() == "additional_payer_notes":
            payer_name = parts[1].strip()
            plan_name = parts[2].strip()
            additional_notes_cols[(payer_name, plan_name)] = idx

    catalog = WideColumnCatalog(
        fixed_columns=fixed_columns,
        code_columns=code_columns,
        payer_groups=list(payer_groups.values()),
        additional_payer_notes_cols=additional_notes_cols,
    )
    return max_codes, catalog


def _extract_attestation(header: dict[str, str]) -> dict[str, str | None]:
    for key, value in header.items():
        stripped = key.strip()
        if stripped.startswith(ATTESTATION_PREFIX):
            return {
                "attestation": stripped,
                "confirm_attestation": _none_if_blank(value),
            }
    return {"attestation": None, "confirm_attestation": None}


def _extract_license_fields(header: dict[str, str]) -> dict[str, str | None]:
    for key, value in header.items():
        stripped = key.strip()
        if stripped.lower().startswith("license_number|"):
            parts = stripped.split("|", 1)
            reported_state = _none_if_blank(parts[1] if len(parts) > 1 else None)
            return {
                "reported_state": reported_state,
                "license_number": _none_if_blank(value),
            }
    return {"reported_state": None, "license_number": None}


def _build_location_rows(
    header: dict[str, str], snapshot_id: str
) -> list[dict[str, Any]]:
    location_names = _split_pipe_values(header.get("location_name"))
    addresses = _split_pipe_values(header.get("hospital_address"))
    count = max(len(location_names), len(addresses))
    if count == 0:
        return []

    rows: list[dict[str, Any]] = []
    for i in range(count):
        rows.append(
            {
                "snapshot_id": snapshot_id,
                "location_ordinal": i,
                "location_name": location_names[i] if i < len(location_names) else None,
                "hospital_address": addresses[i] if i < len(addresses) else None,
            }
        )
    return rows


def _build_general_contract_provision_rows(
    header: dict[str, str], snapshot_id: str
) -> list[dict[str, Any]]:
    """Emit one Bronze row when the optional column header is present.

    CSV exposes general contract provisions as a single flat string in the
    General Data Elements (row 1/2) — no payer/plan structure. A present but
    blank value still emits a row so the dbt validation layer can flag a
    missing ``provisions`` value; an absent column emits nothing.
    """
    if "general_contract_provisions" not in header:
        return []
    return [
        {
            "snapshot_id": snapshot_id,
            "provision_ordinal": 0,
            "payer_name": None,
            "plan_name": None,
            "provisions": _none_if_blank(header.get("general_contract_provisions")),
        }
    ]


def _build_npi_rows(
    header: dict[str, str], snapshot_id: str
) -> list[dict[str, Any]]:
    npis = [v for v in _split_pipe_values(header.get("type_2_npi")) if v]
    return [
        {"snapshot_id": snapshot_id, "npi_ordinal": i, "npi": npi}
        for i, npi in enumerate(npis)
    ]


def _split_pipe_values(raw_value: str | None) -> list[str]:
    if raw_value is None:
        return []
    return [part.strip() for part in raw_value.split("|") if part.strip()]


def _none_if_blank(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None

