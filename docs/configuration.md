# Runtime Configuration

HPT keeps runtime configuration as small immutable dataclasses in
`hpt.ingest.config`.

- `ClientConfig`: HTTP timeout, retry, and user-agent settings.
- `StorageConfig`: raw source storage, parsed Bronze output, and quarantine roots.
- `DownloadConfig`: download target, registry path, storage, client, and run flags.
- `IngestConfig`: ingest target, registry path, and storage roots.

## Environment Variables

| Variable | Config | Default | Notes |
|---|---|---|---|
| `HPT_RAW_STORAGE_BASE_URI` | `StorageConfig.raw_base_uri` | `file://./data` | fsspec URI for raw downloads and snapshot metadata. |
| `HPT_PARSED_BRONZE_ROOT` | `StorageConfig.bronze_root` | `data/bronze` | Parsed Bronze Parquet output root. |
| `HPT_QUARANTINE_ROOT` | `StorageConfig.quarantine_root` | `data/quarantine` | Parser validation failure output root. |
| `HPT_REGISTRY_PATH` | `DownloadConfig.registry_path`, `IngestConfig.registry_path` | bundled registry | Optional registry file override. |
| `HPT_HTTP_CONNECT_TIMEOUT` | `ClientConfig.connect_timeout_s` | `10` | HTTP connect timeout in seconds. |
| `HPT_HTTP_READ_TIMEOUT` | `ClientConfig.read_timeout_s` | `300` | HTTP read timeout in seconds. |
| `HPT_HTTP_TIMEOUT` | `ClientConfig.timeout_s` | `60` | Default HTTP timeout in seconds. |
| `HPT_HTTP_RETRIES` | `ClientConfig.retries` | `3` | HTTP transport retry count. |
| `HPT_USER_AGENT` | `ClientConfig.user_agent` | `hpt-pipeline/0.1` | User-Agent sent to publishers. |

## Important Distinction

`StorageConfig.raw_base_uri` is for source files and snapshot metadata managed
by `BronzeStorage`. `StorageConfig.bronze_root` is for normalized parsed Bronze
tables written by `BronzeWriter`.
