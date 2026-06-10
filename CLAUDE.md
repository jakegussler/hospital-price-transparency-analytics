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

# dbt validation: always one pinned snapshot and the smallest relevant selector
hpt run-dbt --snapshot-ids 97e28644-a4fc-4b3c-9c5c-8e9cf650500e --command build --selector validation
```

For agent-run dbt validation, never invoke `dbt` directly or use the full-corpus
`make dbt-*` targets. Always call `hpt run-dbt` with exactly one explicit
`--snapshot-ids` value and one non-empty, smallest relevant `--selector`. Never
omit the selector to build the whole dbt graph. Never use
`--hospital-ids`, `--all-hospitals`, `--per-snapshot`, `--full-refresh`, or
`--full-rebuild`; do not pass `--seeds` unless the change specifically requires
seed validation. The canonical rules and pinned CSV Wide, CSV Tall, and JSON
snapshot IDs are in `AGENTS.md`, including larger CSV Tall and JSON options for
cases that need more representative row volume.

If verification truly needs a full refresh or full rebuild, do not run dbt.
Report that full-refresh verification is still needed, why the scoped snapshot
run is insufficient, and the exact verification command or scope the user should
run outside the agent workflow.

`hpt run-dbt` passes the explicit snapshot as the `snapshot_ids` dbt var, which
prunes Bronze hive partitions and bounds memory. A partial selector can leave
out-of-selector models stale, so broaden the selector only when the smallest
targeted run cannot validate the change. See
`docs/development/snapshot-scoped-runs.md` for implementation details, not for
permission to use its unscoped/full-refresh examples.

dbt selectors available: `staging`, `silver_base`, `silver_core`,
`silver_review_queue`, `silver`, `validation`,
`pipeline_snapshot_metadata`, `pipeline_charge_data`.

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
- **Agents invoke dbt only through `hpt run-dbt`.** Pin exactly one approved
  snapshot UUID and use the smallest relevant selector; never run direct,
  unscoped, per-snapshot-all, or full-refresh dbt commands.
- **Bronze stays source-faithful.** No business normalization, payer matching,
  code rollups, or hospital identity resolution in Bronze parsers — that belongs
  in dbt Silver/Gold.
- **Never commit local runtime artifacts.** `data/`, `logs/`, `*.duckdb`,
  downloaded MRFs, and quarantine output are git-ignored on purpose.
- **Preserve snapshot lineage** (`snapshot_id`, `file_hash`, source URL, source
  filename, ingest timestamps) through every downstream layer.
- **`fsspec` is intentional.** Don't hard-code local-only paths in
  ingest/download code.
- **Distinguish implemented from planned.** Gold models, Airflow, Docker, and
  Terraform are placeholders. Don't describe them as production-ready.
- **`docs/notes/` and `docs/planning/` are history, not authoritative.** Record
  known mismatches you don't fix in `docs/cleanup.md`.

## When you need domain meaning vs. structure

For *what the data means* (charge types, methodologies, CMS schema intent), see
`docs/local/industry_guide.md`, `docs/local/methodologies_algorithms.md`, and
`docs/cms_reference/`. For *how it's stored/parsed* (tooling, storage, tests),
use the architecture and development docs listed in `docs/ai/context.md`.
Task-specific prompt patterns live in `docs/ai/prompting-guide.md`.
