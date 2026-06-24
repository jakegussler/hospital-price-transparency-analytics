# Storage Layout

The pipeline separates source storage, parsed Bronze output, quarantine output,
and the local analytical database.

## Default Local Roots

By default, runtime files live under `data/`:

```text
data/
  raw/
  metadata/
  bronze/
  quarantine/
  audit/
  hpt.duckdb
```

`data/` is ignored by git.

## Raw Files

Raw MRF files are managed by `BronzeStorage` under
`HPT_RAW_STORAGE_BASE_URI`.

Path pattern:

```text
{raw_base_uri}/raw/hospital_id={hospital_id}/ingested_at={YYYY-MM-DD}/{filename}
```

Raw files are the downloaded source artifacts. They may be plain JSON, plain CSV,
gzip, or zip archives. Download-time storage should preserve the source artifact;
ingest can materialize parser-ready temporary files when needed.

## Snapshot Metadata

Snapshot records are also managed under `HPT_RAW_STORAGE_BASE_URI`.

Path pattern:

```text
{raw_base_uri}/metadata/hospital_mrf_snapshots/hospital_id={hospital_id}/{snapshot_id}.parquet
```

Snapshot metadata tracks:

- `snapshot_id`
- `hospital_id`
- `source_url`
- `source_file_name`
- `file_hash`
- `ingested_at`
- `valid_from`

Snapshot metadata is **append-only**: a new snapshot is written when downloaded
file bytes differ from the latest snapshot hash, and prior records are left
untouched. Currentness is not stored — dbt derives `is_current_snapshot` and
`valid_to` downstream from `valid_from` recency per hospital. Python resolves
"the latest snapshot" by the same recency ordering so ingest knows which file to
parse.

## Bronze Parquet

Parsed Bronze Parquet is written by `BronzeWriter` under
`HPT_BRONZE_ROOT`.

Path pattern:

```text
{bronze_root}/{table}/snapshot_id={snapshot_id}/part-NNN.parquet
```

Before dbt runs, `hpt run-dbt` also maintains one operational, zero-row schema
sentinel for every declared Bronze source:

```text
{bronze_root}/{table}/snapshot_id=__bootstrap__/_schema.parquet
```

The reserved bootstrap partition guarantees that every DuckDB source glob
matches at least one schema-compatible file even when the local corpus contains
only one source format. Because each sentinel has zero rows, it does not create
a snapshot or contribute Bronze facts.

The dbt project reads the same files through `HPT_BRONZE_ROOT`, defaulting to
`../data/bronze` from inside `transform/`.

Current and expected Bronze table families:

- Shared: `hospital_mrf_snapshots`, `hospital_locations`, `type2_npi`.
- JSON: `standard_charge_info`, `code_information`, `drug_information`,
  `standard_charges`, `standard_charge_modifiers`, `payers_information`,
  `modifiers`, `modifier_payer_info`.
- CSV: `csv_charge_rows`.

## Quarantine

Parser validation failures are written under `HPT_QUARANTINE_ROOT`.

Quarantine records should be treated as diagnostic output. They are useful for
understanding source-specific schema problems and deciding whether parser logic
needs to be expanded.

## DuckDB

DuckDB is configured by the dbt profile in `transform/profiles.yml`.

Default path:

```text
data/hpt.duckdb
```

Environment variable:

```text
HPT_DUCKDB_PATH
```

DuckDB should read Bronze Parquet through dbt external source definitions rather
than by copying Bronze data into ad hoc local tables.

## Run Audit

`hpt download`, `hpt ingest`, and `hpt run-dbt` write append-only Parquet under
`HPT_AUDIT_ROOT`:

```text
{audit_root}/runs/run_date=YYYY-MM-DD/*.parquet
{audit_root}/attempts/run_date=YYYY-MM-DD/*.parquet
{audit_root}/node_results/run_date=YYYY-MM-DD/*.parquet
{audit_root}/runs/run_date=1970-01-01/_schema.parquet
{audit_root}/attempts/run_date=1970-01-01/_schema.parquet
{audit_root}/node_results/run_date=1970-01-01/_schema.parquet
```

Three grains, finest last:

- **runs** — one CLI invocation. Each writes a `started` run-state record and a
  terminal `completed` record; a run with no completed record is reported as
  `running_or_interrupted`.
- **attempts** — one hospital download, one hospital/snapshot ingest, or one
  concrete dbt invocation (command × selector × snapshot-batch). dbt attempts
  also carry `peak_rss_mb`, the per-invoke peak resident memory sampled while
  dbt/DuckDB ran in-process.
- **node_results** — one dbt node (model/test/seed/snapshot) per dbt invocation,
  keyed by `(attempt_id, node_unique_id)`. Carries per-model timing
  (`execution_time_s`, plus a compile/execute split), `node_status`,
  `rows_affected`, test `failures`, and the denormalized invoke context
  (command, selector, snapshot scope). Harvested directly from the in-process
  `dbtRunner` result, not from logs or `run_results.json`. Capture is
  non-fatal — a harvest failure never fails the dbt run — and run-operations
  (which have no real node) are skipped.

Audit writes are fail-closed: a command does not report success when its run or
attempt record cannot be persisted (node-result capture is the exception, being
best-effort observability).

On the first audit append, `AuditStore` atomically creates zero-row schema
sentinels for every dataset. They keep all three Parquet sources queryable before
the first record is written and do not contribute rows.

The audit data is outside the Bronze/Silver/Gold medallion flow. It can be
queried directly or through the unscoped dbt views in DuckDB schema
`main_audit`:

```sql
select *
from read_parquet('data/audit/runs/**/*.parquet', hive_partitioning = true)
where terminal_status in ('failed', 'partial');

select a.run_id, a.snapshot_id, a.attempt_type, a.bronze_row_counts
from read_parquet('data/audit/attempts/**/*.parquet', hive_partitioning = true) a
where a.snapshot_id = '<snapshot-id>'
order by a.started_at;
```

The dbt `audit` tag builds source-faithful staging views, one-row-per-run,
one-row-per-attempt, and one-row-per-node marts (`audit__node_results`), plus
long-form stage/count detail views. `audit__node_results` adds a
`row_count_semantics` label so `rows_affected` is read correctly per
materialization (full-table rebuild count vs. incremental delta vs. n/a for
views vs. test-failure rows) instead of being summed across incompatible grains.
All audit models remain views so newly completed command records are immediately
visible.

Snapshot-grained Silver and validation tables inside DuckDB are incremental
dbt tables. Normal scoped runs replace rows for the requested `snapshot_id`s
using the custom `snapshot_replace` strategy; they do not recreate the table
from only that scoped batch. Replacement uses the requested scope rather than
the model output, so a zero-row model result removes prior rows for that
snapshot.

Retention is a dbt/runtime choice:

- `HPT_SILVER_RETENTION_MODE=current_only` keeps only rows for current Bronze
  snapshots after the post-run retention operation.
- `HPT_SILVER_RETENTION_MODE=all_snapshots` keeps accumulated Silver and
  validation history.

Use `make dbt-rebuild` for a true full-refresh rebuild from all Bronze Parquet.
That path runs dbt `--full-refresh` without a `snapshot_ids` var.

## Local vs Future Object Storage

`HPT_RAW_STORAGE_BASE_URI` accepts `fsspec` URIs such as `file://`, `s3://`, and
`gs://`. Keep raw and metadata operations storage-abstracted so the project can
move from local development to object storage without rewriting the pipeline.

Parsed Bronze output is currently path-based local Parquet output. If Bronze
moves to object storage later, update `BronzeWriter`, dbt external source paths,
and this document together.
