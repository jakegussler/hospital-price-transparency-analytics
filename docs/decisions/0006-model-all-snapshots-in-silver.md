# 0006: Model All Snapshots In Silver

Status: accepted

## Context

The downloader records file-level snapshots, and Bronze Parquet is physically
partitioned by `snapshot_id`. DuckDB and dbt can read each Bronze table directory
as one logical table while retaining partition pruning when a snapshot filter is
applied early.

The project needs historical comparison, incremental loading, and lineage back
to individual source files. Modeling only the current snapshot would make the
first queries simpler but would discard the structure needed for those goals.

## Decision

Silver models include all snapshots by default. Current-only views or Gold
models can be built on top when a use case only needs the latest file per
hospital.

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
  views, not as a default filter in base Silver.
- Snapshot-scoped Silver IDs should not be reused as cross-snapshot canonical
  service item IDs.
