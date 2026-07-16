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

## Warehouse resource scaling

- Validation over large mixed-format corpora can exceed the memory or temp-spill
  budget of a developer workstation. `transform/profiles.yml` therefore keeps
  the default thread count at `1`, bounds temp storage, and exposes the memory,
  thread, and spill settings as deployment-time environment variables.
- The validation grain is materialized once in `val_int__standard_charge_grain`,
  `val_int__code_grain`, and `val_int__csv_code_pairs`, and violation rules are
  evaluated in a single pass. Hospital-batched or per-snapshot builds remain the
  supported way to bound peak resources as the registry grows.
- If CSV-wide code expansion remains a bottleneck at larger scale, fuse the two
  per-ordinal unpivots in `hpt_csv_code_unpivot` to remove the self-join in
  `val_int__csv_code_pairs`. Validation models are transitive ancestors of
  Silver Core and Gold, so they cannot be excluded from a complete downstream
  build.
- The Phase-2 Gold **comparison/benchmark marts** (`gld_mart__service_price_comparison_current`,
  `gld_mart__service_price_summary`, `gld_mart__hospital_service_benchmarks`,
  `gld_mart__payer_service_benchmarks`) and the `gld_int__service_comparison_spine` also
  can exceed the same temp budget over the full corpus because their peer-window
  functions sort the whole observation-by-code surface. Durable fix: a larger
  machine, or pre-aggregating/partitioning the window inputs.

## `billing_class` is absent in the profiled sample

- No hospital in the profiled 12-hospital Nashville sample publishes
  `billing_class` (confirmed: zero occurrences of `"billing_class"` in the source
  MRFs; `raw_billing_class` is null at the Bronze layer for JSON and CSV). The
  parser maps the column, so future sources that publish it remain supported.
- The decision 0017 tier rule (`hpt_comparison_tier`) originally required
  `clean_billing_class is not null` for `tier_2_context_aligned`, so under the strict
  rule **0%** of observations are cross-hospital comparable and the entire
  comparison/summary/benchmark output is empty. Empty marts still satisfy
  structural `not_null`/`unique` tests, so the semantic problem needs explicit
  coverage.
- Current behavior (in `gld_fct__rate_observations`) coalesces
  `clean_billing_class` to `'unspecified'`, so uniform absence is represented
  explicitly rather than collapsing tier 2. This assumption must be re-profiled
  as the corpus expands. Durable options are to make `billing_class` optional in
  the tier definition through a decision 0017 amendment, or require it only when
  publishers in the comparison corpus distinguish it.

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
- The `gld_mart__service_price_comparison_current` ratio columns
  (`gross_to_cash_ratio`, `cash_to_negotiated_ratio`) are computed per charge-item
  context in the mart per open question §14.2 ("a couple of guarded ratio columns
  in the mart now; dedicated model later"). Promote to a dedicated
  `gld__cash_vs_negotiated` model if the cross-amount-kind logic grows.

## Decision 0021 rollout follow-ups (2026-07-15)

- The methodology-separated, hospital-weighted refactor (decision 0021) was
  verified on an 8-hospital corpus (nashville-general, williamson-medical-center,
  tristar-northcrest, tristar-ashland-city, tristar-summit, tristar-skyline,
  tristar-hendersonville, tristar-stonecrest) built on an external drive
  (`/Volumes/Primary/hpt/data`). The full 14-hospital corpus rebuild is planned
  for AWS with the same per-snapshot sequence; rerun the MS-DRG 003 regression
  audit and the corpus-wide P10-constant audit there.
- Ambiguous multi-amount contract/contexts (the
  `multiple_amounts_per_contract_context` blocker) often hide a revenue-code or
  network distinction the comparison key does not model. Profile the co-code
  patterns on the full corpus and decide whether a revenue-code context
  component would recover a material share of the excluded contracts.
- `contract_identity_precision = 'payer_only'` collapses all plan-less rates of
  one payer+methodology into one contract. Safe today (multi-amount collapse is
  quarantined), but re-profile as the corpus grows: a payer publishing many
  plan-less contracts would inflate ambiguity exclusions rather than mix rates.
- The Evidence exact-context route (`/compare/context/[service_context_url_slug]`)
  is prerendered only for floor-met contexts reachable through links. If a
  full exact-context index ever becomes affordable at build time, revisit
  page coverage for below-floor contexts.
- 8-hospital audit findings (2026-07-15): the named regression is fixed — zero
  comparable MS-DRG contexts show a P10 of $1,947 (previously 87.5%), MS-DRG 003
  splits into case-rate / fee-schedule / per-diem cohorts at 6 hospitals each,
  and the 56 United/VACCN repetitions collapse to one contract vote. Ambiguous
  contract share is 0.8–2% per hospital except williamson-medical-center at
  7.2% (csv_wide) — profile its multi-amount patterns before the AWS rebuild.
  Repeated per-diem P10 constants across many contexts (e.g. $1,176.878 in
  1,273 contexts) are expected: one payer's daily rate legitimately covers many
  DRGs; they are now confined to per-diem cohorts.
- Pre-existing stale dbt unit test: `charge_item_schema_version_mismatch_warns_once`
  (transform/models/validation/_validation_unit_tests.yml) errors with a missing
  `gross_charge` column in its fixture; the model evolved after the fixture was
  written. Unrelated to decision 0021; fix the fixture to the current schema.
- Evidence source size: on the 8-hospital corpus, `payer_contracting_explorer`
  is ~1.3 GB uncompressed at ingest (1.0M rows after the methodology grain
  split) and `npm run sources` needs `NODE_OPTIONS=--max-old-space-size=6144`.
  Evidence warns about client-side performance. Before the full AWS corpus,
  either prune the payer explorer's public column set, pre-aggregate the
  payer-page views, or split the mart by payer for lazy loading.

## Evidence public reporting redesign follow-ups (2026-07-07)

- The 3-hospital dev corpus (nashville-general, tristar-northcrest,
  williamson-medical-center) has **zero cross-hospital exact-context overlap**:
  every `gld_bi__service_market_explorer` row has `hospital_count = 1`, so all
  contexts are `insufficient_denominator`, `gld_bi__featured_services` is
  empty, and comparability-funnel stage 5 is 0. The public pages render honest
  empty states for this, but it is worth investigating whether systematic
  context-label differences (setting/billing-class labeling across the three
  source formats) prevent overlap that should exist, versus the corpus simply
  being too small.
- Evidence static builds prerender only param pages reachable through links in
  rendered tables. Unlinked `/compare/[service_slug]` deep links 404 on a plain
  static host; the deploy target needs a fallback rewrite (documented in
  `apps/evidence/README.md`). Revisit if a full service index page (linking all
  slugs) becomes affordable at build time.
- The plan's "glossary coverage" QA idea (automated diff of rendered enum
  values vs. `/glossary` anchors) is not implemented; today the mapping is
  maintained by hand in page SQL label cases and the glossary page.
- `scripts/check_evidence_readiness.py` gates on `featured_services >= 1 row`,
  which legitimately fails on corpora with no floor-met contexts (like the
  current dev corpus). That is by design for public-demo gating, but do not
  treat its failure as a pipeline bug on small corpora.
