# Pipeline Overview

The implemented pipeline has two Python CLI phases followed by a dbt/DuckDB
modeling phase.

```mermaid
flowchart LR
  registry[HospitalRegistry] --> download[Download]
  download --> rawFiles[RawMRFFiles]
  download --> snapshotMeta[SnapshotMetadata]
  snapshotMeta --> ingest[Ingest]
  rawFiles --> ingest
  ingest --> bronze[BronzeParquet]
  bronze --> dbt[dbtDuckDB]
  dbt --> silver[SilverModels]
  silver --> gold[GoldModels]
```

## Implemented Components

`hpt download` reads hospital sources from the active registry, streams each MRF
URL to temporary storage, hashes the bytes, compares the hash to the current
snapshot, and writes a new raw file plus Type-2 snapshot metadata only when the
source changed.

Important modules:

- `src/hpt/cli.py`
- `src/hpt/ingest/download.py`
- `src/hpt/ingest/client.py`
- `src/hpt/ingest/storage.py`
- `src/hpt/ingest/snapshot.py`
- `src/hpt/registry/loader.py`

`hpt ingest` resolves each hospital's current snapshot, materializes compressed
files when needed, sniffs the MRF layout, selects a parser, writes Bronze Parquet
batches, and sends validation failures to quarantine.

Important modules:

- `src/hpt/pipeline/ingest_snapshot.py`
- `src/hpt/ingest/mrf_sniffer.py`
- `src/hpt/ingest/compression.py`
- `src/hpt/parsers/json_mrf.py`
- `src/hpt/parsers/csv_tall.py`
- `src/hpt/parsers/csv_wide.py`
- `src/hpt/loaders/parquet.py`

`transform/` is the dbt project. It defines external Bronze Parquet sources for
DuckDB, staging views, validation models, Silver Base/Core models, and review
queue models. Snapshot-grained Silver and validation tables are incremental;
Gold models are still planned.

## Download Flow

```mermaid
flowchart TD
  cliDownload[hptDownload] --> loadRegistry[LoadRegistry]
  loadRegistry --> streamFile[StreamSourceFile]
  streamFile --> hashFile[ComputeSHA256]
  hashFile --> compareSnapshot[CompareCurrentSnapshot]
  compareSnapshot --> unchanged[UnchangedResult]
  compareSnapshot --> changed[WriteRawFile]
  changed --> detectFormat[DetectFormat]
  detectFormat --> writeSnapshot[WriteSnapshotRecord]
```

Key behavior:

- The registry controls which hospitals and URLs are targeted.
- File hashes prevent duplicate snapshots when downloaded bytes are unchanged.
- Raw storage and snapshot metadata share the same `fsspec` base URI.
- The `--force` flag forces a download attempt, but hash comparison still
  determines whether a new snapshot is written.

## Ingest Flow

```mermaid
flowchart TD
  cliIngest[hptIngest] --> currentSnapshot[GetCurrentSnapshot]
  currentSnapshot --> resolveRaw[ResolveRawPath]
  resolveRaw --> prepare[PrepareParserPath]
  prepare --> sniff[SniffLayout]
  sniff --> parser[SelectParser]
  parser --> batches[YieldPolarsBatches]
  batches --> writer[WriteBronzeParquet]
  parser --> quarantine[WriteQuarantineRecords]
```

Key behavior:

- Ingest operates on current snapshot metadata, not directly on arbitrary files.
- Compressed raw archives remain intact; parser-ready copies are materialized
  under temporary storage when needed.
- Parser outputs are grouped by Bronze table name.
- `BronzeWriter` writes partitioned Parquet parts under the Bronze root.

## Transform Flow

dbt reads Bronze Parquet through `dbt-duckdb` external source definitions in
`transform/models/staging/_bronze_sources.yml`.

Implemented behavior:

- Staging views read Bronze sources without changing grain.
- Snapshot-grained Silver and validation tables use dbt incremental
  `delete+insert` keyed by `snapshot_id`, so scoped dbt runs replace the current
  batch without dropping unrelated snapshots.
- `HPT_SILVER_RETENTION_MODE=current_only` is the default product mode. After a
  successful `hpt run-dbt` materializing run, dbt prunes rows whose
  `snapshot_id` is no longer current according to Bronze
  `hospital_mrf_snapshots`.
- `HPT_SILVER_RETENTION_MODE=all_snapshots` keeps accumulated Silver and
  validation rows for historical analysis.
- Review queue models and cross-snapshot validation summaries remain
  full-refresh tables because their distinct counts span all retained Silver
  rows.
- Gold tables will answer analysis questions such as price variation, hospital
  comparisons, payer comparisons, and compliance reporting.

## Boundaries

Python owns source acquisition, source tracking, structural parsing, and Bronze
file writing. dbt owns semantic normalization and analytics models. Airflow,
Docker, and Terraform folders exist as planned integration points, not active
runtime dependencies.
