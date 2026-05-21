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
- `valid_to`
- `is_current_snapshot`

The metadata behaves like a Type-2 slowly changing dimension. A new snapshot is
created when downloaded file bytes differ from the current snapshot hash.

## Bronze Parquet

Parsed Bronze Parquet is written by `BronzeWriter` under
`HPT_PARSED_BRONZE_ROOT`.

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

## Local vs Future Object Storage

`HPT_RAW_STORAGE_BASE_URI` accepts `fsspec` URIs such as `file://`, `s3://`, and
`gs://`. Keep raw and metadata operations storage-abstracted so the project can
move from local development to object storage without rewriting the pipeline.

Parsed Bronze output is currently path-based local Parquet output. If Bronze
moves to object storage later, update `BronzeWriter`, dbt external source paths,
and this document together.
