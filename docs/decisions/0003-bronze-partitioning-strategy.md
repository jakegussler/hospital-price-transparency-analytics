# 0003: Bronze Partitioning Strategy

Status: accepted

## Context

The pipeline needs predictable storage paths for raw files, snapshot metadata,
and parsed Bronze tables. The layout should support lineage, incremental
ingestion, and easy DuckDB/dbt reads.

## Decision

Use Hive-style path segments for raw files and parsed Bronze output:

```text
raw/hospital_id={hospital_id}/ingested_at={YYYY-MM-DD}/{filename}
metadata/hospital_mrf_snapshots/hospital_id={hospital_id}/{snapshot_id}.parquet
bronze/{table}/snapshot_id={snapshot_id}/part-NNN.parquet
```

## Rationale

Partitioning raw files by hospital and ingest date makes source artifacts easy
to inspect. Partitioning Bronze tables by `snapshot_id` preserves lineage and
lets DuckDB read partition columns through Hive partitioning.

## Consequences

- `snapshot_id` is the primary lineage key for parsed Bronze tables.
- Bronze table directories should remain stable because dbt external sources
  depend on them.
- If raw path partitioning changes, snapshot resolution logic and docs must be
  updated together.
- Silver models can use `snapshot_id` to trace normalized rows back to source
  files.
