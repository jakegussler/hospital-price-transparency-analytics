# 0006: Model All Snapshots In Silver

Status: amended by `docs/planning/incremental-implementation-plan.md`

## Amendment

The original lineage decision still holds for Bronze: parsed Bronze Parquet
preserves all snapshots. Silver and validation are now configurable:

- `HPT_SILVER_RETENTION_MODE=current_only` is the default product mode and
  prunes non-current snapshot rows after materializing dbt runs.
- `HPT_SILVER_RETENTION_MODE=all_snapshots` keeps accumulated Silver and
  validation history when historical analysis or parser regression work needs
  it.

Snapshot-grained Silver models still use `snapshot_id` as the incremental batch
key and preserve source lineage for retained rows.

Price history itself is out of v1 scope (decision 0016); `all_snapshots` and the
`snapshot_id` lineage are retained as the seam an adopter accumulating
longitudinal data would build on, not because v1 ships a history product. The
default `current_only` mode reflects that the shipped analytics goal is current
cross-hospital comparison.

## Context

The downloader records file-level snapshots, and Bronze Parquet is physically
partitioned by `snapshot_id`. DuckDB and dbt can read each Bronze table directory
as one logical table while retaining partition pruning when a snapshot filter is
applied early.

The project needs historical comparison, incremental loading, and lineage back
to individual source files. Modeling only the current snapshot would make the
first queries simpler but would discard the structure needed for those goals.

## Original Decision

Silver models were originally planned to include all snapshots by default.
Current-only views or Gold models could be built on top when a use case only
needed the latest file per hospital. The amendment above replaces that default
with configurable Silver/validation retention.

Use `snapshot_id` as the unit of lineage, reconciliation, and future incremental
work.

## Rationale

MRF files are immutable once snapshotted. A changed file hash creates a new
snapshot, which gives the pipeline a natural batch boundary. Keeping every
snapshot in Silver makes price changes, source drift, and backfills analyzable
without special history tables.

This also keeps full-refresh and incremental dbt logic aligned: both read the
same Bronze source definitions, and incremental models can later restrict work
to new or selected snapshots.

## Consequences

- Silver primary and foreign keys for snapshot-scoped entities should include or
  derive from `snapshot_id`.
- dbt staging models should preserve `snapshot_id` from Bronze sources.
- Development filters should be pushed into early CTEs so DuckDB can prune
  partitioned Parquet files.
- `is_current_snapshot` should be treated as an attribute for current-only
  views, not as a default filter in base Silver. It is now a derived attribute
  computed in dbt by `hpt_resolved_snapshot_state_sql` from `valid_from` recency
  rather than stored in Bronze; see `docs/architecture/storage-layout.md` and
  `docs/architecture/silver-schema.md`.
- Snapshot-scoped Silver IDs should not be reused as cross-snapshot canonical
  service item IDs.
