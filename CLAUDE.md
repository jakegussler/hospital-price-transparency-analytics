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

# dbt / DuckDB (always run from transform/ with --profiles-dir .)
make export-hospitals-seed
make dbt-seed
make dbt-run
make dbt-test
make dbt-build
make dbt-build-selector DBT_SELECTOR=silver
```

dbt selectors available: `staging`, `silver_base`, `silver_core`,
`silver_review_queue`, `silver`, `validation`,
`pipeline_snapshot_metadata`, `pipeline_charge_data`.

## Code map

- `src/hpt/cli.py` — Typer CLI (`download`, `ingest`, `export-hospitals-seed`).
- `src/hpt/ingest/` — config, HTTP download, raw storage, compression, snapshot
  metadata, format detection, schema sniffing.
- `src/hpt/parsers/` — JSON, CSV Tall, CSV Wide, and header parsing.
- `src/hpt/loaders/parquet.py` — Bronze Parquet writer.
- `src/hpt/pipeline/ingest_snapshot.py` — ingest orchestration.
- `src/hpt/registry/` — bundled hospital registry loader and models.
- `transform/` — dbt project targeting DuckDB (Bronze sources + Silver models).
- `tests/` — pytest suite mirroring `src/hpt/` layout.

## Gotchas (Claude-specific)

- **CLI is `hpt ingest`, never `hpt parse`.** Stale docs/prompts may reference
  `hpt parse`; it does not exist. Do not introduce it.
- **dbt must run from `transform/` with `--profiles-dir .`.** The `make dbt-*`
  targets already `cd transform` for you; replicate that if invoking dbt
  directly.
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
