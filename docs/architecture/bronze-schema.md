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

  standard_charge_info {
    string charge_item_id PK
    string snapshot_id FK
    string description
    int item_ordinal
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
    float unit
    string type
  }

  standard_charges {
    string standard_charge_id PK
    string snapshot_id FK
    string charge_item_id FK
    int charge_ordinal
    float minimum
    float maximum
    float gross_charge
    float discounted_cash
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
    float standard_charge_dollar
    float standard_charge_percentage
    string standard_charge_algorithm
    float median_amount
    float tenth_percentile
    float ninetieth_percentile
    string count
    string additional_payer_notes
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
    float drug_unit_of_measurement
    string drug_type_of_measurement
    float standard_charge_gross
    float standard_charge_discounted_cash
    float standard_charge_min
    float standard_charge_max
    string modifiers
    string payer_name
    string plan_name
    float standard_charge_negotiated_dollar
    float standard_charge_negotiated_percentage
    string standard_charge_negotiated_algorithm
    string methodology
    float median_amount
    float tenth_percentile
    float ninetieth_percentile
    string count
    string additional_generic_notes
    string additional_payer_notes
    string source_format
  }

  hospital_mrf_snapshots ||--o{ hospital_locations : has
  hospital_mrf_snapshots ||--o{ type2_npi : has
  hospital_mrf_snapshots ||--o{ standard_charge_info : has
  standard_charge_info ||--o{ code_information : has
  standard_charge_info ||--o| drug_information : may_have
  standard_charge_info ||--o{ standard_charges : has
  standard_charges ||--o{ standard_charge_modifiers : has
  standard_charges ||--o{ payers_information : has
  hospital_mrf_snapshots ||--o{ modifiers : has
  modifiers ||--o{ modifier_payer_info : has
  hospital_mrf_snapshots ||--o{ csv_charge_rows : has
```

## Current Table Families

Shared tables for all formats:

- `hospital_mrf_snapshots`
- `hospital_locations`
- `type2_npi`

JSON-only tables:

- `standard_charge_info`
- `code_information`
- `drug_information`
- `standard_charges`
- `standard_charge_modifiers`
- `payers_information`
- `modifiers`
- `modifier_payer_info`

CSV Bronze table:

- `csv_charge_rows`

## Important Notes

- `csv_charge_rows` is produced by CSV parsers, but it is not yet declared in
  `transform/models/staging/_bronze_sources.yml`.
- `code_N` and `code_N_type` columns in `csv_charge_rows` are dynamic per file.
- Bronze stores `modifier_code` strings on `standard_charge_modifiers`; it does
  not resolve them to `modifier_code_id`.
- Bronze preserves source values and parser lineage. Hospital, payer, plan,
  charge-item, code, and modifier normalization belongs in Silver.
