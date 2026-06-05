# Snapshot-Scoped dbt Runs

The pricing pipeline can exhaust memory when dbt scans every Bronze snapshot at
once. Snapshot scoping restricts a dbt run to one or more `snapshot_id`s so
DuckDB prunes Bronze hive partitions instead of reading the whole corpus.
Snapshot-grained Silver and validation tables are incremental, so scoped runs
replace rows for the selected snapshots and preserve unrelated retained rows.

## How it works

Staging models read Bronze source relations directly. One macro handles
snapshot scoping through the `snapshot_ids` dbt var:

- `hpt_snapshot_filter(table_alias=None)` emits
  `and <alias>.snapshot_id in (...)` in staging `WHERE` clauses when
  `snapshot_ids` is non-empty (otherwise nothing).

Scoped runs read the *full* data for the selected snapshots, with no row cap,
but only those partitions. Unscoped direct dbt runs read all available Bronze
partitions.

When you call `hpt_snapshot_filter()` inside a join where more than one table
exposes `snapshot_id`, pass the driving table's alias
(e.g. `hpt_snapshot_filter('sc')`) to avoid an ambiguous-column error.

## Running it

```bash
# Seed once (charge/validation models depend on seeds).
make dbt-seed

# Resolve hospitals to their current snapshots and build the charge pipeline.
hpt run-dbt --hospital-ids ballad-jcmc --command build --selector pipeline_charge_data
# or:
make dbt-run-hospitals HOSPITAL_IDS=ballad-jcmc
make dbt-incremental HOSPITAL_IDS=ballad-jcmc

# Pin explicit historical snapshots, or mix both. Inputs are merged + deduped.
hpt run-dbt --snapshot-ids 7ca24003-...,209991a1-... --command build
hpt run-dbt --hospital-ids a,b --snapshot-ids 7ca24003-... --command run --no-seeds
```

`hpt run-dbt` flags: `--hospital-ids` (resolved to each hospital's current
snapshot), `--snapshot-ids` (pinned explicitly), `--command` (default `build`),
`--selector` (default `pipeline_charge_data`; pass `""` to disable),
`--full-rebuild`, `--seeds/--no-seeds`, `--log-level`. It exits non-zero if no
snapshot IDs resolve, if dbt fails, or if the post-run retention operation
fails.

Do not pass `--full-refresh` through a scoped `hpt run-dbt` invocation. The
runner rejects that combination because dbt would rebuild incremental tables
from only the scoped rows. Use the full rebuild path instead:

```bash
make dbt-rebuild
# or:
hpt run-dbt --full-rebuild --selector ""
```

The full rebuild path runs with no `snapshot_ids` var and passes dbt
`--full-refresh`.

## Retention

`HPT_SILVER_RETENTION_MODE` controls the final retained rows after
materializing runs:

- `current_only` (default) runs `hpt_prune_stale_snapshots` after successful
  `build` or `run` commands. The prune reads current snapshot IDs directly from
  Bronze `hospital_mrf_snapshots`, not from incremental Silver metadata.
- `all_snapshots` skips pruning and keeps accumulated Silver/validation rows.
  The retention operation still syncs `slv_base__hospital_snapshots` current
  flags from Bronze.

Bronze Parquet is never pruned by this setting.

### Verify the scope landed

```bash
cd transform && dbt show --profiles-dir . --inline \
  "select snapshot_id, count(*) from {{ ref('slv_base__payer_rates') }} group by 1"
```

In `current_only` mode, you should see the retained current snapshot rows. In
`all_snapshots` mode, historical snapshot rows remain accumulated.

## Things to know

- **Unit tests are excluded.** `hpt run-dbt` adds
  `--exclude-resource-type unit_test` for `build`/`test`. Unit-test fixtures pin
  their own `snapshot_id`s, which the filter would strip. Run the full unit-test
  suite unscoped via `make dbt-build` / CI.
- **Cross-snapshot history requires `all_snapshots`.** Default `current_only`
  mode prunes non-current snapshot rows after materializing runs. To compare
  historical snapshots in Silver, set `HPT_SILVER_RETENTION_MODE=all_snapshots`
  before building those snapshots.
- **Partial selectors can leave stale neighbors.** A scoped `pipeline_charge_data`
  build only updates that subgraph; models outside it keep their previous rows.
  Cross-model `reconcile_*` / `relationships_*` tests can flag the mismatch. For
  a fully coherent scoped update, scope the whole graph (`--selector ""`) —
  partition pruning still bounds memory.
- **Seed mapping changes require explicit reprocessing.** Updating
  `payer_aliases`, `payer_context_rules`, or `canonical_payers` does not
  retro-apply to already materialized `slv_core__payer_rates` rows. Reprocess
  affected snapshots explicitly, or run a full rebuild.
- See `docs/cleanup.md` for the known `reconcile_csv_rows_to_standard_charges`
  data gap that scoping surfaces.
