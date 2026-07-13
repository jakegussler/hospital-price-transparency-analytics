# Agent Guide

This is the canonical project guidance for AI coding tools and new contributors.
Codex reads it directly; `CLAUDE.md` imports it; Cursor's project rule points to
it. Keep shared rules here rather than duplicating them in tool-specific files.
Use [docs/ai/README.md](docs/ai/README.md) for the design of this AI workflow.

## Project Purpose

Hospital Price Transparency ingests CMS hospital MRFs, tracks source-file
snapshots, parses JSON and CSV layouts into Bronze Parquet, and prepares the data
for dbt/DuckDB normalization and analysis.

## Current Architecture

- `src/hpt/cli.py` exposes `hpt download`, `hpt ingest`, `hpt run-dbt`, and
  `hpt clear-snapshot`; keep the CLI thin.
- `src/hpt/ingest/` owns download, storage, compression, snapshots, format
  detection, and schema sniffing.
- `src/hpt/parsers/` owns JSON, CSV Tall, CSV Wide, and header parsing.
- `src/hpt/loaders/parquet.py` writes Bronze Parquet partitions.
- `src/hpt/pipeline/` connects snapshot resolution, parsing, Bronze writing, and
  the supported dbt run modes.
- `src/hpt/registry/` owns the active bundled hospital registry schema.
- `transform/` is the dbt/DuckDB project: Bronze sources, validation, Silver,
  Gold, and the `gld_bi__*` presentation marts.
- `apps/evidence/` is the static public reporting app. It reads exported Parquet
  from allowlisted BI marts; analytical semantics stay in dbt.
- `infra/` and `orchestration/` are planned integration points, not production
  implementations.

## Development Commands

```bash
pip install -e ".[dev,warehouse]"
make test
make lint
make format
hpt download --help
hpt ingest --help
hpt run-dbt --command build --select slv_core__payer_rates+
```

Use `hpt ingest` for parsing. Do not document or call `hpt parse` unless the CLI
is changed to provide it.

## dbt Agent Rules

- Never invoke `dbt` directly, including `cd transform && dbt ...`.
- Never use Make targets such as `make dbt-run`, `make dbt-test`, `make dbt-build`,
  or `make dbt-rebuild`.
- Always use the `hpt run-dbt` CLI layer.
- For day-to-day iteration, scope the node graph with **either** `--select`
  **or** `--selector` (mutually exclusive). Prefer `--select <changed models>`
  (or `<model>+` to include downstream) over a named selector; it rebuilds
  exactly what you touched. Fall back to `--selector` when a coherent tag group
  is the right unit.
- A fresh warehouse needs `--seeds`; otherwise do not pass `--seeds` unless the
  change affects seed data or seed-dependent behavior.

### Memory at full-corpus scale

The Nashville corpus (14 hospitals across CSV Wide, CSV Tall, and JSON) is large
enough that a single-pass full build can exhaust DuckDB's temp-spill directory.
The validation grain is built once in `val_int__*` table intermediates, but that
grain build can still spill heavily. Bound peak memory with one of:

- **Hospital-batched single-pass builds** — `--hospital-ids <subset>` in batches
  of ~4; `snapshot_replace` accumulates and the final batch's unscoped marts
  cover every loaded snapshot. Uses only scoping flags.
- **`--per-snapshot` / `--full-refresh`** — the orchestrator's purpose-built
  memory-bounding modes (one snapshot at a time). Previously discouraged for
  agents; allowed when a full-corpus rebuild would otherwise OOM.

`preserve_insertion_order: false` in `transform/profiles.yml` reduces spill but
is not sufficient alone. See `docs/cleanup.md` for current operational risks.

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
- Treat ignored material under `docs/planning/`, `docs/local/`, and `docs/ai/`
  as working context, not public or authoritative documentation.
- Keep `AGENTS.md` focused on durable, recurring rules. Put explanations in
  tracked docs and multi-step reusable workflows in `.agents/skills/`.

## Testing Expectations

- Add or update pytest coverage for parser behavior, snapshot/storage changes,
  registry validation, and CLI/pipeline changes.
- For dbt work, add dbt tests alongside models where practical. Assert each
  Silver model's natural row grain (not just its positional surrogate key) with
  `dbt_utils.unique_combination_of_columns`, error where the grain is structurally
  guaranteed and warn where source faithfulness allows repeats. `dbt_utils` is a
  project dependency; run `make dbt-deps` once before building.
- For docs-only changes, verify links and commands against the actual source
  tree.

## Domain Reference Documents

These tracked documents orient agents working with HPT data semantics. Do not
pull them in for structural or tooling tasks (parser changes, CLI work, storage
layout, test setup). Use them when you need to understand what the data means,
not how it is stored.

- `docs/domain/hpt-glossary.md` defines the project vocabulary.
- `docs/domain/cms-mrf-schema-notes.md` summarizes CMS schema behavior and the
  parser boundary.
- `docs/domain/cms-validation-rules.md` inventories CMS conformance checks and
  how they route through parser quarantine, validation, and Silver exclusion.
- `docs/decisions/0015-classify-methodology-and-amount-semantics.md` explains
  methodology and amount comparability semantics.
- `docs/decisions/0017-gold-comparability-framework.md` explains the Gold
  comparison tiers and denominator rules.

## Cautions

- Do not commit local data, DuckDB files, logs, or downloaded MRFs.
- Do not treat ignored planning, notes, prompts, or research as authoritative.
- Be explicit when describing planned components such as Airflow, Docker, and
  Terraform. Do not imply they are production-ready. Silver and Gold are
  implemented; Gold cross-hospital percentile/benchmark output is only as broad
  as the loaded corpus (3-hospital denominator floor).
