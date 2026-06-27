# AI Context

This is a compact project context pack for AI agents. Prefer the longer docs for
details; use this file to quickly orient before editing.

## Mission

Build a reproducible hospital price transparency pipeline from CMS MRF source
files to local analytical models.

## Current Pipeline

```text
registry -> hpt download -> raw files + snapshot metadata -> hpt ingest
         -> Bronze Parquet -> dbt/DuckDB -> validation + Silver -> Gold
```

## Key Source Areas

- `src/hpt/cli.py`: Typer CLI with `download` and `ingest`.
- `src/hpt/ingest/`: config, download, storage, snapshot, detection,
  compression, schema sniffing.
- `src/hpt/parsers/`: JSON, CSV Tall, CSV Wide, and header parsing.
- `src/hpt/loaders/parquet.py`: Bronze Parquet writer.
- `src/hpt/pipeline/ingest_snapshot.py`: ingest orchestration.
- `src/hpt/registry/`: active registry loader, models, and bundled registry.
- `transform/`: dbt project targeting DuckDB (Bronze sources, Silver models, and
  the implemented Gold layer in `main_gold`).
- `tests/`: pytest coverage for current Python behavior.

## Important Constraints

- Bronze is source-faithful and should not contain business normalization.
- Python handles structural parsing; dbt handles Silver/Gold semantics.
- dbt staging views are canonical and unscoped; snapshot-grained consumers own
  run scoping through `hpt_scoped_ref()` and `hpt_scoped_source()`.
- Raw storage and snapshot metadata use `fsspec`.
- Local runtime data under `data/` should not be committed.
- `docs/notes/` is historical source material, not the primary current docs.
- Airflow, Docker, and Terraform are planned or skeletal unless implementation
  files are added. Silver foundation models and the Gold layer (Phase 1
  dimensions/fact/bridge/coverage scorecard + Phase 2 marts/benchmarks) are
  implemented; the Gold contract is decisions 0017/0018 and
  `docs/architecture/gold-schema.md`.

## Useful References

- `README.md`
- `AGENTS.md`
- `docs/architecture/pipeline-overview.md`
- `docs/architecture/medallion-layers.md`
- `docs/architecture/silver-schema.md`
- `docs/architecture/gold-schema.md`
- `docs/architecture/storage-layout.md`
- `docs/domain/hpt-glossary.md`
- `docs/domain/cms-mrf-schema-notes.md`
- `docs/domain/cms-validation-rules.md`
- `docs/domain/hospital-registry-rules.md`
- `docs/development/getting-started.md`
- `docs/development/testing-strategy.md`
- `docs/development/common-debugging-notes.md`
- `docs/cleanup.md`
