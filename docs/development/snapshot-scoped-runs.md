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

Bidirectional reconciliation tests apply the same `snapshot_ids` filter to
their accumulated Silver side during scoped runs. Unscoped builds still compare
the complete Bronze and Silver datasets.

When you call `hpt_snapshot_filter()` inside a join where more than one table
exposes `snapshot_id`, pass the driving table's alias
(e.g. `hpt_snapshot_filter('sc')`) to avoid an ambiguous-column error.

## Running it

```bash
# Seed once (charge/validation models depend on seeds).
make dbt-seed

# Resolve hospitals to their current snapshots and build the coherent dbt graph.
hpt run-dbt --hospital-ids ballad-jcmc --command build
# or:
make dbt-run-hospitals HOSPITAL_IDS=ballad-jcmc
make dbt-incremental HOSPITAL_IDS=ballad-jcmc

# Pin explicit historical snapshots, or mix both. Inputs are merged + deduped.
hpt run-dbt --snapshot-ids 7ca24003-...,209991a1-... --command build
hpt run-dbt --hospital-ids a,b --snapshot-ids 7ca24003-... --command run --no-seeds
```

`hpt run-dbt` flags: `--hospital-ids` (resolved to each hospital's current
snapshot), `--snapshot-ids` (pinned explicitly), `--command` (default `build`),
`--selector` (optional; use only for an intentionally partial run; a
comma-separated list runs each selector in turn),
`--all-hospitals` (scope every registry hospital's current snapshot into one
run), `--per-snapshot` (iterate every current snapshot one run at a time),
`--full-refresh` (per-snapshot only; see below), `--full-rebuild`,
`--seeds/--no-seeds`, `--log-level`. It exits non-zero if no snapshot IDs
resolve, if dbt fails, or if the post-run retention operation fails.

Do not pass `--full-refresh` through a scoped `hpt run-dbt` invocation. The
runner rejects that combination because dbt would rebuild incremental tables
from only the scoped rows. Use the full rebuild path instead:

```bash
make dbt-rebuild
# or:
hpt run-dbt --full-rebuild
```

The full rebuild path runs with no `snapshot_ids` var and passes dbt
`--full-refresh`.

### Per-snapshot iteration

`--per-snapshot` builds every hospital's current snapshot, but invokes dbt once
per snapshot instead of scoping them all into a single run, which bounds peak
memory on large registries. `--seeds` seeds once up front; the stale-snapshot
prune runs once after every snapshot is built.

`--full-refresh` is allowed here (unlike a plain scoped run) and applies dbt
`--full-refresh` to the **first** snapshot only, rebuilding the complete graph
from scratch so later snapshots append incrementally rather than overwriting.
It cannot be combined with `--selector`: a partial full refresh would replace
selected parent tables and scoped staging views while leaving unselected
siblings and downstream models stale.

```bash
# Rebuild incremental tables from scratch, then append each remaining snapshot.
hpt run-dbt --per-snapshot --full-refresh --seeds
```

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

## Clearing a snapshot

A `build` that fails partway can leave a snapshot partially materialized: some
snapshot-grained tables have its rows, others do not. `hpt clear-snapshot`
removes a snapshot cleanly so it can be rebuilt:

```bash
hpt clear-snapshot --snapshot-ids <snapshot-id>
```

It runs the `hpt_clear_snapshots` operation, which is the mirror of
`hpt_prune_stale_snapshots`: both iterate the same
`hpt_snapshot_grained_incremental_models()` list and delete by `snapshot_id`,
but clear deletes the rows that *are* the targeted snapshot(s) instead of the
rows that are *not* current. Table-materialized models (`slv_base__hospitals`,
`slv_core__*`, `slv_review_queue__*`) are excluded on purpose — they are
`CREATE OR REPLACE` and self-heal on the next run. Only warehouse rows are
touched; raw files, snapshot metadata, and Bronze partitions are left intact, so
re-running dbt for the snapshot rebuilds it.

Staging views are also intentionally untouched. A snapshot-scoped dbt invocation
persists its `snapshot_id` filter in each staging view definition, so after a
failed per-snapshot run the staging views continue to show the snapshot that was
being processed when the run failed. That does not mean the clear failed; verify
the clear against snapshot-grained Silver or validation tables. The next coherent
dbt build replaces the staging views with that build's scope.

To clear automatically when a materializing run fails, pass
`hpt run-dbt --clear-on-failure`. Per-snapshot runs clear the failing snapshot;
single-pass scoped runs clear the whole scoped set. The clear fires only on a
`build`/`run` failure — not on a seed or post-run prune failure, since those do
not leave a half-written snapshot.

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
  build only updates that subgraph; models and scoped staging views outside it
  keep their previous rows or previous `snapshot_id` filter. Cross-model
  `reconcile_*` / `relationships_*` tests can flag the mismatch, and selected
  models can read stale unselected views. Omit `--selector` for a coherent
  scoped update; partition pruning still bounds memory.
- **Seed mapping changes require explicit reprocessing.** Updating
  `payer_aliases`, `payer_context_rules`, or `canonical_payers` does not
  retro-apply to already materialized `slv_core__payer_rates` rows. Reprocess
  affected snapshots explicitly, or run a full rebuild.
- See `docs/cleanup.md` for the known `reconcile_csv_rows_to_standard_charges`
  data gap that scoping surfaces.
