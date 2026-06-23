# Snapshot-Scoped dbt Runs

The pricing pipeline can exhaust memory when dbt scans every Bronze snapshot at
once. Snapshot scoping restricts a dbt run to one or more `snapshot_id`s so
DuckDB prunes Bronze hive partitions instead of reading the whole corpus.
Snapshot-grained Silver and validation tables are incremental, so scoped runs
replace rows for the selected snapshots and preserve unrelated retained rows.

## How it works

Staging models are canonical, unscoped views over Bronze and always expose every
available snapshot. Snapshot-grained consumers own run scoping through two
input macros:

- `hpt_scoped_ref(model_name)` wraps a snapshot-grained model input.
- `hpt_scoped_source(source_name, table_name)` wraps a Bronze source input.

Both wrappers call `hpt_snapshot_filter()` inside a derived table. When
`snapshot_ids` is non-empty, the predicate prunes Bronze hive partitions and
limits accumulated-table reads to the requested batch. With no `snapshot_ids`,
the wrappers read all snapshots.

Scoped runs read the *full* data for the selected snapshots, with no row cap.
Staging remains stable for exploration before and after scoped runs.
Snapshot-grained incremental models use `snapshot_replace`, which deletes the
explicitly requested snapshot rows before inserting the new model result. This
also replaces a snapshot with zero rows. Repeat incremental materializing runs
without `snapshot_ids` fail; use the explicit full-rebuild path for unscoped
replacement.

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
comma-separated list runs each selector in turn), `--select` (model node
selection with dbt graph operators; see below; mutually exclusive with
`--selector`), `--all-hospitals` (scope every registry hospital's current
snapshot into one run), `--per-snapshot` (iterate every current snapshot one run
at a time), `--full-refresh` (per-snapshot only; see below), `--full-rebuild`,
`--defer-tests` (split `build` into a materialize pass plus one test pass; see
below), `--seeds/--no-seeds`, `--log-level`. It exits non-zero if no snapshot IDs
resolve, if dbt fails, or if the post-run retention operation fails.

### Node selection with `--select`

`--select` scopes the run to specific model nodes instead of a named selector,
passing dbt's graph-operator syntax through verbatim:

```bash
# Just one model, scoped to one snapshot (fast inner-loop check).
hpt run-dbt --snapshot-ids 97e28644-... --command build --select slv_core__payer_rates

# The model and everything downstream of it.
hpt run-dbt --snapshot-ids 97e28644-... --command build --select slv_core__payer_rates+

# A union of several nodes in a single invocation.
hpt run-dbt --snapshot-ids 97e28644-... --command run --select slv_base__payer_rates+ slv_core__charge_items
```

Comma-separated nodes become a single union `--select` (one invocation), unlike
comma-separated `--selector` values, which run one at a time. `--select` and
`--selector` are mutually exclusive — dbt would intersect them. A bare
`--select model` leaves downstream models computed from the old logic; use
`model+` when your change affects them. Node selection is the preferred scope for
validating a small, known set of changed models: it rebuilds exactly what you
touched and bounds wall-clock time. Peak memory is still governed by the snapshot
scope, not the number of nodes, so keep the snapshot pin small.

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
`--full-refresh` to the **first** snapshot for each selector, rebuilding the
selected graph from scratch so later snapshots append incrementally rather than
overwriting. Partial selectors are allowed, but callers are responsible for
choosing a selector whose selected parents and downstream models can be
refreshed coherently.

```bash
# Rebuild incremental tables from scratch, then append each remaining snapshot.
hpt run-dbt --per-snapshot --full-refresh --seeds

# Rebuild only the selected graph one snapshot at a time.
hpt run-dbt --per-snapshot --full-refresh --selector per_snapshot
```

### Deferred testing with `--defer-tests`

dbt `build` interleaves each model with its tests. Generic tests (`not_null`,
`accepted_values`, `relationships`, `unique_combination_of_columns`) defined in
the `_*.yml` files run against the **whole** materialized table, not just the
scoped snapshot. So a multi-snapshot `build` re-tests every already-built
snapshot after each new one — roughly `N`× the necessary test work on an `N`-
snapshot rebuild. (Singular tests in `transform/tests/*.sql` already scope
themselves via `hpt_scoped_ref`, so they are not the cost here.)

`--defer-tests` splits a `build` into two phases: it materializes every snapshot
with `run` (no interleaved tests), runs the stale-snapshot prune, then runs a
single **unscoped** `test` pass over the whole, now-consistent table. This turns
`O(N²)` test scans into `O(N)` and is the recommended default for multi-snapshot
and full-refresh rebuilds.

```bash
# Rebuild every current snapshot, then test once at the end.
hpt run-dbt --per-snapshot --defer-tests

# Same, scoped to one model graph.
hpt run-dbt --per-snapshot --defer-tests --select slv_core__payer_rates+
```

Trade-off: you lose `build`'s interleaved fail-fast for **data-quality** tests —
a constraint violation in snapshot 3's data is reported only after every snapshot
is materialized. **Structural** failures (SQL/compile/schema errors) still abort
the materialize loop immediately, so a model that cannot build stops the run at
once. `--clear-on-failure` still applies to the materialize phase. `--defer-tests`
only applies to `build`; combining it with another command raises an error.

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

## Re-ingesting a snapshot

A successful scoped rebuild replaces the requested snapshot in every selected
snapshot-grained model, including models whose new result contains zero rows.
Normal re-ingests therefore do not require `hpt clear-snapshot` before dbt.
Rows left stale by older `delete+insert` runs self-heal the next time their
snapshot is rebuilt; known affected snapshots should receive a scoped rebuild
after deploying `snapshot_replace`.

This warehouse replacement guarantee is separate from Bronze file replacement.
Bronze snapshot partitions are not yet atomically replaced when re-ingested; see
`docs/cleanup.md` for that remaining storage risk.

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
`slv_core__service_items`, `slv_review_queue__*`) are excluded on purpose —
they are `CREATE OR REPLACE` and self-heal on the next run. Only warehouse rows
are touched; raw files, snapshot metadata, and Bronze partitions are left
intact, so re-running dbt for the snapshot rebuilds it.

Staging views are also intentionally untouched. They are canonical, unscoped
views over Bronze, so they continue to expose every available snapshot before
and after a clear. Verify the clear against snapshot-grained Silver or validation
tables.

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
  suite unscoped via `make dbt-unit-test` / CI.
- **Cross-snapshot history requires `all_snapshots`.** Default `current_only`
  mode prunes non-current snapshot rows after materializing runs. To compare
  historical snapshots in Silver, set `HPT_SILVER_RETENTION_MODE=all_snapshots`
  before building those snapshots.
- **Partial selectors can leave stale neighbors.** A scoped `pipeline_charge_data`
  build only updates that subgraph; snapshot-grained models outside it keep
  their previous rows. Cross-model `reconcile_*` / `relationships_*` tests can
  flag the mismatch. Omit `--selector` for a coherent scoped update; partition
  pruning still bounds memory.
- **Seed mapping changes require explicit reprocessing.** Updating
  `payer_aliases`, `payer_context_rules`, or `canonical_payers` does not
  retro-apply to already materialized `slv_core__payer_rates` rows. Reprocess
  affected snapshots explicitly, or run a full rebuild.
- See `docs/cleanup.md` for the known `reconcile_csv_rows_to_standard_charges`
  data gap that scoping surfaces.
