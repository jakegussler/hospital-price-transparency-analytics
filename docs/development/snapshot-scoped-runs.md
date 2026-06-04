# Snapshot-Scoped dbt Runs

The pricing pipeline can exhaust memory when dbt scans every Bronze snapshot at
once. Snapshot scoping restricts a dbt run to one or more `snapshot_id`s so
DuckDB prunes Bronze hive partitions instead of reading the whole corpus.

## How it works

Two macros cooperate through the `snapshot_ids` dbt var:

- `hpt_snapshot_filter(table_alias=None)` emits
  `and <alias>.snapshot_id in (...)` in staging `WHERE` clauses when
  `snapshot_ids` is non-empty (otherwise nothing).
- `hpt_staging_source(...)` checks `snapshot_ids` **first**. When it is set, the
  macro emits the bare relation so the filter's predicate reaches the
  `read_parquet(...)` scan and prunes partitions. When it is empty, the usual
  dev-default `limit`/`using sample` guard applies
  (`HPT_STAGING_FILTER_ENABLED`).

So scoping and the limit/sample guard are mutually exclusive: a scoped run reads
the *full* data for the selected snapshots, with no row cap, but only those
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

# Pin explicit historical snapshots, or mix both. Inputs are merged + deduped.
hpt run-dbt --snapshot-ids 7ca24003-...,209991a1-... --command build
hpt run-dbt --hospital-ids a,b --snapshot-ids 7ca24003-... --command run --no-seeds
```

`hpt run-dbt` flags: `--hospital-ids` (resolved to each hospital's current
snapshot), `--snapshot-ids` (pinned explicitly), `--command` (default `build`),
`--selector` (default `pipeline_charge_data`; pass `""` to disable),
`--seeds/--no-seeds`, `--log-level`. It exits non-zero if no snapshot IDs
resolve or if dbt fails.

### Verify the scope landed

```bash
cd transform && dbt show --profiles-dir . --inline \
  "select snapshot_id, count(*) from {{ ref('slv_base__payer_rates') }} group by 1"
```

You should see exactly the snapshot(s) you passed.

## Things to know

- **Unit tests are excluded.** `hpt run-dbt` adds
  `--exclude-resource-type unit_test` for `build`/`test`. Unit-test fixtures pin
  their own `snapshot_id`s, which the filter would strip. Run the full unit-test
  suite unscoped via `make dbt-build` / CI.
- **Cross-snapshot analysis must happen in one invocation.** Silver models are
  `materialized: table` and CTAS-replace each run, so a run scoped to snapshot A
  overwrites a prior run scoped to B. To compare A and B, pass both:
  `--snapshot-ids A,B`.
- **Partial selectors can leave stale neighbors.** A scoped `pipeline_charge_data`
  build only rebuilds that subgraph; models outside it keep their previous
  snapshot's rows. Cross-model `reconcile_*` / `relationships_*` tests then flag
  the mismatch. For a fully coherent rebuild, scope the whole graph
  (`--selector ""`) — partition pruning still bounds memory.
- See `docs/cleanup.md` for the known `reconcile_csv_rows_to_standard_charges`
  data gap that scoping surfaces.
