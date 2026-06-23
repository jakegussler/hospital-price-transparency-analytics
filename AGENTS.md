# Agent Guide

This file gives coding agents project context. Keep it aligned with the docs in
`docs/`; future Cursor rules should be distilled from this guide rather than
invented separately.

## Project Purpose

Hospital Price Transparency ingests CMS hospital MRFs, tracks source-file
snapshots, parses JSON and CSV layouts into Bronze Parquet, and prepares the data
for dbt/DuckDB normalization and analysis.

## Current Architecture

- `src/hpt/cli.py` exposes `hpt download`, `hpt ingest`, `hpt run-dbt`, and
  `hpt clear-snapshot`. It is a thin layer that builds config objects and runs a
  process.
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
hpt run-dbt --snapshot-ids <one-snapshot-id> --command build --selector <smallest-relevant-selector>
```

Use `hpt ingest` for parsing. Do not document or call `hpt parse` unless the CLI
is changed to provide it.

## dbt Agent Safety Rules

Agents must validate dbt changes with the smallest possible snapshot-scoped run.

- Never invoke `dbt` directly, including `cd transform && dbt ...`.
- Never use unscoped/full-corpus Make targets such as `make dbt-run`,
  `make dbt-test`, `make dbt-build`, or `make dbt-rebuild`.
- Always use the `hpt run-dbt` CLI layer and pass exactly one explicit
  `--snapshot-ids` value. Pin the snapshot UUID rather than using
  `--hospital-ids`, whose current snapshot can change.
- Never pass `--all-hospitals`, `--per-snapshot`, `--full-refresh`, or
  `--full-rebuild`.
- If correctness requires a full refresh or full rebuild to verify, do not run
  dbt. State that full-refresh verification is still needed, explain why the
  scoped validation is insufficient, and tell the user exactly which verification
  command or scope should be run outside the agent workflow.
- Always pass one non-empty `--selector`; never omit it to build the whole dbt
  graph. Use the smallest selector/model and command that exercise the change,
  broadening scope only when the targeted run cannot validate the behavior.
- Do not pass `--seeds` unless the change affects seed data or seed-dependent
  behavior.

Use these pinned local snapshots consistently. Prefer the small snapshots for
simple logic validation; choose the larger snapshots only when the change needs
more representative row volume or source complexity.

| Size | Format | Hospital | Snapshot ID | Approximate local size |
|---|---|---|---|---|
| Small | CSV Wide | Lincoln Health System | `cd725773-f575-45dd-a796-adf9c9805a14` | 8.6 MB raw; 0.8 MB Bronze |
| Small | CSV Tall | Ballad Sycamore | `209991a1-5cfa-42b8-a2bf-9e40595898db` | 4.8 MB raw ZIP; 8.5 MB Bronze |
| Small | JSON | NGMC Gainesville | `97e28644-a4fc-4b3c-9c5c-8e9cf650500e` | 2.0 MB raw; 3.2 MB Bronze |
| Larger | CSV Tall | Ballad JCMC | `7ca24003-a8af-4e11-8f29-4587ffb22506` | 5.6 MB raw ZIP; 9.7 MB Bronze |
| Larger | JSON | Vanderbilt University Medical Center | `8fa7c1b7-ea2e-4c1d-b38b-ae23899921bc` | 1.9 GB raw; 30.1 MB Bronze |

Example:

```bash
hpt run-dbt \
  --snapshot-ids 97e28644-a4fc-4b3c-9c5c-8e9cf650500e \
  --command build \
  --selector validation
```

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
- For dbt work, add dbt tests alongside models where practical. Assert each
  Silver model's natural row grain (not just its positional surrogate key) with
  `dbt_utils.unique_combination_of_columns`, error where the grain is structurally
  guaranteed and warn where source faithfulness allows repeats. `dbt_utils` is a
  project dependency; run `make dbt-deps` once before building.
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
