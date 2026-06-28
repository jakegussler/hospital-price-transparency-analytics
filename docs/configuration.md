# Runtime Configuration

HPT keeps runtime configuration as small immutable dataclasses in
`hpt.ingest.config`.

- `ClientConfig`: HTTP timeout, retry, and user-agent settings.
- `StorageConfig`: raw source, Bronze, quarantine, and audit roots.
- `ReferenceStorageConfig`: raw and Bronze roots for external reference data.
- `DownloadConfig`: download target, registry path, storage, client, and run flags.
- `IngestConfig`: ingest target, registry path, and storage roots.
- `HPT_REGISTRY_PATH` is also used by the hospitals seed export command.

## Environment Variables

| Variable | Config | Default | Notes |
|---|---|---|---|
| `HPT_RAW_STORAGE_BASE_URI` | `StorageConfig.raw_base_uri` | canonical project `data` root as absolute `file:///...` URI | fsspec URI for raw downloads and snapshot metadata. |
| `HPT_BRONZE_ROOT` | `StorageConfig.bronze_root` and dbt Bronze source definitions | `<project_root>/data/bronze` for Python, `../data/bronze` from `transform/` for dbt | Parsed Bronze Parquet root written by ingest and read by dbt external sources. |
| `HPT_QUARANTINE_ROOT` | `StorageConfig.quarantine_root` | `<project_root>/data/quarantine` | Parser validation failure output root. |
| `HPT_AUDIT_ROOT` | `StorageConfig.audit_root` | `<project_root>/data/audit` | Append-only Parquet records for audited command invocations and attempts. |
| `HPT_REFERENCE_ROOT` | `ReferenceStorageConfig.reference_root` | `<project_root>/data/reference/bronze` | Bronze Parquet root written by `hpt load-reference` and read by dbt reference sources. |
| `HPT_REFERENCE_RAW_ROOT` | `ReferenceStorageConfig.raw_root` | `<project_root>/data/reference/raw` | Cached raw archives and extracted members for external reference data. |
| `HPT_REGISTRY_PATH` | `DownloadConfig.registry_path`, `IngestConfig.registry_path`, hospitals seed export | bundled registry | Optional registry file override. |
| `HPT_HTTP_CONNECT_TIMEOUT` | `ClientConfig.connect_timeout_s` | `10` | HTTP connect timeout in seconds. |
| `HPT_HTTP_READ_TIMEOUT` | `ClientConfig.read_timeout_s` | `300` | HTTP read timeout in seconds. |
| `HPT_HTTP_TIMEOUT` | `ClientConfig.timeout_s` | `60` | Default HTTP timeout in seconds. |
| `HPT_HTTP_RETRIES` | `ClientConfig.retries` | `3` | HTTP transport retry count. |
| `HPT_USER_AGENT` | `ClientConfig.user_agent` | `hpt-pipeline/0.1` | User-Agent sent to publishers. |
| `HPT_DUCKDB_PATH` | dbt `profiles.yml` | `../data/hpt.duckdb` from `transform/` | DuckDB database path used by dbt. |
| `HPT_SILVER_RETENTION_MODE` | dbt `hpt_silver_retention_mode` var and `hpt run-dbt` retention behavior | `current_only` | Use `current_only` to prune non-current snapshot rows after materializing dbt runs, or `all_snapshots` to retain accumulated Silver/validation history while still syncing snapshot current flags from Bronze. |

## Important Distinction

`StorageConfig.raw_base_uri` is for source files and snapshot metadata managed
by `BronzeStorage`. `StorageConfig.bronze_root` is for normalized parsed Bronze
tables written by `BronzeWriter`.

## Storage Root Precedence

For ingest/download config construction, storage roots are resolved with
this precedence:

1. Explicit function argument (for example CLI `--raw-base-uri`).
2. Environment variable (`HPT_RAW_STORAGE_BASE_URI`, `HPT_BRONZE_ROOT`,
   `HPT_QUARANTINE_ROOT`, `HPT_AUDIT_ROOT`, `HPT_REFERENCE_ROOT`, or
   `HPT_REFERENCE_RAW_ROOT`).
3. Canonical project defaults rooted at `<project_root>/data`.

`HPT_RAW_STORAGE_BASE_URI` accepts any fsspec-compatible URI
(`file:///...`, `s3://...`, `gs://...`), so cloud migration remains a config
change instead of a code rewrite.

## dbt And DuckDB

The dbt project in `transform/` uses `transform/profiles.yml`. It reads
`HPT_DUCKDB_PATH` for the local DuckDB database, `HPT_BRONZE_ROOT` for external
Bronze Parquet sources, and `HPT_AUDIT_ROOT` for external operational audit
sources. Python uses the same root names, so one override points writers and dbt
reads at the same directories for local development.

Before invoking dbt, `hpt run-dbt` ensures every declared Bronze source table
has a zero-row schema sentinel under
`{HPT_BRONZE_ROOT}/{table}/snapshot_id=__bootstrap__/_schema.parquet`. This
prevents DuckDB `read_parquet` globs from failing when the local corpus contains
only JSON or only CSV snapshots. The Bronze root must be writable for dbt runs,
and `snapshot_id=__bootstrap__` is reserved for these operational files. The
bootstrap refuses to run until at least one real `hospital_mrf_snapshots`
Parquet file exists.

Staging models are canonical, unscoped views over Bronze source relations.
Snapshot-scoped runs pass the `snapshot_ids` dbt var so `hpt_scoped_ref()` and
`hpt_scoped_source()` can push a `snapshot_id in (...)` predicate into
snapshot-grained consumer queries and let DuckDB prune Bronze hive partitions.
Repeat incremental materializing runs require a non-empty `snapshot_ids` scope;
the custom `snapshot_replace` strategy rejects unscoped execution rather than
risk leaving stale rows when a model produces zero rows.

Snapshot-grained Silver and validation models are incremental. A true rebuild
from all Bronze requires both of the following:

1. No `snapshot_ids` dbt var.
2. dbt `--full-refresh`.

Use `hpt run-dbt --full-rebuild` for that path. Normal scoped incremental runs
should use `hpt run-dbt --hospital-ids ...` or
`hpt run-dbt --snapshot-ids ...`; the runner rejects scoped `--full-refresh`
because it would replace incremental tables with only the scoped rows.
Per-snapshot full refresh accepts `--selector` and refreshes the first snapshot
for each selected graph. Callers are responsible for selecting a coherent set
of snapshot-grained dependencies.
