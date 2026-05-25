"""Polars schemas for the Bronze layer.

Single source of truth for column names and types across all formats. Every
parser references these schemas so that each table's Parquet file is
shape-identical regardless of source format.

See :mod:`docs/bronze_layer.md` for the full data dictionary.
"""

from __future__ import annotations

import polars as pl

SHARED_SCHEMAS: dict[str, dict[str, pl.DataType]] = {
    "hospital_mrf_snapshots": {
        "snapshot_id": pl.Utf8,
        "hospital_id": pl.Utf8,
        "reported_hospital_name": pl.Utf8,
        "source_url": pl.Utf8,
        "source_file_name": pl.Utf8,
        "source_format": pl.Utf8,
        "file_hash": pl.Utf8,
        "ingested_at": pl.Utf8,
        "published_last_updated_on": pl.Utf8,
        "schema_version": pl.Utf8,
        "is_current_snapshot": pl.Boolean,
        "valid_from": pl.Utf8,
        "valid_to": pl.Utf8,
        "attestation": pl.Utf8,
        "confirm_attestation": pl.Utf8,
        "attester_name": pl.Utf8,
        "affirmation": pl.Utf8,
        "confirm_affirmation": pl.Utf8,
        "reported_state": pl.Utf8,
        "license_number": pl.Utf8,
    },
    "hospital_locations": {
        "snapshot_id": pl.Utf8,
        "location_ordinal": pl.Int64,
        "location_name": pl.Utf8,
        "hospital_address": pl.Utf8,
    },
    "type2_npi": {
        "snapshot_id": pl.Utf8,
        "npi": pl.Utf8,
        "npi_ordinal": pl.Int64,
    },
}

JSON_SCHEMAS: dict[str, dict[str, pl.DataType]] = {
    "standard_charge_info": {
        "charge_item_id": pl.Utf8,
        "snapshot_id": pl.Utf8,
        "description": pl.Utf8,
        "item_ordinal": pl.Int64,
        "reported_schema_version": pl.Utf8,
        "reported_schema_family": pl.Utf8,
        "parser_schema_family": pl.Utf8,
        "parser_schema_version": pl.Utf8,
        "schema_version_mismatch": pl.Boolean,
    },
    "code_information": {
        "snapshot_id": pl.Utf8,
        "charge_item_id": pl.Utf8,
        "code_ordinal": pl.Int64,
        "code": pl.Utf8,
        "type": pl.Utf8,
    },
    "drug_information": {
        "snapshot_id": pl.Utf8,
        "charge_item_id": pl.Utf8,
        "unit": pl.Float64,
        "type": pl.Utf8,
    },
    "standard_charges": {
        "standard_charge_id": pl.Utf8,
        "snapshot_id": pl.Utf8,
        "charge_item_id": pl.Utf8,
        "charge_ordinal": pl.Int64,
        "minimum": pl.Float64,
        "maximum": pl.Float64,
        "gross_charge": pl.Float64,
        "discounted_cash": pl.Float64,
        "setting": pl.Utf8,
        "billing_class": pl.Utf8,
        "additional_generic_notes": pl.Utf8,
    },
    "standard_charge_modifiers": {
        "snapshot_id": pl.Utf8,
        "standard_charge_id": pl.Utf8,
        "modifier_code": pl.Utf8,
        "modifier_ordinal": pl.Int64,
    },
    "payers_information": {
        "snapshot_id": pl.Utf8,
        "standard_charge_id": pl.Utf8,
        "payer_ordinal": pl.Int64,
        "payer_name": pl.Utf8,
        "plan_name": pl.Utf8,
        "methodology": pl.Utf8,
        "standard_charge_dollar": pl.Float64,
        "standard_charge_percentage": pl.Float64,
        "standard_charge_algorithm": pl.Utf8,
        "estimated_amount": pl.Float64,
        "median_amount": pl.Float64,
        "tenth_percentile": pl.Float64,
        "ninetieth_percentile": pl.Float64,
        "count": pl.Utf8,
        "additional_payer_notes": pl.Utf8,
    },
    "json_record_parse_diagnostics": {
        "snapshot_id": pl.Utf8,
        "section": pl.Utf8,
        "record_ordinal": pl.Int64,
        "reported_schema_version": pl.Utf8,
        "reported_schema_family": pl.Utf8,
        "accepted_schema_family": pl.Utf8,
        "accepted_schema_version": pl.Utf8,
        "schema_version_mismatch": pl.Boolean,
        "attempted_schema_families": pl.Utf8,
        "failure_count": pl.Int64,
        "error_summary": pl.Utf8,
        "final_status": pl.Utf8,
        "diagnosed_at": pl.Utf8,
    },
    "modifiers": {
        "modifier_code_id": pl.Utf8,
        "snapshot_id": pl.Utf8,
        "code": pl.Utf8,
        "description": pl.Utf8,
        "setting": pl.Utf8,
    },
    "modifier_payer_info": {
        "snapshot_id": pl.Utf8,
        "modifier_code_id": pl.Utf8,
        "payer_name": pl.Utf8,
        "plan_name": pl.Utf8,
        "description": pl.Utf8,
    },
}

CSV_CHARGE_ROWS_BASE: dict[str, pl.DataType] = {
    "snapshot_id": pl.Utf8,
    "row_ordinal": pl.Int64,
    "description": pl.Utf8,
    # code_N/code_N_type fields are inserted dynamically per file.
    "setting": pl.Utf8,
    "billing_class": pl.Utf8,
    "drug_unit_of_measurement": pl.Float64,
    "drug_type_of_measurement": pl.Utf8,
    "standard_charge_gross": pl.Float64,
    "standard_charge_discounted_cash": pl.Float64,
    "standard_charge_min": pl.Float64,
    "standard_charge_max": pl.Float64,
    "modifiers": pl.Utf8,
    "payer_name": pl.Utf8,
    "plan_name": pl.Utf8,
    "standard_charge_negotiated_dollar": pl.Float64,
    "standard_charge_negotiated_percentage": pl.Float64,
    "standard_charge_negotiated_algorithm": pl.Utf8,
    "methodology": pl.Utf8,
    "median_amount": pl.Float64,
    "tenth_percentile": pl.Float64,
    "ninetieth_percentile": pl.Float64,
    "count": pl.Utf8,
    "additional_generic_notes": pl.Utf8,
    "additional_payer_notes": pl.Utf8,
    "source_format": pl.Utf8,
}


def build_csv_charge_rows_schema(max_codes: int) -> dict[str, pl.DataType]:
    """Build ``csv_charge_rows`` schema with dynamic ``code_N`` columns."""
    if max_codes < 0:
        msg = "max_codes must be >= 0"
        raise ValueError(msg)

    schema: dict[str, pl.DataType] = {
        "snapshot_id": pl.Utf8,
        "row_ordinal": pl.Int64,
        "description": pl.Utf8,
    }
    for i in range(1, max_codes + 1):
        schema[f"code_{i}"] = pl.Utf8
        schema[f"code_{i}_type"] = pl.Utf8

    for column, dtype in CSV_CHARGE_ROWS_BASE.items():
        if column in {"snapshot_id", "row_ordinal", "description"}:
            continue
        schema[column] = dtype

    return schema


CSV_SCHEMAS: dict[str, dict[str, pl.DataType]] = {}

BRONZE_SCHEMAS: dict[str, dict[str, pl.DataType]] = {
    **SHARED_SCHEMAS,
    **JSON_SCHEMAS,
    **CSV_SCHEMAS,
}


__all__ = [
    "BRONZE_SCHEMAS",
    "CSV_CHARGE_ROWS_BASE",
    "CSV_SCHEMAS",
    "JSON_SCHEMAS",
    "SHARED_SCHEMAS",
    "build_csv_charge_rows_schema",
]
