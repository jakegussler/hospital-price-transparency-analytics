# CLAUDE.md

Guidance for Claude Code working in this repository. This file is the entry
point; it imports the canonical agent guide and AI context, then adds a
command cheat sheet and the gotchas that most often trip up agents here.

## Imported context

The authoritative agent rules and compact project context live in dedicated
files. Read them before making non-trivial changes:

@AGENTS.md
@docs/ai/context.md

`AGENTS.md` is the source of truth for architecture, domain rules, data/storage
rules, documentation maintenance, and testing expectations. Do not duplicate or
contradict it here — update `AGENTS.md` when those rules change, and keep this
file limited to Claude Code workflow specifics.

## What this project is

A local-first data pipeline for CMS hospital machine-readable files (MRFs):
`registry → hpt download → raw files + snapshot metadata → hpt ingest → Bronze
Parquet → dbt/DuckDB Silver models`. Python owns structural parsing; dbt owns
semantic normalization. Requires Python 3.11+.

## Command cheat sheet

Prefer the `make` targets; they wrap the underlying commands consistently.

```bash
# Setup
make install-dev                 # pip install -e ".[dev,warehouse]"

# Python quality checks — run these before considering a change done
make test                        # pytest tests/
make lint                        # ruff check src/ tests/ scripts/
make format                      # ruff format src/ tests/ scripts/

# Run a single test
pytest tests/parsers/test_csv_tall.py -k some_case

# Pipeline (Python)
make download                    # hpt download
make ingest                      # hpt ingest   (NOT `hpt parse` — see gotchas)

# Registry seed export (does not invoke dbt)
make export-hospitals-seed

# dbt build: scope to changed models (or use a named selector)
hpt run-dbt --command build --select slv_core__payer_rates+
hpt run-dbt --command build --selector validation
hpt run-dbt --command build --select gld_+
```

Never invoke `dbt` directly or use `make dbt-*` targets. Always use `hpt run-dbt`
with one node-scoping flag (`--select` or `--selector`; mutually exclusive).
Never pass `--all-hospitals`, `--per-snapshot`, `--full-refresh`, `--full-rebuild`,
or `--defer-tests`; do not pass `--seeds` unless the change specifically requires
seed validation. The dataset is small enough that full builds across all snapshots
are fast — no snapshot-pinning is needed.

dbt selectors available (`--selector`): `staging`, `silver_base`, `silver_core`,
`silver_review_queue`, `silver_audit`, `silver`, `validation`,
`pipeline_snapshot_metadata`, `pipeline_charge_data`. Or pass `--select` with
model node selection and graph operators (`model`, `model+`, `+model`, `@model`)
to target arbitrary models — mutually exclusive with `--selector`.

## Code map

- `src/hpt/cli.py` — Typer CLI (`download`, `ingest`, `export-hospitals-seed`,
  `run-dbt`, `clear-snapshot`). Thin: builds config objects and runs a process.
- `src/hpt/ingest/` — config, HTTP download, raw storage, compression, snapshot
  metadata, format detection, schema sniffing.
- `src/hpt/parsers/` — JSON, CSV Tall, CSV Wide, and header parsing.
- `src/hpt/loaders/parquet.py` — Bronze Parquet writer.
- `src/hpt/pipeline/ingest_snapshot.py` — ingest orchestration.
- `src/hpt/pipeline/dbt_config.py` / `dbt_manager.py` / `dbt_orchestrator.py` —
  dbt run config (modes, validation, list-normalized inputs), the dbtRunner
  wrapper, and run-mode orchestration (scoped / all-current / per-snapshot /
  full-rebuild, selector iteration).
- `src/hpt/registry/` — bundled hospital registry loader and models.
- `transform/` — dbt project targeting DuckDB (Bronze sources + Silver models).
- `tests/` — pytest suite mirroring `src/hpt/` layout.

## Gotchas (Claude-specific)

- **CLI is `hpt ingest`, never `hpt parse`.** Stale docs/prompts may reference
  `hpt parse`; it does not exist. Do not introduce it.
- **Agents invoke dbt only through `hpt run-dbt`.** Scope the node graph with
  `--select <model>[+]` (preferred) or a named `--selector`; never run direct,
  full-refresh, or `--defer-tests` dbt commands.
- **`--select` leaves out-of-graph models stale.** A bare `--select model`
  rebuilds only that node; use `model+` to also rebuild the downstream you
  changed, or the validation/test against stale children will mislead you.
- **Bronze stays source-faithful.** No business normalization, payer matching,
  code rollups, or hospital identity resolution in Bronze parsers — that belongs
  in dbt Silver/Gold.
- **Never commit local runtime artifacts.** `data/`, `logs/`, `*.duckdb`,
  downloaded MRFs, and quarantine output are git-ignored on purpose.
- **Preserve snapshot lineage** (`snapshot_id`, `file_hash`, source URL, source
  filename, ingest timestamps) through every downstream layer.
- **`fsspec` is intentional.** Don't hard-code local-only paths in
  ingest/download code.
- **Distinguish implemented from planned.** Airflow, Docker, and Terraform are
  placeholders — don't describe them as production-ready. Gold is implemented
  (`docs/architecture/gold-schema.md`, decisions 0017/0018), but its
  cross-hospital percentile/benchmark output is bounded by the loaded corpus
  (3-hospital denominator floor).
- **`docs/notes/` and `docs/planning/` are history, not authoritative.** Record
  known mismatches you don't fix in `docs/cleanup.md`.

## When you need domain meaning vs. structure

For *what the data means* (charge types, methodologies, CMS schema intent), see
`docs/local/industry_guide.md`, `docs/local/methodologies_algorithms.md`, and
`docs/cms_reference/`. For *how it's stored/parsed* (tooling, storage, tests),
use the architecture and development docs listed in `docs/ai/context.md`.
Task-specific prompt patterns live in `docs/ai/prompting-guide.md`.
