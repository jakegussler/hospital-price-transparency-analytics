# Known Follow-Ups And Risks

This file is a short ledger for unresolved cleanup work, deferred hardening, and
known risks that do not have a better home yet. Do not use it for general
architecture notes, status summaries, or planning history; move durable guidance
to the relevant docs and delete resolved items from here.

## dbt And Bronze Source Risks

- Billing-code normalization added `modifier_signature`, `modifier_count`,
  `clean_setting`, and `clean_billing_class` to `slv_core__payer_rates` via
  `on_schema_change: append_new_columns`, so payer-rate rows for snapshots not
  rebuilt since the change hold nulls in those columns and the two `not_null`
  tests on `modifier_signature`/`modifier_count` fail until those snapshots are
  rebuilt. The three pinned AGENTS.md snapshots are already backfilled by
  scoped builds. Run an unscoped rebuild (for example `make dbt-rebuild`) to
  backfill the rest; that run also executes the new `_core_unit_tests.yml`
  unit tests, which snapshot-scoped runs exclude by design.
- Charge-item normalization has the same backfill caveat: `code_is_specific`
  on `slv_core__charge_item_codes` holds nulls (and its `not_null` test fails)
  for snapshots not rebuilt since the change, the new `slv_core__charge_items`
  model holds rows only for rebuilt snapshots, and `slv_core__service_items`
  — rebuilt from whatever `slv_core__charge_items` holds — covers only those
  snapshots until an unscoped rebuild. The three pinned AGENTS.md snapshots
  are backfilled by scoped builds.
- Bronze re-ingest is not yet an atomic snapshot-partition replacement.
  `BronzeWriter` overwrites the part files it writes but does not remove obsolete
  trailing part files when the new result has fewer parts, so stale Bronze rows
  can remain before dbt reads the partition. This is separate from the warehouse
  `snapshot_replace` strategy and needs backend-neutral partition-overwrite
  semantics in the ingest/storage layer.
- Lincoln Health System (CSV Wide) contributes zero rows to
  `slv_base__payer_rates`: every payer rate it encodes is algorithm-based with no
  `count` of allowed amounts, so all are excluded by
  `v3_percentage_or_algorithm_requires_count`. This is correct CMS enforcement of
  CSV Conditional Requirement 7, but the all-or-nothing outcome is worth a look —
  confirm Lincoln genuinely omits `count` rather than the parser dropping a
  populated count column.
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
- `csv_placeholder_headers_resolved` can currently inspect only bracketed
  placeholders that survive in parsed license-number and attestation values.
  Row-3 code, payer-name, and plan-name header placeholders are not retained in
  Bronze, so the validation rule cannot evaluate the full CMS placeholder
  requirement.
- `csv_modifier_without_item_minimum_information` currently emits only when both
  description and all qualifying charge/note fields are absent. CMS CSV
  Conditional Requirement 11 requires a description and at least one qualifying
  field, so the rule should also emit when either side alone is missing.
