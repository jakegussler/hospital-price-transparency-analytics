"""Parser for CSV wide-format MRF files (dynamic payer columns)."""

from __future__ import annotations

import logging
from collections.abc import Iterator
from pathlib import Path
from typing import TYPE_CHECKING, Any

from hpt.parsers.base import BaseParser
from hpt.parsers.csv_header import (
    build_header_batch,
    build_wide_column_catalog,
    get_charge_reader,
    parse_csv_header,
)
from hpt.parsers.helpers import _df
from hpt.parsers.schemas import build_csv_charge_rows_schema

if TYPE_CHECKING:
    import polars as pl

logger = logging.getLogger(__name__)

_BATCH_SIZE = 5000


class CsvWideParser(BaseParser):
    """Parse and unpivot CSV wide-format hospital MRF files."""

    def parse(self, file_path: Path) -> Iterator[dict[str, pl.DataFrame]]:
        snapshot_record, location_rows, npi_rows, provision_rows = parse_csv_header(
            file_path, self.snapshot_meta
        )
        yield build_header_batch(
            snapshot_record, location_rows, npi_rows, provision_rows
        )

        reader, charge_headers, handle = get_charge_reader(file_path)
        try:
            max_codes, catalog = build_wide_column_catalog(charge_headers)
            schema = build_csv_charge_rows_schema(max_codes)
            rows_buffer: list[dict[str, Any]] = []
            snapshot_id = self.snapshot_meta["snapshot_id"]
            source_format = self.snapshot_meta.get("source_format", "csv_wide")

            for row_ordinal, row in enumerate(reader):
                fixed_values = _extract_values(row, catalog.fixed_columns)
                emitted_payer_row = False

                for payer_group in catalog.payer_groups:
                    payer_values = _extract_values(row, payer_group.columns)
                    notes_idx = catalog.additional_payer_notes_cols.get(
                        (payer_group.payer_name, payer_group.plan_name)
                    )
                    note_value = (
                        _safe_cell(row, notes_idx) if notes_idx is not None else None
                    )

                    # In wide format the payer/plan identity lives in the column
                    # headers and is shared by every item, so an empty payer block
                    # is the absence of a rate rather than a source-asserted row.
                    # Skip it: materializing it would invent a payer-rate fact the
                    # source never stated and inflate Bronze with null rows.
                    if not payer_values and note_value is None:
                        continue

                    out_row = _new_row(
                        schema, snapshot_id, row_ordinal, source_format, fixed_values
                    )
                    out_row["payer_name"] = payer_group.payer_name or None
                    out_row["plan_name"] = payer_group.plan_name or None
                    for key, value in payer_values.items():
                        out_row[key] = value
                    if note_value is not None:
                        out_row["additional_payer_notes"] = note_value

                    rows_buffer.append(out_row)
                    emitted_payer_row = True

                # Every item must still surface its item-level standard charge
                # (gross, discounted cash, min/max, codes). When no payer column
                # carried a value for this item, emit a single item-only baseline
                # row with null payer identity — the same shape a CSV Tall
                # item-only row takes.
                if not emitted_payer_row:
                    rows_buffer.append(
                        _new_row(
                            schema, snapshot_id, row_ordinal, source_format, fixed_values
                        )
                    )

                if len(rows_buffer) >= _BATCH_SIZE:
                    yield {"csv_charge_rows": _df(rows_buffer, schema)}
                    rows_buffer = []

            if rows_buffer:
                yield {"csv_charge_rows": _df(rows_buffer, schema)}
        finally:
            handle.close()


def _new_row(
    schema: dict[str, Any],
    snapshot_id: str,
    row_ordinal: int,
    source_format: str,
    fixed_values: dict[str, str | None],
) -> dict[str, Any]:
    out_row: dict[str, Any] = {column: None for column in schema}
    out_row["snapshot_id"] = snapshot_id
    out_row["row_ordinal"] = row_ordinal
    out_row["source_format"] = source_format
    for key, value in fixed_values.items():
        out_row[key] = value
    return out_row


def _extract_values(
    row: list[str],
    column_map: dict[str, int],
) -> dict[str, str | None]:
    values: dict[str, str | None] = {}
    for column_name, index in column_map.items():
        value = _safe_cell(row, index)
        if value is None:
            continue
        values[column_name] = value
    return values


def _safe_cell(row: list[str], idx: int | None) -> str | None:
    if idx is None or idx >= len(row):
        return None
    value = row[idx].strip()
    return value or None
