# Bronze Layer — Data Dictionary

Hospital Price Transparency Pipeline  
Medallion layer: **Bronze (Raw / Staging)**  
Last updated: 2026-04-19

---

## Overview

The Bronze layer is a **source-faithful representation** of CMS Machine-Readable Files (MRFs). Its purpose is to extract data from three source formats (JSON, CSV Tall, CSV Wide) into relational structures without applying business logic, normalization, or cross-table resolution.

### Core principles

- **No transformation** — column values reflect what the source file contained, including nulls, inconsistencies, and duplicates.
- **Numeric values are preserved as text** — amount, unit, and percentage columns are stored as `Utf8` in both JSON and CSV Bronze so the exact source digits survive. dbt staging is the numeric type boundary: `hpt_safe_decimal` casts currency-like amounts to `decimal(18, 4)` and `hpt_safe_double` casts percentages/units to `double`. See `docs/decisions/0010-monetary-precision.md`.
- **No relational resolution** — Bronze parsers do not perform lookup joins. Raw code strings remain raw code strings.
- **Surrogate keys are pipeline-generated** — the source files contain no natural PKs at the charge-item level. Keys are generated deterministically so that re-ingesting the same file always produces the same keys.

### Format-specific Bronze schemas

The three source formats have meaningfully different structures, and forcing them into a single Bronze schema would require Silver-level normalization logic in the Python parsers. Instead, Bronze uses **two distinct schemas**:

| Format | Bronze Schema | Rationale |
|---|---|---|
| JSON | Multi-table relational (9 tables) | Source is already hierarchical; tables map directly to nested arrays |
| CSV Tall | Single flat table (`csv_charge_rows`) | Source is flat; grouping into parent/child entities is Silver-level work |
| CSV Wide | Single flat table (`csv_charge_rows`) | Wide columns are unpivoted during parsing; output is identical to CSV Tall Bronze |

All three formats share a common `hospital_mrf_snapshots` table and its array children (`hospital_locations`, `type2_npi`), as the header fields are structurally equivalent across all formats.

### What belongs in the CSV parser vs. Silver

The Python/SQL boundary is: **Python handles format-specific structural parsing; SQL/dbt handles semantic normalization.**

| Concern | Layer | Reason |
|---|---|---|
| Unpivoting Wide payer columns into rows | **Bronze parser (Python)** | Payer names in column headers are a format artifact, not data; they cannot be modeled in SQL without knowing payer names at model-write time |
| Splitting pipe-delimited header fields (`location_name`, `hospital_address`, `type_2_npi`) | **Bronze parser (Python)** | Produces `hospital_locations` and `type2_npi` rows; direct structural parsing |
| Exploding `code\|1`, `code\|2`, ... columns into normalized code rows | **Silver (dbt)** | Requires cross-row awareness; belongs with semantic normalization |
| Splitting pipe-delimited `modifiers` string into individual codes | **Silver (dbt)** | Same as above |
| Grouping CSV rows by charge item to create parent entity | **Silver (dbt)** | Deduplication/grouping is business logic |
| Mapping payer names to a canonical payer dimension | **Silver (dbt)** | Business logic |

### Key generation rules

| Key | Pattern | Example |
|---|---|---|
| `snapshot_id` | Set at ingestion time; UUID or hash-based | `vumc_20240101_abc123` |
| `charge_item_id` | `{snapshot_id}_{item_ordinal}` | `vumc_20240101_abc123_42` |
| `standard_charge_id` | `{charge_item_id}_{charge_ordinal}` | `vumc_20240101_abc123_42_0` |
| `modifier_code_id` | `{snapshot_id}_{modifier_ordinal}` | `vumc_20240101_abc123_7` |
| `hospital_location_id` | `{snapshot_id}_{location_ordinal}` | `vumc_20240101_abc123_0` |

> **CSV note:** `charge_item_id` and `standard_charge_id` are not generated for CSV Bronze — they are synthesized at Silver when charge items are identified by grouping. CSV Bronze uses only `snapshot_id` and `row_ordinal`.

### When to add a surrogate PK

A surrogate PK is added **only when another table holds an FK pointing to it**. Leaf tables (nothing references them downstream in Bronze) do not need a PK.

---

## Shared Tables (All Formats)

These tables are populated identically regardless of source format. The CSV parser splits pipe-delimited header fields during parsing to produce normalized rows.

---

### `hospital_mrf_snapshots`

**Grain:** One row per ingested MRF file.  
**Role:** Root anchor table. Every other Bronze table references `snapshot_id`. Created by the parser at ingestion time, not extracted from the source file itself.

| Column | Type | Key | Source | Notes |
|---|---|---|---|---|
| `snapshot_id` | `Utf8` | PK | Pipeline-generated | Unique identifier for this ingestion event |
| `hospital_id` | `Utf8` | FK | Pipeline-generated | Nullable at Bronze; populated at Silver after cross-snapshot hospital normalization |
| `reported_hospital_name` | `Utf8` | | Source-derived | As reported in the MRF file header |
| `source_url` | `Utf8` | | Pipeline-generated | URL the file was retrieved from |
| `source_file_name` | `Utf8` | | Pipeline-generated | Original filename |
| `source_format` | `Utf8` | | Pipeline-generated | `json`, `csv_tall`, or `csv_wide` |
| `file_hash` | `Utf8` | | Pipeline-generated | SHA-256 of the raw file; used to detect duplicate ingestions |
| `ingested_at` | `Utf8` | | Pipeline-generated | ISO 8601 timestamp; cast to `Datetime` at Silver |
| `published_last_updated_on` | `Utf8` | | Source-derived | From MRF header field `last_updated_on` |
| `schema_version` | `Utf8` | | Source-derived | CMS schema version declared in the file |
| `valid_from` | `Utf8` | | Pipeline-generated | ISO 8601; download/valid-from timestamp. Recency key for dbt-derived currentness. Currentness (`is_current_snapshot`) and `valid_to` are **not stored**; dbt derives them from `valid_from` recency |
| `attestation` | `Utf8` | | Source-derived | Nullable |
| `confirm_attestation` | `Utf8` | | Source-derived | Nullable |
| `attester_name` | `Utf8` | | Source-derived | Nullable |
| `reported_state` | `Utf8` | | Source-derived | Nullable |
| `license_number` | `Utf8` | | Source-derived | Nullable |

---

### `hospital_locations`

**Grain:** One row per location entry in the MRF file header.  
**Role:** Child of `hospital_mrf_snapshots`. Leaf table.

> **JSON source:** Iterates the `hospital_address` / `location_name` arrays.  
> **CSV source:** Splits pipe-delimited `location_name` and `hospital_address` header fields on `|` and zips them by position.

| Column | Type | Key | Source | Notes |
|---|---|---|---|---|
| `snapshot_id` | `Utf8` | FK | Pipeline-generated | → `hospital_mrf_snapshots.snapshot_id` |
| `location_ordinal` | `Int64` | | Source-derived | Position in the source location array / pipe-delimited list |
| `location_name` | `Utf8` | | Source-derived | Nullable |
| `hospital_address` | `Utf8` | | Source-derived | Nullable; full address as a single string |

---

### `type2_npi`

**Grain:** One row per NPI entry in the MRF file header.  
**Role:** Child of `hospital_mrf_snapshots`. Leaf table.

> **JSON source:** Iterates the `type_2_npi` array.  
> **CSV source:** Splits pipe-delimited `type_2_npi` header field on `|`.

| Column | Type | Key | Source | Notes |
|---|---|---|---|---|
| `snapshot_id` | `Utf8` | FK | Pipeline-generated | → `hospital_mrf_snapshots.snapshot_id` |
| `npi` | `Utf8` | | Source-derived | NPI number as string; leading zeros must be preserved |
| `npi_ordinal` | `Int64` | | Source-derived | Position in the source NPI array / pipe-delimited list |

---

## JSON Bronze Tables

These tables are populated **only by the JSON parser**. They map directly to the nested array structure of the CMS MRF JSON schema.

---

### `standard_charge_info`

**Grain:** One row per entry in the source `standard_charge_information` array.  
**Role:** Central parent table for charge data. `code_information`, `drug_information`, and `standard_charges` all reference `charge_item_id`.

| Column | Type | Key | Source | Notes |
|---|---|---|---|---|
| `charge_item_id` | `Utf8` | PK | Pipeline-generated | `{snapshot_id}_{item_ordinal}`; not present in source |
| `snapshot_id` | `Utf8` | FK | Pipeline-generated | → `hospital_mrf_snapshots.snapshot_id` |
| `description` | `Utf8` | | Source-derived | Human-readable charge description |
| `item_ordinal` | `Int64` | | Source-derived | Position in `standard_charge_information` array; preserves source order |

---

### `code_information`

**Grain:** One row per billing code associated with a charge item.  
**Role:** Child of `standard_charge_info`. Leaf table.

| Column | Type | Key | Source | Notes |
|---|---|---|---|---|
| `snapshot_id` | `Utf8` | FK | Pipeline-generated | → `hospital_mrf_snapshots.snapshot_id`; denormalized for direct querying |
| `charge_item_id` | `Utf8` | FK | Pipeline-generated | → `standard_charge_info.charge_item_id` |
| `code_ordinal` | `Int64` | | Source-derived | Position within the item's code list |
| `code` | `Utf8` | | Source-derived | Billing code value (e.g., `99213`, `J0696`) |
| `type` | `Utf8` | | Source-derived | Code system: `CPT`, `HCPCS`, `NDC`, `DRG`, `MS-DRG`, `TRIS-DRG`, etc. |

> **Note on dual DRG codes:** A single charge item may carry both `MS-DRG` and `TRIS-DRG` codes simultaneously, producing two rows with different `type` values. This reflects multi-payer clinical coding and is not a data error.

---

### `drug_information`

**Grain:** One row per charge item that has drug pricing metadata. 1:1 with `standard_charge_info` when present.  
**Role:** Child of `standard_charge_info`. Leaf table.

> **Why no PK:** 1:1 relationship with `standard_charge_info` means `charge_item_id` alone identifies the row.  
> **Silver note:** Because this is 1:1, Silver may consolidate `drug_information` columns directly into the `charge_items` table rather than maintaining a separate table.

| Column | Type | Key | Source | Notes |
|---|---|---|---|---|
| `snapshot_id` | `Utf8` | FK | Pipeline-generated | → `hospital_mrf_snapshots.snapshot_id`; denormalized for direct querying |
| `charge_item_id` | `Utf8` | FK | Pipeline-generated | → `standard_charge_info.charge_item_id` |
| `unit` | `Utf8` | | Source-derived | Nullable |
| `type` | `Utf8` | | Source-derived | Unit type: `GR`, `ML`, `ME`, etc. Nullable |

---

### `standard_charges`

**Grain:** One row per payer-setting charge record within a charge item.  
**Role:** Child of `standard_charge_info`. Parent of `payers_information` and `standard_charge_modifiers`.

| Column | Type | Key | Source | Notes |
|---|---|---|---|---|
| `standard_charge_id` | `Utf8` | PK | Pipeline-generated | `{charge_item_id}_{charge_ordinal}`; not present in source |
| `snapshot_id` | `Utf8` | FK | Pipeline-generated | → `hospital_mrf_snapshots.snapshot_id`; denormalized for direct querying |
| `charge_item_id` | `Utf8` | FK | Pipeline-generated | → `standard_charge_info.charge_item_id` |
| `charge_ordinal` | `Int64` | | Source-derived | Position within the item's standard_charges array |
| `minimum` | `Utf8` | | Source-derived | Nullable |
| `maximum` | `Utf8` | | Source-derived | Nullable |
| `gross_charge` | `Utf8` | | Source-derived | Nullable |
| `discounted_cash` | `Utf8` | | Source-derived | Nullable |
| `setting` | `Utf8` | | Source-derived | `inpatient`, `outpatient`, or `both` |
| `billing_class` | `Utf8` | | Source-derived | Nullable; e.g., `professional`, `facility` |
| `additional_generic_notes` | `Utf8` | | Source-derived | Nullable |

---

### `standard_charge_modifiers`

**Grain:** One row per modifier code applied to a standard charge.  
**Role:** Child of `standard_charges`. Leaf table.

> **Critical design note — raw string, not resolved FK:**  
> In the CMS JSON source, `standard_charges[].modifier_code` is an array of plain code strings (e.g., `["25", "59"]`), not references to the top-level `modifier_information` array. Bronze stores the raw string exactly as found in the source. **Do not resolve `modifier_code` to `modifier_code_id` here** — that lookup join is a Silver-layer transformation.
>
> The Silver transformation will perform:
> ```sql
> JOIN bronze.modifiers m
>   ON b.snapshot_id = m.snapshot_id
>   AND b.modifier_code = m.code
> ```

| Column | Type | Key | Source | Notes |
|---|---|---|---|---|
| `snapshot_id` | `Utf8` | FK | Pipeline-generated | → `hospital_mrf_snapshots.snapshot_id` |
| `standard_charge_id` | `Utf8` | FK | Pipeline-generated | → `standard_charges.standard_charge_id` |
| `modifier_code` | `Utf8` | | Source-derived | Raw code string from source (e.g., `"25"`); **not** a FK to `modifiers` |
| `modifier_ordinal` | `Int64` | | Source-derived | Position within the charge's modifier_code array |

---

### `payers_information`

**Grain:** One row per payer/plan rate record within a standard charge.  
**Role:** Child of `standard_charges`. Leaf table.

> **Why no PK:** Nothing holds an FK pointing to this table at Bronze. `payer_ordinal` is added instead of a surrogate PK to support deduplication traceability.  
> **Data quality note:** Duplicate payer rows with identical rates but differing `additional_payer_notes` have been observed during profiling. `payer_ordinal` preserves all source rows so Silver can apply an explicit deduplication strategy rather than silently dropping rows.

| Column | Type | Key | Source | Notes |
|---|---|---|---|---|
| `snapshot_id` | `Utf8` | FK | Pipeline-generated | → `hospital_mrf_snapshots.snapshot_id` |
| `standard_charge_id` | `Utf8` | FK | Pipeline-generated | → `standard_charges.standard_charge_id` |
| `payer_ordinal` | `Int64` | | Pipeline-generated | Position within the charge's payers_information array; enables deduplication traceability at Silver |
| `payer_name` | `Utf8` | | Source-derived | |
| `plan_name` | `Utf8` | | Source-derived | Nullable |
| `methodology` | `Utf8` | | Source-derived | Nullable |
| `standard_charge_dollar` | `Utf8` | | Source-derived | Nullable |
| `standard_charge_percentage` | `Utf8` | | Source-derived | Nullable |
| `standard_charge_algorithm` | `Utf8` | | Source-derived | Nullable |
| `median_amount` | `Utf8` | | Source-derived | Nullable |
| `tenth_percentile` | `Utf8` | | Source-derived | Nullable |
| `ninetieth_percentile` | `Utf8` | | Source-derived | Nullable |
| `count` | `Utf8` | | Source-derived | Nullable; stored as string to preserve source fidelity |
| `additional_payer_notes` | `Utf8` | | Source-derived | Nullable |

---

### `modifiers`

**Grain:** One row per entry in the top-level `modifier_information` array in the MRF file.  
**Role:** Defines what modifier codes mean. Parent of `modifier_payer_info`.

> **JSON-only:** The top-level `modifier_information` array does not exist in CSV formats. CSV files carry modifier codes only as a pipe-delimited string in `csv_charge_rows.modifiers`, with no associated descriptions, settings, or payer rates. The `modifiers` and `modifier_payer_info` tables are never populated by CSV parsers.
>
> **Two modifier structures in JSON source:**  
> - `modifier_information[]` (top-level array) — defines modifier codes with descriptions, settings, and payer rates. Ingested into this table.  
> - `standard_charges[].modifier_code[]` (charge-level array) — a list of raw code strings indicating which modifiers apply to a charge. Ingested into `standard_charge_modifiers`.  
>
> These are linked at Silver by matching `standard_charge_modifiers.modifier_code = modifiers.code` within the same snapshot.

| Column | Type | Key | Source | Notes |
|---|---|---|---|---|
| `modifier_code_id` | `Utf8` | PK | Pipeline-generated | `{snapshot_id}_{modifier_ordinal}`; not present in source |
| `snapshot_id` | `Utf8` | FK | Pipeline-generated | → `hospital_mrf_snapshots.snapshot_id` |
| `code` | `Utf8` | | Source-derived | Modifier code string (e.g., `"25"`); matched against `standard_charge_modifiers.modifier_code` at Silver |
| `description` | `Utf8` | | Source-derived | Nullable |
| `setting` | `Utf8` | | Source-derived | Nullable |

---

### `modifier_payer_info`

**Grain:** One row per payer/plan rate record within a modifier definition.  
**Role:** Child of `modifiers`. Leaf table. **JSON-only** — see `modifiers` note above.

| Column | Type | Key | Source | Notes |
|---|---|---|---|---|
| `snapshot_id` | `Utf8` | FK | Pipeline-generated | → `hospital_mrf_snapshots.snapshot_id` |
| `modifier_code_id` | `Utf8` | FK | Pipeline-generated | → `modifiers.modifier_code_id` |
| `payer_name` | `Utf8` | | Source-derived | |
| `plan_name` | `Utf8` | | Source-derived | Nullable |
| `description` | `Utf8` | | Source-derived | Nullable |

---

## CSV Bronze Table

This table is populated by **both the CSV Tall parser and the CSV Wide parser**. Both parsers produce the same schema. The Wide parser performs a structural unpivot during parsing to achieve this.

---

### `csv_charge_rows`

**Grain:** One row per source file row (after Wide unpivoting). Each row represents one payer rate for one charge item context.  
**Role:** Flat staging table for all CSV-sourced charge data. Code columns (`code_1`, `code_1_type`, etc.) are retained as flat numbered columns here and normalized into rows at Silver.

> **On CSV Tall:** Each source row maps directly to one row in this table with no structural transformation.
>
> **On CSV Wide:** Payer names and plan names are embedded in column headers in the Wide format (e.g., `standard_charge|BlueCross|Blue Choice PPO|negotiated_dollar`). These column headers encode data values — not structure — and cannot be modeled in SQL without knowing payer names at model-write time. The Wide parser extracts the payer name and plan name from each header and unpivots the payer-specific columns into rows, producing one row per source row × payer combination. After unpivoting, the output is structurally identical to CSV Tall Bronze. This is a parsing concern, not a transformation — no business logic is applied.
>
> **On numbered code columns:** The CMS CSV format encodes billing codes as `code|1`, `code|1|type`, `code|2`, `code|2|type`, etc. These are retained as flat numbered columns in Bronze (`code_1`, `code_1_type`, `code_2`, `code_2_type`, ...). Silver normalizes them into rows via `UNPIVOT`. The maximum number of code columns encountered in a file can optionally be recorded as metadata on `hospital_mrf_snapshots` to help Silver models bound their unpivot range.
>
> **On modifiers:** The `modifiers` column contains a pipe-delimited string of modifier codes (e.g., `"25|59"`). Silver splits this into individual modifier rows. No modifier metadata (description, setting, payer rates) is available in CSV — only the code strings.

| Column | Type | Key | Source | Notes |
|---|---|---|---|---|
| `snapshot_id` | `Utf8` | FK | Pipeline-generated | → `hospital_mrf_snapshots.snapshot_id` |
| `row_ordinal` | `Int64` | | Pipeline-generated | Position of the source row in the file; preserves source order |
| `description` | `Utf8` | | Source-derived | General description of the item or service |
| `code_1` | `Utf8` | | Source-derived | Nullable |
| `code_1_type` | `Utf8` | | Source-derived | Nullable |
| `code_2` | `Utf8` | | Source-derived | Nullable |
| `code_2_type` | `Utf8` | | Source-derived | Nullable |
| `code_N` | `Utf8` | | Source-derived | Repeated pattern up to however many code columns exist in the file; unknown at schema definition time |
| `code_N_type` | `Utf8` | | Source-derived | Nullable |
| `setting` | `Utf8` | | Source-derived | `inpatient`, `outpatient`, or `both` |
| `billing_class` | `Utf8` | | Source-derived | Optional; `professional`, `facility`, or `both`. Nullable |
| `drug_unit_of_measurement` | `Utf8` | | Source-derived | Nullable |
| `drug_type_of_measurement` | `Utf8` | | Source-derived | Nullable; `GR`, `ME`, `ML`, `UN`, `F2`, `EA`, `GM` |
| `standard_charge_gross` | `Utf8` | | Source-derived | Nullable |
| `standard_charge_discounted_cash` | `Utf8` | | Source-derived | Nullable |
| `standard_charge_min` | `Utf8` | | Source-derived | Nullable; de-identified minimum across all payers |
| `standard_charge_max` | `Utf8` | | Source-derived | Nullable; de-identified maximum across all payers |
| `modifiers` | `Utf8` | | Source-derived | Nullable; pipe-delimited modifier code string (e.g., `"25\|59"`); split at Silver |
| `payer_name` | `Utf8` | | Source-derived (Tall) / Parser-extracted (Wide) | Nullable; extracted from column header during Wide unpivoting |
| `plan_name` | `Utf8` | | Source-derived (Tall) / Parser-extracted (Wide) | Nullable; extracted from column header during Wide unpivoting |
| `standard_charge_negotiated_dollar` | `Utf8` | | Source-derived | Nullable |
| `standard_charge_negotiated_percentage` | `Utf8` | | Source-derived | Nullable |
| `standard_charge_negotiated_algorithm` | `Utf8` | | Source-derived | Nullable |
| `methodology` | `Utf8` | | Source-derived | Nullable; standard charge methodology |
| `median_amount` | `Utf8` | | Source-derived | Nullable |
| `tenth_percentile` | `Utf8` | | Source-derived | Nullable |
| `ninetieth_percentile` | `Utf8` | | Source-derived | Nullable |
| `count` | `Utf8` | | Source-derived | Nullable; stored as string to preserve source fidelity (values include `"0"`, `"1 through 10"`, whole numbers ≥ 11) |
| `additional_generic_notes` | `Utf8` | | Source-derived | Nullable |
| `additional_payer_notes` | `Utf8` | | Source-derived | Nullable; Wide format has a separate `additional_payer_notes` column; Tall encodes payer-specific notes in `additional_generic_notes` |
| `source_format` | `Utf8` | | Pipeline-generated | `csv_tall` or `csv_wide`; retained for lineage tracing |

---

## Entity Relationship Summary

### JSON Bronze

```
hospital_mrf_snapshots (PK: snapshot_id)
│
├── hospital_locations          [leaf]
├── type2_npi                   [leaf]
├── standard_charge_info (PK: charge_item_id)
│   ├── drug_information        [leaf, 1:1]
│   ├── code_information        [leaf]
│   └── standard_charges (PK: standard_charge_id)
│       ├── standard_charge_modifiers  [leaf — stores raw modifier_code string]
│       └── payers_information         [leaf — no PK, uses payer_ordinal]
│
└── modifiers (PK: modifier_code_id)
    └── modifier_payer_info     [leaf]

Silver join: standard_charge_modifiers.modifier_code → modifiers.code (within snapshot)
```

### CSV Bronze (Tall and Wide)

```
hospital_mrf_snapshots (PK: snapshot_id)
│
├── hospital_locations          [leaf]
├── type2_npi                   [leaf]
└── csv_charge_rows             [leaf — flat; no child tables at Bronze]
```

### Silver Unification

Silver receives inputs from both Bronze schemas and normalizes them into a single format-agnostic model:

```
JSON Bronze:  standard_charge_info + standard_charges + payers_information + code_information
CSV Bronze:   csv_charge_rows (grouped by description + code set, code columns unpivoted)
                    ↓
Silver: hospitals → charge_items → charge_item_codes → payer_charges → modifiers
```

---

## Open Questions / Pending Decisions

| Item | Status | Notes |
|---|---|---|
| Payer name normalization | Pending | Payer names are the primary normalization challenge at Silver; no canonical list yet |
| Erlanger/Panacea endpoint format | Pending | Format and EIN still need confirmation at download time |
| Max code column count tracking | Open | Consider adding `max_code_columns` to `hospital_mrf_snapshots` as metadata to help Silver dbt models bound their CSV UNPIVOT range |
| CSV `additional_generic_notes` vs `additional_payer_notes` | Open | Tall encodes payer-specific notes in the generic notes column; Wide has a separate column. Silver should unify these, likely by coalescing into a single `notes` field per charge row |
| `modifiers` Silver handling for CSV | Open | CSV modifier strings contain code values only (no description, setting, or payer rates). Silver `modifiers` dimension will be sparsely populated for CSV-sourced hospitals — may need a NULL-safe join or a separate modeling path |
