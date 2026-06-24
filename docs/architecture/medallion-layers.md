# Medallion Layers

The project follows a medallion pattern: Bronze preserves source-faithful parsed
records, dbt validation records CMS conformance issues, Silver normalizes
business entities, and Gold serves analytics.

## Bronze

Status: implemented for JSON, CSV Tall, and CSV Wide parser outputs.

Bronze is a structural representation of source MRFs. It should preserve raw CMS
values and avoid business-level normalization.

Bronze responsibilities:

- Track one `hospital_mrf_snapshots` row per ingested file.
- Preserve source URL, source filename, file hash, snapshot ID, and ingest
  metadata.
- Parse common header fields into `hospital_mrf_snapshots`,
  `hospital_locations`, and `type2_npi`.
- Stream JSON `standard_charge_information` into relational tables that mirror
  the JSON hierarchy.
- Parse CSV Tall charge rows into `csv_charge_rows`.
- Unpivot CSV Wide payer columns into the same `csv_charge_rows` shape.
- Quarantine rows that fail parser validation.

Bronze should not:

- Resolve hospital identity across source files.
- Canonicalize payer or plan names.
- Group CSV rows into charge-item entities.
- Explode code columns into normalized code dimensions.
- Resolve modifier strings to modifier definitions.
- Cast questionable source values into stricter business types when doing so
  would lose source fidelity.

## Validation

Status: implemented in dbt under `models/validation/`.

Validation is the queryable data-quality boundary between Bronze/staging and
Silver. It turns the CMS rule registry into row-level violation tables,
rejection keysets, and monitoring statistics.

Snapshot-grained validation models are materialized incrementally with the
custom `snapshot_replace` strategy on `snapshot_id`. It deletes rows for the
explicitly requested snapshot scope before inserting the model result, including
when that result is empty. Cross-snapshot aggregate statistics such as
`val_stats__rule_summary` remain full-refresh tables because their distinct
counts span the loaded corpus.

Canonical staging views remain unscoped. Snapshot-grained validation consumers
apply the requested `snapshot_ids` scope at their Bronze/staging input boundary.

Validation responsibilities:

- Emit one row per failing value in `val__*_violations` models.
- Attach `rule_id`, severity, grain, diagnostic type, source keys, and CMS
  citation metadata from the `cms_validation_rules` seed.
- Preserve JSON structural quarantine diagnostics as
  `val__structural_parse_violations`.
- Produce `val__*_rejections` keysets that Silver base models anti-join.
- Route exclusions by the emitted entity grain and source keys, not by severity
  alone. File/header findings are report-only; child failures never remove
  parents or siblings.
- Provide summary and monitoring models under `val_stats__*`.

Validation should not:

- Modify Bronze or staging rows.
- Apply payer identity resolution or business normalization.
- Hide warn-severity records from Silver.

See `docs/bronze_layer.md` for the Bronze data dictionary.
See `docs/architecture/bronze-schema.md` for the implemented Bronze schema
diagram.

## Silver

Status: foundation and core implemented. The dbt project has
`models/silver/base/` models that normalize Bronze snapshots, hospitals, charge
items, standard charge contexts, payer rates, codes, NPIs, locations, and
modifiers, and `models/silver/core/` models that add canonical payer identity
plus payer/plan context, billing-code enrichment (match keys, format status,
comparability, NDC canonical-11), modifier and drug-unit reference enrichment,
and deterministic within-hospital cross-snapshot service-item identity
(`slv_core__charge_items` signatures and the `slv_core__service_items`
dimension). Payer/plan context is curated in `payer_context_rules`; where no
rule supplies a structural `plan_type`, `slv_core__payer_rates` falls back to a
deterministic word-boundary token derivation (`hpt_derive_plan_type`) and
records the provenance in `plan_type_basis`
(`payer_context_rule` / `derived_plan_type` / `none`). Plan classification is
enrichment and never gates row inclusion. Data-quality finding views live under
`models/silver/audit/`, including `slv_audit__plan_context_coverage`, which
measures market_segment and plan_type coverage by canonical payer.

Silver converts source-faithful, validation-filtered Bronze data into
normalized analytical entities.

Expected responsibilities:

- Normalize hospital identity from registry and source metadata.
- Normalize charge items and standard charge contexts across JSON and CSV inputs.
- Split and type billing codes from JSON and CSV sources.
- Standardize payer and plan strings where rules are defensible.
- Normalize modifiers and modifier relationships.
- Convert source date strings into typed dates where valid.
- Exclude records that fail reject-severity validation rules while retaining
  enough source keys to trace the exclusion back to Bronze.

Silver should remain close enough to source data that issues can be traced back
to a specific `snapshot_id`, source file, and row or ordinal.

Snapshot-grained Silver Base and Silver Core tables are materialized
incrementally with `snapshot_replace` on `snapshot_id`. Staging remains
canonical unscoped views; snapshot-grained consumers scope their inputs for each
run. The registry-backed `slv_base__hospitals` dimension remains a full-refresh
table, and review queue models remain full-refresh tables because they aggregate
across snapshots. The cross-snapshot `slv_core__service_items` dimension is
likewise a full-refresh table that reads its inputs unscoped and is excluded
from the snapshot prune: it spans snapshots by design, and a snapshot-scoped
run must not shrink it. Under `current_only` retention it builds correctly but
shows `snapshot_count = 1` everywhere; continuity tracking needs
`all_snapshots` retention and multi-snapshot ingestion.

Silver retention is controlled by `HPT_SILVER_RETENTION_MODE`:

- `current_only` (default) prunes non-current `snapshot_id`s from
  snapshot-grained Silver and validation tables after a successful materializing
  dbt run.
- `all_snapshots` keeps accumulated snapshot history in Silver and validation.

Bronze always preserves all parsed snapshots regardless of Silver retention.

See `docs/architecture/silver-schema.md` for the implemented Silver base schema,
including the full pipeline DAG, column schemas, and a comparison against the
2026-05-20 reference image.

## Gold

Status: planned. The dbt project has a `models/gold/` directory, but no
implemented models yet.

Gold will serve use-case-specific analytics. The v1 comparability contract is
decision `docs/decisions/0017-gold-comparability-framework.md`: current
cross-hospital comparison is code-cohort based, context-aligned, dollar-aware,
and explainable through blocker reasons.

Likely responsibilities:

- A rate-observation spine that preserves lineage and exposes amount semantics.
- Current hospital-level price comparison views over comparable code cohorts.
- Payer and market-segment benchmark tables where identity/context gates pass.
- Charge-code and service-context summaries with denominator thresholds.
- Coverage and data-readiness scorecards that explain blocked observations.
- Datasets suitable for dashboards or notebooks.

Gold models can trade some source detail for usability, but they should retain
lineage back to Silver and Bronze identifiers. They should not create a global
service master, canonical plan dimension, price-history mart, basket index,
geography enrichment, or semantic layer in v1.

## Operational Audit

Status: implemented in dbt under `models/audit/`.

Operational audit data records pipeline execution rather than hospital pricing
semantics, so it remains outside the Bronze/Silver/Gold medallion flow. dbt
exposes append-only run, attempt, and node-result Parquet through source-faithful
staging views and operational marts in the `main_audit` DuckDB schema.

Audit models are deliberately unscoped from `snapshot_ids` and materialized as
views. The run mart resolves started/completed events to one row per invocation;
attempt, stage, and output-count marts retain their distinct operational grains.
The `audit__node_results` mart adds per-model performance metrics — one row per
dbt node per invocation (timing, status, row counts) harvested from the
in-process `dbtRunner` result — and dbt attempts carry `peak_rss_mb`, the
per-invoke peak resident memory. Together these answer "how long did each model
take, how much did it write, and how much memory did the run use" across run
arguments and snapshot breadth.

## Layer Ownership

```mermaid
flowchart LR
  raw[RawMRFFiles] --> bronze[BronzeSourceFaithful]
  bronze --> validation[dbtValidation]
  validation --> silver[SilverNormalizedEntities]
  silver --> gold[GoldAnalytics]
```

- Python owns raw acquisition and Bronze structural parsing.
- dbt owns Silver and Gold SQL transformations.
- Python writes operational audit records; dbt exposes operational audit views
  outside the medallion flow.
- DuckDB is the expected local analytical database.
- Airflow, Docker, and Terraform will orchestrate and deploy this flow later.
