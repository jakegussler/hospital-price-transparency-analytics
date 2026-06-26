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
- Plan normalization added the new NOT NULL column `plan_type_basis` to
  `slv_core__payer_rates` (and the `plan_type` token-derivation fallback) via
  `on_schema_change: append_new_columns`, so payer-rate rows for snapshots not
  rebuilt since the change hold null `plan_type_basis` and the `not_null` test
  on it fails until those snapshots are rebuilt (observed: only the rebuilt
  snapshot has a non-null value; the rest are stale). Scoped builds backfill the
  rebuilt snapshot; run an unscoped rebuild (for example `make dbt-rebuild`) to
  backfill the rest and apply the `plan_type` derivation across the corpus. The
  `core_payer_rates_plan_type_basis_consistency` invariant and the
  `accepted_values` tests already pass on rebuilt rows.
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
- Lincoln Health System (CSV Wide) now contributes its ~2,674 dollar-bearing
  payer rates to `slv_base__payer_rates`. Those rows encode an algorithm string
  and a usable negotiated dollar but no `count`; CSV Conditional Requirement 7
  asks for `count`, but the dollar is the comparable value, so they are retained
  and flagged by the non-excluding warn rule `v3_algorithm_with_dollar_missing_count`
  rather than excluded. Algorithm/percentage rows with neither a dollar nor a
  count remain excluded by `v3_percentage_or_algorithm_requires_count` (correct
  CR7 enforcement). The pinned snapshot `cd725773-f575-45dd-a796-adf9c9805a14` is
  backfilled by scoped builds; an unscoped rebuild is still needed to propagate
  the new retain/flag behavior across the rest of the corpus.
- Silver grain/enum contracts (productionize item 4) added several **deliberately
  warn-severity** dbt tests; do not promote them to error. The
  `slv_base__charge_item_codes` `(silver_charge_item_id, canonical_code_system,
  clean_code)` combination warns because the same code listed twice on one item is
  source-faithful (observed ~17.5k on the corpus). The `slv_base__standard_charges`
  `(snapshot_id, silver_charge_item_id, standard_charge_signature)` combination is
  warn because byte-identical JSON contexts carry distinct signatures. The
  `clean_billing_class` `accepted_values` test is warn because CMS documents those
  values as recommended, matching the report-only `billing_class_allowed_values`
  validation rule. Genuine payer/plan duplicate contexts surface in
  `slv_audit__payer_rate_duplicate_context` and the warn-only
  `core_payer_rate_duplicate_context` test rather than being deduped away.
- The same `append_new_columns` backfill caveat above applies to the `not_null`
  tests on `slv_core__payer_rates` `amount_kind`, `amount_comparability_tier`,
  `methodology`, `methodology_basis`, and `is_price_comparable`: snapshots not
  rebuilt since those columns landed hold nulls and fail on the stale slice. They
  pass on a fresh build (confirmed by the offline e2e fixture run) and on rebuilt
  snapshots; an unscoped rebuild backfills the rest.

## Service-Item Continuity And Validation Corpus

- Service-item supersession links are an extension point, not v1 work.
  `slv_core__service_items` has no `valid_from`/`valid_to`; a token-set-changing
  description rewrite mints a new `service_item_id` and retires the old one with
  no link between them (decision 0014). The multi-snapshot validation
  (`docs/development/multi-snapshot-validation.md`) proves continuity and drift
  *mechanics*, which is sufficient for v1. Calibrating over-merge thresholds and
  adding supersession belong to the price-history extension point (decision
  0016), which is deliberately out of v1 scope and would only be picked up once
  orchestrated multi-snapshot accumulation produced real drift-driven churn.
- The two validation hospitals (`zzz-msval-continuity`, `zzz-msval-overmerge`)
  live in a dedicated fixtures seed
  (`transform/seeds/fixtures/hospitals_validation_fixtures.csv`, tag
  `validation_fixtures`), **not** in `transform/seeds/hospitals.csv`. That seed is
  again a faithful export of the bundled registry, so `make export-hospitals-seed`
  round-trips without dropping rows. The fixtures are kept out of the registry on
  purpose — the registry drives downloads and `MrfSource.url` must be a real
  `HttpUrl`, so fake entries would be attempted on `download --all`. They are
  unioned into `slv_base__hospitals` only when `HPT_INCLUDE_VALIDATION_FIXTURES=true`
  (the `hpt_include_validation_fixtures` dbt var), which the multi-snapshot
  validation workflow sets so the `service_items → hospitals` referential test
  passes; normal runs leave the var false and never include them.

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

## Audit Node-Result Metrics

- `audit__node_results.rows_affected` is sourced from the dbt adapter response
  (`adapter_response.rows_affected`). The dbt-duckdb adapter does not populate it
  for every statement type — observed `NULL` for an incremental model build — so
  row-count coverage is adapter-dependent, not guaranteed. The
  `row_count_semantics` label documents how to read the value per
  materialization; treat `NULL` as "not reported" rather than zero rows. Revisit
  if a later dbt-duckdb version reports it more consistently.

## Gold cross-hospital output is unverifiable locally

- Every Gold peer/percentile/benchmark output (the comparison mart's market and
  payer peer stats, and the Phase 2 summary/benchmark marts) is unverifiable on a
  single pinned snapshot: one hospital means the peer hospital count never clears
  the 3-hospital floor, so published stats stay null and rows carry
  `below_min_hospital_denominator`. Scoped agent runs smoke-test mechanics only;
  validating published percentiles and deltas needs a multi-hospital corpus and is
  a human-run task per AGENTS.md.
- The `gld__service_price_comparison_current` ratio columns
  (`gross_to_cash_ratio`, `cash_to_negotiated_ratio`) are computed per charge-item
  context in the mart per open question §14.2 ("a couple of guarded ratio columns
  in the mart now; dedicated model later"). Promote to a dedicated
  `gld__cash_vs_negotiated` model if the cross-amount-kind logic grows.
