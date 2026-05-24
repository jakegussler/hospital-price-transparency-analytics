# CMS MRF Schema Notes

This project currently targets CMS Hospital Price Transparency MRF structures,
including JSON, CSV Tall, and CSV Wide layouts. The checked-in format templates
under `docs/format_templates/` are the local reference files.

## Shared Header Concepts

All supported layouts contain hospital-level metadata and charge data.

Header fields populate the shared Bronze tables:

- `hospital_mrf_snapshots`
- `hospital_locations`
- `type2_npi`

Important header concepts:

- Hospital name is source-reported and may not match registry naming.
- `last_updated_on` is source-reported and may need Silver typing.
- Schema `version` is source-reported.
- Location names and addresses can contain multiple values.
- Type-2 NPIs can contain multiple values.
- License number can encode state in CSV header keys.
- Attestation is structurally different in JSON and CSV, but maps to the same
  Bronze snapshot fields.

See `docs/header_parsing.md` for detailed extraction rules.

## JSON Layout

JSON MRFs are a single top-level object. Header fields live at the top level.
Charge records live in `standard_charge_information`.

Parser rules:

- Stream with `ijson`; do not load large source files into memory.
- Parse header fields from top-level keys.
- Iterate `standard_charge_information` items as charge-item parents.
- Read optional top-level `modifier_information` as modifier definitions; do not
  expect a source root object named `standard_charge_modifiers`.
- Read charge-level modifier references from
  `standard_charges[].modifier_code`.
- Preserve arrays as child tables when they are structural source arrays.
- Validate charge records with Pydantic models where practical.
- Write invalid charge records to quarantine rather than failing the full file
  when row-level validation can isolate the issue.

Bronze JSON table families:

- `standard_charge_info`
- `code_information`
- `drug_information`
- `standard_charges`
- `standard_charge_modifiers`
- `payers_information`
- `modifiers`
- `modifier_payer_info`

## CSV Tall Layout

CSV Tall files use the first three rows differently from charge rows:

```text
Row 1  Header keys
Row 2  Header values
Row 3  Charge column headers
Row 4+ Charge data rows
```

Parser rules:

- Zip row 1 and row 2 to extract header metadata.
- Treat row 3 as the charge-data header row.
- Parse rows 4 and onward as source charge rows.
- Preserve raw charge row values in `csv_charge_rows`.
- Leave charge-item grouping, code explosion, payer normalization, and modifier
  normalization to Silver.

## CSV Wide Layout

CSV Wide files share the same first three row structure as CSV Tall, but payer
and plan names are embedded in dynamic charge columns.

Parser rules:

- Parse rows 1 and 2 like CSV Tall.
- Use row 3 to catalog static columns and payer-bearing dynamic columns.
- Unpivot payer-specific wide columns into rows.
- Write the same Bronze table shape as CSV Tall: `csv_charge_rows`.
- Preserve payer and plan strings extracted from column headers.

## Attestation

In JSON, attestation fields are structured values. In CSV, the attestation text
itself appears as a header cell and the row 2 value is the confirmation.

CSV parser rule:

- Detect the attestation column by text prefix, not by fixed position.
- Store the full statement text in `attestation`.
- Store the row 2 value in `confirm_attestation`.

## License State

CSV license headers can look like `license_number|TN`.

Parser rule:

- Split the key on `|`.
- Store the suffix as `reported_state`.
- Store the row 2 value as `license_number`.

## Bronze vs Silver Decisions

Bronze should handle source structure only:

- JSON hierarchy to relational child tables.
- CSV header extraction.
- CSV Wide unpivoting.
- Pipe-delimited hospital locations and NPIs.

Silver should handle business semantics:

- Code normalization and code-system cleanup.
- Charge-item grouping for CSV.
- Payer and plan matching.
- Modifier resolution.
- Date casting and data quality rules.
