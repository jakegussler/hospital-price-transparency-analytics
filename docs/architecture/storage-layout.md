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
```

Each invocation writes a `started` run-state record and a terminal `completed`
record. A run with no completed record is reported as `running_or_interrupted`.
Attempts record one hospital download, one hospital/snapshot ingest, or one
concrete dbt invocation. Audit writes are fail-closed: a command does not report
success when its audit record cannot be persisted.

The audit data is outside Bronze and Silver but can be queried directly:

```sql
select *
from read_parquet('data/audit/runs/**/*.parquet', hive_partitioning = true)
where terminal_status in ('failed', 'partial');

select a.run_id, a.snapshot_id, a.attempt_type, a.bronze_row_counts
from read_parquet('data/audit/attempts/**/*.parquet', hive_partitioning = true) a
where a.snapshot_id = '<snapshot-id>'
order by a.started_at;
```

Snapshot-grained Silver and validation tables inside DuckDB are incremental
dbt tables. Normal scoped runs replace rows for the requested `snapshot_id`s
using `delete+insert`; they do not recreate the table from only that scoped
batch.

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
