# Bronze Schema Diagram

This document describes the implemented Bronze schema. It is grounded in
`src/hpt/parsers/schemas.py`, `docs/bronze_layer.md`, and the current dbt Bronze
source declarations in `transform/models/staging/_bronze_sources.yml`.

Local reference image:

![Bronze schema reference](../local/diagrams/hps_bronze_2026-05-20.png)

The image is a useful visual reference, but the Mermaid diagram below reflects
what currently exists in the parser schemas. Bronze does not currently include a
canonical `hospital` dimension, and most leaf tables do not have Silver-style
surrogate primary keys.

```mermaid
erDiagram
  hospital_mrf_snapshots {
    string snapshot_id PK
    string hospital_id
    string reported_hospital_name
    string source_url
    string source_file_name
    string source_format
    string file_hash
    string ingested_at
    string published_last_updated_on
    string schema_version
    boolean is_current_snapshot
    string valid_from
    string valid_to
    string attestation
    string confirm_attestation
    string attester_name
    string affirmation
    string confirm_affirmation
    string reported_state
    string license_number
  }

  hospital_locations {
    string snapshot_id FK
    int location_ordinal
    string location_name
    string hospital_address
  }

  type2_npi {
    string snapshot_id FK
    string npi
    int npi_ordinal
  }

  general_contract_provisions {
    string snapshot_id FK
    int provision_ordinal
    string payer_name
    string plan_name
    string provisions
  }

  standard_charge_info {
    string charge_item_id PK
    string snapshot_id FK
    string description
    int item_ordinal
    string reported_schema_version
    string reported_schema_family
    string parser_schema_family
    string parser_schema_version
    boolean schema_version_mismatch
  }

  code_information {
    string snapshot_id FK
    string charge_item_id FK
    int code_ordinal
    string code
    string type
  }

  drug_information {
    string snapshot_id FK
    string charge_item_id FK
    string unit
    string type
  }

  standard_charges {
    string standard_charge_id PK
    string snapshot_id FK
    string charge_item_id FK
    int charge_ordinal
    string minimum
    string maximum
    string gross_charge
    string discounted_cash
    string setting
    string billing_class
    string additional_generic_notes
  }

  standard_charge_modifiers {
    string snapshot_id FK
    string standard_charge_id FK
    string modifier_code
    int modifier_ordinal
  }

  payers_information {
    string snapshot_id FK
    string standard_charge_id FK
    int payer_ordinal
    string payer_name
    string plan_name
    string methodology
    string standard_charge_dollar
    string standard_charge_percentage
    string standard_charge_algorithm
    string estimated_amount
    string median_amount
    string tenth_percentile
    string ninetieth_percentile
    string count
    string additional_payer_notes
  }

  json_record_parse_diagnostics {
    string snapshot_id FK
    string section
    int record_ordinal
    string reported_schema_version
    string reported_schema_family
    string accepted_schema_family
    string accepted_schema_version
    boolean schema_version_mismatch
    string attempted_schema_families
    int failure_count
    string error_summary
    string final_status
    string diagnosed_at
  }

  modifiers {
    string modifier_code_id PK
    string snapshot_id FK
    string code
    string description
    string setting
  }

  modifier_payer_info {
    string snapshot_id FK
    string modifier_code_id FK
    string payer_name
    string plan_name
    string description
  }

  csv_charge_rows {
    string snapshot_id FK
    int row_ordinal
    string description
    string code_N
    string code_N_type
    string setting
    string billing_class
    string drug_unit_of_measurement
    string drug_type_of_measurement
    string standard_charge_gross
    string standard_charge_discounted_cash
    string standard_charge_min
    string standard_charge_max
    string modifiers
    string payer_name
    string plan_name
    string standard_charge_negotiated_dollar
    string standard_charge_negotiated_percentage
    string standard_charge_negotiated_algorithm
    string methodology
    string median_amount
    string tenth_percentile
    string ninetieth_percentile
    string count
    string additional_generic_notes
    string additional_payer_notes
    string source_format
  }

  hospital_mrf_snapshots ||--o{ hospital_locations : has
  hospital_mrf_snapshots ||--o{ type2_npi : has
  hospital_mrf_snapshots ||--o{ general_contract_provisions : has
  hospital_mrf_snapshots ||--o{ standard_charge_info : has
  standard_charge_info ||--o{ code_information : has
  standard_charge_info ||--o| drug_information : may_have
  standard_charge_info ||--o{ standard_charges : has
  standard_charges ||--o{ standard_charge_modifiers : has
  standard_charges ||--o{ payers_information : has
  hospital_mrf_snapshots ||--o{ json_record_parse_diagnostics : has
  hospital_mrf_snapshots ||--o{ modifiers : has
  modifiers ||--o{ modifier_payer_info : has
  hospital_mrf_snapshots ||--o{ csv_charge_rows : has
```

## Current Table Families

Shared tables for all formats:

- `hospital_mrf_snapshots`
- `hospital_locations`
- `type2_npi`
- `general_contract_provisions` (JSON emits one row per array object with
  optional payer/plan; CSV emits a single row from the flat General Data
  Element column)

JSON-only tables:

- `standard_charge_info`
- `code_information`
- `drug_information`
- `standard_charges`
- `standard_charge_modifiers`
- `payers_information`
- `json_record_parse_diagnostics`
- `modifiers`
- `modifier_payer_info`

CSV Bronze table:

- `csv_charge_rows`

## Important Notes

- Optional tables a parser emits with no rows for a snapshot (e.g.
  `general_contract_provisions` when absent, or `modifiers` for a file with no
  modifier dimension) are written as zero-row Parquet files so their partition
  directory always exists and downstream dbt `read_parquet` globs do not fail.
- `general_contract_provisions` is source-faithful: a provisions object missing
  its required `provisions` text is preserved (not quarantined), and the dbt
  `general_contract_provisions_required_shape` rule flags it in
  `val__header_violations`.
- `code_N` and `code_N_type` columns in `csv_charge_rows` are dynamic per file.
- Bronze stores `modifier_code` strings on `standard_charge_modifiers`; it does
  not resolve them to `modifier_code_id`.
- JSON `standard_charge_information` rows include reported and parser schema
  family fields. When a row parses only under a non-reported schema family, the
  row is retained and `json_record_parse_diagnostics` records the fallback.
- Both JSON and CSV Bronze store numeric-looking source values (charges,
  percentiles, units) as raw text (`Utf8`). dbt staging is the numeric type
  boundary: it casts currency-like amount fields to `decimal(18, 4)` via
  `hpt_safe_decimal` and percentages/units to `double` via `hpt_safe_double`
  before Silver modeling; see `docs/decisions/0010-monetary-precision.md`.
- JSON and CSV differ in how invalid numbers are surfaced. JSON validates each
  record with Pydantic before Bronze, so a record with an invalid numeric field
  is quarantined as JSONL and recorded in the `json_record_parse_diagnostics`
  Bronze table — invalid JSON numbers generally never reach an accepted Bronze
  row. CSV performs no such validation; its malformed numeric values survive as
  raw text in Bronze and are queryable through the dbt
  `stg_bronze__csv_numeric_parse_diagnostics` staging model, which emits one row
  per non-empty raw value that fails the staging cast. The broader dbt
  validation schema now supersedes that CSV-only diagnostic for Silver
  filtering: `val__standard_charge_violations`, `val__payer_rate_violations`,
  and `val__drug_violations` emit one row per malformed numeric value across
  JSON and CSV where Bronze row evidence exists.
- Bronze preserves source values and parser lineage. Hospital, payer, plan,
  charge-item, code, and modifier normalization belongs in Silver.
- Bronze and staging are not filtered by validation. Reject-severity validation
  failures remain in Bronze and are excluded only when Silver base models
  anti-join the dbt rejection keysets.
