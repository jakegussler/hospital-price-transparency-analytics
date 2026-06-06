# Agent Guide

This file gives coding agents project context. Keep it aligned with the docs in
`docs/`; future Cursor rules should be distilled from this guide rather than
invented separately.

## Project Purpose

Hospital Price Transparency ingests CMS hospital MRFs, tracks source-file
snapshots, parses JSON and CSV layouts into Bronze Parquet, and prepares the data
for dbt/DuckDB normalization and analysis.

## Current Architecture

- `src/hpt/cli.py` exposes `hpt download`, `hpt ingest`, and `hpt run-dbt`. It is
  a thin layer that builds config objects and runs a process.
- `src/hpt/ingest/` owns config, HTTP download, raw storage, compression,
  snapshot metadata, format detection, and schema sniffing.
- `src/hpt/parsers/` owns JSON, CSV Tall, CSV Wide, and header parsing.
- `src/hpt/loaders/parquet.py` writes Bronze Parquet partitions.
- `src/hpt/pipeline/ingest_snapshot.py` connects snapshot resolution, parser
  selection, quarantine handling, and Bronze writing.
- `src/hpt/pipeline/dbt_config.py`, `dbt_manager.py`, and `dbt_orchestrator.py`
  form the dbt orchestration layer: `DbtRunConfig` holds the run details and
  normalizes comma-separated inputs to lists, `DbtManager` wraps `dbtRunner`
  invocations, and `DbtOrchestrator` sequences the run modes (scoped,
  all-current, per-snapshot, full-rebuild) and iterates selectors.
- `src/hpt/registry/` owns the active bundled hospital registry schema.
- `transform/` is a dbt project targeting DuckDB. It defines Bronze sources and
  Silver foundation models; Gold models are planned.
- `infra/`, `orchestration/`, and `scripts/` are placeholders unless files are
  added later.

## Development Commands

```bash
pip install -e ".[dev,warehouse]"
make test
make lint
make format
hpt download --help
hpt ingest --help
cd transform && dbt run --profiles-dir .
```

Use `hpt ingest` for parsing. Do not document or call `hpt parse` unless the CLI
is changed to provide it.

## Data And Storage Rules

- Treat `data/` as local runtime output; it is ignored by git.
- Raw files and snapshot metadata are rooted at `HPT_RAW_STORAGE_BASE_URI`.
- Parsed Bronze Parquet is rooted at `HPT_BRONZE_ROOT` for both Python ingest
  output and dbt external sources.
- Quarantine records are rooted at `HPT_QUARANTINE_ROOT`.
- DuckDB defaults to `data/hpt.duckdb` through `HPT_DUCKDB_PATH`.
- `fsspec` support is intentional; avoid hard-coding local-only storage paths in
  ingest/download code.

## Domain Rules

- Bronze is source-faithful. Do not add business normalization, payer matching,
  code rollups, or hospital identity resolution in Bronze parsers.
- Python handles structural parsing: JSON streaming, CSV header extraction, CSV
  Wide unpivoting, and pipe-delimited header fields.
- dbt handles semantic normalization in Silver and analytics-ready models in
  Gold.
- Preserve raw CMS values where possible, including odd nulls, duplicate rows,
  mixed code systems, and payer/plan strings.
- Snapshot lineage matters. Keep `snapshot_id`, `file_hash`, source URL, source
  filename, and ingest timestamps intact through downstream layers.

## Documentation Rules

- Update `README.md` when setup, top-level commands, or project status changes.
- Update `docs/configuration.md` when environment variables or config precedence
  changes.
- Update `docs/architecture/` when pipeline boundaries, storage layout, or
  medallion responsibilities change.
- Update `docs/domain/` when CMS schema handling, registry rules, or terminology
  changes.
- Update `docs/development/` when commands, tests, debugging workflows, or
  tooling expectations change.
- Record unresolved follow-ups, risks, or known mismatches in `docs/cleanup.md`
  unless fixing them in the same change. Do not use it for general architecture
  notes or status summaries.

## Testing Expectations

- Add or update pytest coverage for parser behavior, snapshot/storage changes,
  registry validation, and CLI/pipeline changes.
- For dbt work, add dbt tests alongside models where practical.
- For docs-only changes, verify links and commands against the actual source
  tree.

## Domain Reference Documents

These documents exist to orient agents working with HPT data semantics. Do not
pull them in for structural or tooling tasks (parser changes, CLI work, storage
layout, test setup). Use them when you need to understand what the data means,
not how it is stored.

**`docs/local/industry_guide.md`** — HPT industry concepts: charge types (gross,
discounted cash, payer-negotiated, min/max), CMS MRF schema intent, code systems,
and how hospital pricing works in practice. Consult this when:
- Building or reviewing Silver/Gold dbt models that interpret charge semantics
  (e.g., `slv_base__standard_charges`, charge-item grain, price normalization).
- Writing dbt tests or accepted-value constraints for charge type or code type
  fields and you are unsure what values are valid or meaningful.
- Analyzing data and a field's purpose or expected range is unclear from the
  column name alone.

**`docs/local/methodologies_algorithms.md`** — How each `methodology` value works,
why `standard_charge_dollar` is sometimes populated on percentage-based contracts,
and how compound `other`-methodology algorithm text encodes multi-component contracts.
Consult this when:
- Modeling or filtering the `methodology`, `negotiated_dollar`,
  `negotiated_percentage`, or `negotiated_algorithm` fields in
  `slv_base__payer_rates` or downstream Gold models.
- Writing logic that classifies, aggregates, or compares payer rates across
  methodology types (e.g., joining fee-schedule rows against percent-of-charges
  rows requires knowing they are not the same measurement).
- Parsing or extracting sub-rules from `standard_charge_algorithm` text for the
  `other` methodology.

**`docs/cms_reference/`** — The CMS-published hospital price transparency
specification files cloned from the official CMS repository. Consult this when:
- The exact CMS-defined field names, allowed values, or schema version behavior
  matters for a Bronze source definition or Silver staging model.
- A question about what CMS requires vs. what hospitals actually provide needs
  a ground-truth reference.

## Cautions

- Do not commit local data, DuckDB files, logs, or downloaded MRFs.
- Do not treat `docs/notes/` as authoritative. It contains planning history and
  research notes.
- Be explicit when describing planned components such as Airflow, Docker,
  Terraform, Silver, or Gold. Do not imply they are production-ready.
