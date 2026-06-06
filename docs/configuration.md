# Runtime Configuration

HPT keeps runtime configuration as small immutable dataclasses in
`hpt.ingest.config`.

- `ClientConfig`: HTTP timeout, retry, and user-agent settings.
- `StorageConfig`: raw source storage, parsed Bronze output, and quarantine roots.
- `DownloadConfig`: download target, registry path, storage, client, and run flags.
- `IngestConfig`: ingest target, registry path, and storage roots.
- `HPT_REGISTRY_PATH` is also used by the hospitals seed export command.

## Environment Variables

| Variable | Config | Default | Notes |
|---|---|---|---|
| `HPT_RAW_STORAGE_BASE_URI` | `StorageConfig.raw_base_uri` | canonical project `data` root as absolute `file:///...` URI | fsspec URI for raw downloads and snapshot metadata. |
| `HPT_BRONZE_ROOT` | `StorageConfig.bronze_root` and dbt Bronze source definitions | `<project_root>/data/bronze` for Python, `../data/bronze` from `transform/` for dbt | Parsed Bronze Parquet root written by ingest and read by dbt external sources. |
| `HPT_QUARANTINE_ROOT` | `StorageConfig.quarantine_root` | `<project_root>/data/quarantine` | Parser validation failure output root. |
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
   `HPT_QUARANTINE_ROOT`).
3. Canonical project defaults rooted at `<project_root>/data`.

`HPT_RAW_STORAGE_BASE_URI` accepts any fsspec-compatible URI
(`file:///...`, `s3://...`, `gs://...`), so cloud migration remains a config
change instead of a code rewrite.

## dbt And DuckDB

The dbt project in `transform/` uses `transform/profiles.yml`. It reads
`HPT_DUCKDB_PATH` for the local DuckDB database and `HPT_BRONZE_ROOT` for
external Bronze Parquet sources. Python ingest uses the same `HPT_BRONZE_ROOT`
name, so a single override points both ingest output and dbt reads at the same
Bronze directory for local development.

Staging models read Bronze source relations directly. Snapshot-scoped runs pass
the `snapshot_ids` dbt var so `hpt_snapshot_filter()` can push a
`snapshot_id in (...)` predicate into staging queries and let DuckDB prune
Bronze hive partitions. Unscoped direct dbt runs scan all available Bronze
partitions.

Snapshot-grained Silver and validation models are incremental. A true rebuild
from all Bronze requires both of the following:

1. No `snapshot_ids` dbt var.
2. dbt `--full-refresh`.

Use `make dbt-rebuild` or `hpt run-dbt --full-rebuild` for that path. Normal
scoped incremental runs should use `hpt run-dbt --hospital-ids ...` or
`hpt run-dbt --snapshot-ids ...`; the runner rejects scoped `--full-refresh`
because it would replace incremental tables with only the scoped rows.
Per-snapshot full refresh is supported only without `--selector`, so all scoped
staging views and dependent models are rebuilt together.
