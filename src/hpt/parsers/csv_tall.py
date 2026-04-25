"""Parser for CSV tall-format MRF files."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import TYPE_CHECKING, Any

from hpt.parsers.base import BaseParser
from hpt.parsers.csv_header import (
    build_header_batch,
    build_tall_column_map,
    get_charge_reader,
    parse_csv_header,
)
from hpt.parsers.helpers import _df
from hpt.parsers.schemas import build_csv_charge_rows_schema

if TYPE_CHECKING:
    import polars as pl

_BATCH_SIZE = 5000
_NUMERIC_COLUMNS = {
    "drug_unit_of_measurement",
    "standard_charge_gross",
    "standard_charge_discounted_cash",
    "standard_charge_min",
    "standard_charge_max",
    "standard_charge_negotiated_dollar",
    "standard_charge_negotiated_percentage",
    "median_amount",
    "tenth_percentile",
    "ninetieth_percentile",
}


class CsvTallParser(BaseParser):
    """Parse CSV tall-format hospital MRF files."""

    def parse(self, file_path: Path) -> Iterator[dict[str, pl.DataFrame]]:
        snapshot_record, location_rows, npi_rows = parse_csv_header(
            file_path, self.snapshot_meta
        )
        yield build_header_batch(snapshot_record, location_rows, npi_rows)

        reader, charge_headers, handle = get_charge_reader(file_path)
        try:
            max_codes, column_map = build_tall_column_map(charge_headers)
            schema = build_csv_charge_rows_schema(max_codes)
            rows_buffer: list[dict[str, Any]] = []
            snapshot_id = self.snapshot_meta["snapshot_id"]
            source_format = self.snapshot_meta.get("source_format", "csv_tall")

            for row_ordinal, row in enumerate(reader):
                out_row = {column: None for column in schema}
                out_row["snapshot_id"] = snapshot_id
                out_row["row_ordinal"] = row_ordinal
                out_row["source_format"] = source_format

                for column_name, index in column_map.items():
                    value = _safe_cell(row, index)
                    if value is None:
                        continue
                    if column_name in _NUMERIC_COLUMNS:
                        out_row[column_name] = _to_optional_float(value)
                    else:
                        out_row[column_name] = value

                rows_buffer.append(out_row)
                if len(rows_buffer) >= _BATCH_SIZE:
                    yield {"csv_charge_rows": _df(rows_buffer, schema)}
                    rows_buffer = []

            if rows_buffer:
                yield {"csv_charge_rows": _df(rows_buffer, schema)}
        finally:
            handle.close()


def _safe_cell(row: list[str], idx: int) -> str | None:
    if idx >= len(row):
        return None
    value = row[idx].strip()
    return value or None


def _to_optional_float(value: str) -> float | None:
    cleaned = value.strip()
    if not cleaned:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None
