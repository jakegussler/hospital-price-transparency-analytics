# Common Debugging Notes

## `hpt ingest` Cannot Find A Snapshot

Check that `hpt download` completed for the hospital first. Ingest reads current
snapshot metadata; it does not scan arbitrary raw files as the source of truth.

Useful checks:

- Confirm the hospital ID exists in the active registry.
- Confirm `HPT_RAW_STORAGE_BASE_URI` is the same for download and ingest.
- Check `data/metadata/hospital_mrf_snapshots/` for snapshot parquet files.

## Download Reports `unchanged`

`unchanged` means the downloaded bytes hash to the same SHA-256 value as the
current snapshot. This can happen even with `--force`; force controls the
download attempt, not whether a duplicate snapshot is written.

## Raw Root And Bronze Root Are Confused

There are two separate storage concepts:

- `HPT_RAW_STORAGE_BASE_URI` stores raw files and snapshot metadata through
  `BronzeStorage`.
- `HPT_BRONZE_ROOT` stores parsed Bronze Parquet written by `BronzeWriter` and
  read by dbt external sources.

Use `--bronze-root` when a one-off ingest run needs a different parsed Bronze
output directory.

## Compressed Files Fail During Ingest

Raw compressed archives should remain intact. Ingest materializes a parser-ready
temporary file when needed.

Check:

- The detected compression type.
- Whether the archive contains an expected JSON or CSV member.
- Whether temporary files under the raw storage root can be created and cleaned
  up.

## Parser Selection Looks Wrong

Parser selection depends on sniffed layout, not just the registry hint.

Check:

- `src/hpt/ingest/detect.py` for coarse file/content detection.
- `src/hpt/ingest/mrf_sniffer.py` for JSON vs CSV Tall vs CSV Wide layout.
- The first rows of CSV files, especially row 3 charge headers.
- JSON top-level keys and `standard_charge_information` shape.

## Quarantine Records Appear

Quarantine records usually indicate row-level validation failures. Inspect them
to decide whether:

- The source file contains invalid data that should remain quarantined.
- The parser or Pydantic model is too strict.
- The source exposes a CMS-permitted optional shape that is not implemented yet.

## dbt Cannot Read Bronze

Check:

- `HPT_BRONZE_ROOT` points to the parsed Bronze root.
- The expected table directories exist under `data/bronze`.
- Parquet files are partitioned as `table/snapshot_id=.../part-NNN.parquet`.
- Commands are run from `transform/` with `--profiles-dir .` if using the local
  checked-in profile.

## Registry Override Is Ignored

Use either the CLI flag:

```bash
hpt download --registry-path path/to/hospitals.yml
hpt ingest --registry-path path/to/hospitals.yml
```

or the environment variable:

```bash
export HPT_REGISTRY_PATH=path/to/hospitals.yml
```

Confirm the file follows the active registry model in `src/hpt/registry/models.py`.

