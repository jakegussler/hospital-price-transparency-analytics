# Known Follow-Ups And Risks

This file is a short ledger for unresolved cleanup work, deferred hardening, and
known risks that do not have a better home yet. Do not use it for general
architecture notes, status summaries, or planning history; move durable guidance
to the relevant docs and delete resolved items from here.

## dbt And Bronze Source Risks

- `reconcile_csv_rows_to_standard_charges` reports a small number of CSV charge
  rows (8 observed for `ballad-jcmc`) that map to no Silver standard charge and
  are not captured by any rejection model. Snapshot scoping surfaced this
  because scoped runs scan the full selected snapshot rather than applying the
  old development row limit. Root-cause the rows and either fix the CSV-to-Silver
  mapping or add an explicit rejection path.
- dbt Bronze source reads can still fail with an empty-glob `read_parquet` error
  when the entire corpus lacks a format-specific table family, such as
  `csv_charge_rows` in a JSON-only local data set. `BronzeWriter` writes
  zero-row Parquet only for tables a parser emits for a snapshot; it does not
  bootstrap every declared Bronze source table. Consider guarding source macros,
  adding a source bootstrap step, or documenting a required mixed-format fixture
  for local dbt runs.

## Parser Validation Hardening

- The JSON streaming parser validates individual
  `standard_charge_information` and `modifier_information` objects, but it does
  not instantiate the root `CMSMRFJson` model over entire files. Header/root
  required-shape gaps are currently surfaced through Bronze header rows and dbt
  validation rather than parser quarantine. Decide whether that boundary is
  sufficient, or add a streaming root-shape validation pass if files appear that
  cannot produce reliable header evidence.
