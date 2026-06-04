# Cleanup And Alignment Notes

This file tracks known inconsistencies discovered while building project
documentation. These are not fixed by the documentation pass unless explicitly
called out in a later implementation task.

## Transform Alignment

- Gold dbt directories exist but do not contain production models yet. (leave
  this for now)
- Silver Base, Silver Core, and review queue models are implemented and
  documented in `docs/architecture/silver-schema.md`.
- The JSON streaming parser validates individual `standard_charge_information`
  and `modifier_information` objects structurally, but it still does not run the
  root `CMSMRFJson` model over entire files. Header/root required-shape gaps are
  therefore surfaced through Bronze header rows and dbt validation rather than
  parser quarantine.
- The Bronze layer materializes empty Parquet files for optional tables a
  parser emits but that have no rows (e.g. a snapshot without
  `general_contract_provisions`), so their partition directory always exists.
  Format-specific tables a parser never emits at all (e.g. `csv_charge_rows`
  for a JSON-only corpus) can still produce an empty-glob `read_parquet` error
  in staging; ingest at least one file of each format, or guard those sources,
  before running dbt.

## Snapshot Scoping Notes

- `hpt_staging_source` (limit/sample) and `snapshot_ids` scoping are mutually
  exclusive by precedence: when the `snapshot_ids` var is non-empty, the staging
  macro emits the bare relation so the `hpt_snapshot_filter()` `WHERE` clause can
  prune Bronze hive partitions. The limit/sample dev guard only applies to
  unscoped runs.
- Snapshot-scoped runs (`hpt run-dbt`) exclude dbt **unit tests**
  (`--exclude-resource-type unit_test`). Unit-test fixtures pin their own
  `snapshot_id` values, which the snapshot filter would strip; they are
  snapshot-agnostic logic checks and still run fully under unscoped
  `make dbt-build` / CI.
- Cross-model integrity tests (`reconcile_*`, cross-model `relationships_*`) can
  fail under a **partial** scoped selector (e.g. `pipeline_charge_data`) when a
  referenced model lives outside the selector and therefore retains a different
  snapshot's data from a prior build (e.g. `slv_base__type2_npis` vs a freshly
  scoped `slv_base__hospital_snapshots`). For a fully coherent rebuild, run the
  scoped build over the whole graph (no `--selector`); partition pruning still
  bounds memory.
- `reconcile_csv_rows_to_standard_charges` reports a small number of CSV charge
  rows (8 observed for `ballad-jcmc`) that map to no Silver standard charge and
  are not captured by any rejection model. This is a real source-data gap that
  the dev-default staging `limit` previously masked; snapshot scoping (full
  scan, no limit) surfaces it. Not yet root-caused.

## Planning Notes

- `docs/notes/` contains useful historical planning and research, but it should
  not be treated as the primary onboarding path.
- Some planning notes describe Airflow, MinIO, Metabase, Docker Compose, and
  Terraform as future architecture. The current repo contains placeholders, not
  active implementations for those systems.

## Script Notes

- Some ad hoc scripts may be useful references but are not maintained as stable
  command-line tools. (this is fine for the scripts in adhoc/scripts)
