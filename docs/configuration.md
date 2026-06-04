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
| `HPT_STAGING_FILTER_ENABLED` | dbt staging filter macro | `true` | Hard on/off switch for applying `LIMIT` or `USING SAMPLE` to staging source reads. This is read directly by the macro and cannot be overridden by macro arguments. |
| `HPT_STAGING_FILTER_METHOD` | dbt `hpt_staging_filter_method` var | `limit` | Default staging source filter method. Use `limit` or `sample`; individual macro calls may override this with `method='LIMIT'` or `method='SAMPLE'`. |
| `hpt_staging_filter_sample_mode` | dbt `hpt_staging_filter_sample_mode` var | `rows` | Default sampling mode when the filter method is `sample`. Use `rows` for row-count sampling or `percent` for Bernoulli percentage sampling. |
| `HPT_STAGING_FILTER_ROWS` | dbt `hpt_staging_filter_rows` var | `100000` | Default row count for `LIMIT` and row-count sampling. `stg_bronze__payers_information` overrides this to `1000000`. |
| `hpt_staging_filter_sample_percentage` | dbt `hpt_staging_filter_sample_percentage` var | `10` | Default percentage when `HPT_STAGING_FILTER_METHOD=sample` and `hpt_staging_filter_sample_mode=percent`. |

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

Staging models apply DuckDB `LIMIT` or `USING SAMPLE` filters to Bronze source
reads by default. Set `HPT_STAGING_FILTER_ENABLED=false` to disable the filter.
The default method is `limit` with `HPT_STAGING_FILTER_ROWS=100000`, except for
`stg_bronze__payers_information`, which uses `1000000` rows. Set
`HPT_STAGING_FILTER_METHOD=sample` to use sampling instead. For sampling,
`hpt_staging_filter_sample_mode=rows` uses row-count sampling and
`hpt_staging_filter_sample_mode=percent` with `hpt_staging_filter_sample_percentage=<number>`
uses Bernoulli percentage sampling.
