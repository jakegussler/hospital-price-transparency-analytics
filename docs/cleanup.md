# Known Follow-Ups And Risks

This file is a short ledger for unresolved cleanup work, deferred hardening, and
known risks that do not have a better home yet. Do not use it for general
architecture notes, status summaries, or planning history; move durable guidance
to the relevant docs and delete resolved items from here.

## dbt And Bronze Source Risks

- Bronze re-ingest is not yet an atomic snapshot-partition replacement.
  `BronzeWriter` overwrites the part files it writes but does not remove obsolete
  trailing part files when the new result has fewer parts, so stale Bronze rows
  can remain before dbt reads the partition. This is separate from the warehouse
  `snapshot_replace` strategy and needs backend-neutral partition-overwrite
  semantics in the ingest/storage layer.

## Validation + Gold marts spill on constrained local machines

- The full Nashville corpus can exceed the temp-spill budget on small developer
  machines. `transform/profiles.yml` sets **`threads: 1`** so the two validation
  violation models do not spill concurrently, plus an explicit
  `max_temp_directory_size` so an oversized model fails cleanly instead of
  filling the disk.
- **`val__code_violations` / `val__standard_charge_violations` restructure (A+B,
  applied).** The dominant spill driver was *not* the `cms_validation_rules` join
  (that join is on the already-filtered violation rows and is cheap). It was the
  normalized charge/code grain being **re-scanned once per rule**: each model
  built a wide JSON+CSV union (and, for code, the CSV unpivot self-join) as a CTE
  and then scanned it ~13× / ~5× through a per-rule `UNION ALL`, recomputing and
  re-spilling the whole surface every branch. Two changes removed this:
  - **A — materialized intermediates.** The grain now lives in
    `val_int__standard_charge_grain`, `val_int__code_grain`, and
    `val_int__csv_code_pairs` (all `+materialized: table`, scoped, under
    `validation.violations.intermediate`). It is computed once and the CSV
    unpivot runs once (the code grain and the missing-code anti-join both read
    `val_int__csv_code_pairs`).
  - **B — single-pass rule evaluation.** Each violation model scans its grain
    once, emitting a `list_filter([... struct_pack ...])` of violated rules per
    row and `unnest`-ing it, instead of one `UNION ALL` branch per rule. Output
    is byte-identical (same surrogate keys / column contract); verified by an
    old-vs-new equivalence harness over synthetic rows hitting every branch and
    by the full `--selector validation` graph.
- Scoping the build to **one hospital at a time** (`--hospital-ids <one>`) keeps
  these models in budget. **Williamson Medical Center** and **Maury Regional**
  (the two largest **CSV-wide** hospitals) remain deactivated (`active: false`);
  re-verify them on the dev box now that the unpivot is materialized once, and
  reactivate if their single-hospital `val__code_violations` fits. If the unpivot
  self-join still spills there, the follow-on is restructure **C** (fuse the two
  per-ordinal unpivots in `hpt_csv_code_unpivot` so there is no self-join) — now a
  localized change to `val_int__csv_code_pairs` / the macro. These violation
  models are transitive ancestors of Silver Core and Gold, so they **cannot** be
  excluded with `--select +tag:gold` because that selector pulls ancestors in.
- The Phase-2 Gold **comparison/benchmark marts** (`gld__service_price_comparison_current`,
  `gld__service_price_summary`, `gld__hospital_service_benchmarks`,
  `gld__payer_service_benchmarks`) and the `gld_int__service_comparison_spine` also
  can exceed the same temp budget over the full corpus because their peer-window
  functions sort the whole observation-by-code surface. Durable fix: a larger
  machine, or pre-aggregating/partitioning the window inputs.

## billing_class is absent corpus-wide (comparability framework relaxed)

- No hospital in the active Nashville corpus publishes `billing_class` (confirmed:
  zero occurrences of `"billing_class"` in the source MRFs; `raw_billing_class` is
  null at the bronze layer for all 12 hospitals, JSON and CSV). The parser maps the
  column but publishers never populate it; `clean_setting` publishes fine.
- The decision 0017 tier rule (`hpt_comparison_tier`) originally required
  `clean_billing_class is not null` for `tier_2_context_aligned`, so under the strict
  rule **0%** of observations are cross-hospital comparable and the entire
  comparison/summary/benchmark output is empty. Empty marts still satisfy
  structural `not_null`/`unique` tests, so the semantic problem needs explicit
  coverage.
- Current behavior (in `gld_core__rate_observations`): coalesce `clean_billing_class`
  to `'unspecified'` so its *uniform* absence is treated as an explicit context
  rather than collapsing tier_2. This yields ~57% tier_2. Durable options: make
  `billing_class` optional in the tier definition (an explicit decision 0017
  amendment) or require it only when a corpus actually publishes it. The relaxed
  comparisons mix professional/facility where hospitals would otherwise distinguish
  them — acceptable here only because *no* hospital in the corpus distinguishes them.

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
  one-hospital scoped run: the peer hospital count never clears the 3-hospital
  floor, so published stats stay null and rows carry
  `below_min_hospital_denominator`. Scoped runs smoke-test mechanics only;
  validating published percentiles and deltas needs a multi-hospital corpus.
- The `gld__service_price_comparison_current` ratio columns
  (`gross_to_cash_ratio`, `cash_to_negotiated_ratio`) are computed per charge-item
  context in the mart per open question §14.2 ("a couple of guarded ratio columns
  in the mart now; dedicated model later"). Promote to a dedicated
  `gld__cash_vs_negotiated` model if the cross-amount-kind logic grows.
