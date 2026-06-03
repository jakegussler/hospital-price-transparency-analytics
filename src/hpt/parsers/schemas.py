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
    "general_contract_provisions": {
        "snapshot_id": pl.Utf8,
        "provision_ordinal": pl.Int64,
        # payer_name/plan_name are optional in CMS and only populated by JSON;
        # CSV exposes a single flat provisions string with both left null.
        "payer_name": pl.Utf8,
        "plan_name": pl.Utf8,
        "provisions": pl.Utf8,
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
        "conflicting_version_signals": pl.Boolean,
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
        # Numeric source values are preserved as raw text in Bronze; dbt staging
        # casts them with hpt_safe_decimal / hpt_safe_double. See ADR 0010.
        "unit": pl.Utf8,
        "type": pl.Utf8,
    },
    "standard_charges": {
        "standard_charge_id": pl.Utf8,
        "snapshot_id": pl.Utf8,
        "charge_item_id": pl.Utf8,
        "charge_ordinal": pl.Int64,
        # Numeric source values are preserved as raw text in Bronze; dbt staging
        # casts them with hpt_safe_decimal / hpt_safe_double. See ADR 0010.
        "minimum": pl.Utf8,
        "maximum": pl.Utf8,
        "gross_charge": pl.Utf8,
        "discounted_cash": pl.Utf8,
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
        # Numeric source values are preserved as raw text in Bronze; dbt staging
        # casts them with hpt_safe_decimal / hpt_safe_double. See ADR 0010.
        "standard_charge_dollar": pl.Utf8,
        "standard_charge_percentage": pl.Utf8,
        "standard_charge_algorithm": pl.Utf8,
        "estimated_amount": pl.Utf8,
        "median_amount": pl.Utf8,
        "tenth_percentile": pl.Utf8,
        "ninetieth_percentile": pl.Utf8,
        "count": pl.Utf8,
        "additional_payer_notes": pl.Utf8,
    },
    "json_record_parse_diagnostics": {
        "snapshot_id": pl.Utf8,
        "section": pl.Utf8,
        "record_ordinal": pl.Int64,
        "reported_schema_version": pl.Utf8,
        "reported_schema_family": pl.Utf8,
        "parser_schema_family": pl.Utf8,
        "parser_schema_version": pl.Utf8,
        "schema_version_mismatch": pl.Boolean,
        "conflicting_version_signals": pl.Boolean,
        "failure_count": pl.Int64,
        "error_summary": pl.Utf8,
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
    # Numeric-looking CSV cells are preserved as raw text in Bronze; dbt staging
    # casts them with hpt_safe_decimal / hpt_safe_double. See ADR 0010.
    "drug_unit_of_measurement": pl.Utf8,
    "drug_type_of_measurement": pl.Utf8,
    "standard_charge_gross": pl.Utf8,
    "standard_charge_discounted_cash": pl.Utf8,
    "standard_charge_min": pl.Utf8,
    "standard_charge_max": pl.Utf8,
    "modifiers": pl.Utf8,
    "payer_name": pl.Utf8,
    "plan_name": pl.Utf8,
    "standard_charge_negotiated_dollar": pl.Utf8,
    "standard_charge_negotiated_percentage": pl.Utf8,
    "standard_charge_negotiated_algorithm": pl.Utf8,
    "methodology": pl.Utf8,
    "median_amount": pl.Utf8,
    "tenth_percentile": pl.Utf8,
    "ninetieth_percentile": pl.Utf8,
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
