# Hospital Price Transparency

Hospital Price Transparency is a local-first data pipeline for ingesting,
normalizing, and analyzing CMS hospital machine-readable files (MRFs). The
current implementation focuses on downloading hospital source files, tracking
file snapshots, parsing JSON and CSV MRF layouts, and writing source-faithful
Bronze Parquet tables for downstream dbt/DuckDB modeling.

## Current Status

Implemented today:

- Python package and CLI under `src/hpt`.
- Registry-driven MRF download with SHA-256 change detection.
- Raw file and snapshot metadata storage through `fsspec`.
- JSON, CSV Tall, and CSV Wide Bronze parsers.
- Bronze Parquet writer partitioned by `snapshot_id`.
- dbt project skeleton targeting DuckDB, with Bronze external sources.
- pytest coverage for config, registry, storage, snapshots, download, parsers,
  Bronze writing, and ingest orchestration.

Planned or early-stage:

- Silver and Gold dbt models.
- Airflow orchestration under `orchestration/`.
- Docker and Terraform under `infra/`.
- Curated production registry workflow.
- Analytics-facing documentation and dashboards.

## Repository Map

```text
src/hpt/             Python package and CLI
tests/               pytest test suite
docs/                Project documentation and reference notes
transform/           dbt project, currently targeting DuckDB
registry/            Experimental registry files and notes
adhoc_scripts/       One-off exploration scripts
scripts/             Placeholder for reusable utility scripts
infra/               Placeholder for Docker and Terraform
orchestration/       Placeholder for Airflow DAGs and plugins
data/                Local runtime data, ignored by git
```

## Quickstart

Use Python 3.11 or newer.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev,warehouse]"
```

Run the test suite:

```bash
make test
```

Download MRF files from the active registry:

```bash
hpt download
```

Parse current downloaded snapshots into Bronze Parquet:

```bash
hpt ingest
```

Run dbt against the DuckDB project:

```bash
cd transform
dbt run --profiles-dir .
dbt test --profiles-dir .
```

By default, local raw files, snapshot metadata, Bronze Parquet, quarantine
records, and DuckDB files live under `data/`.

## Core Commands

```bash
make install-dev
make test
make lint
make format
hpt download --help
hpt ingest --help
```

The CLI commands are the source of truth for pipeline execution. Use
`hpt ingest` for parsing downloaded snapshots into Bronze Parquet.

## Documentation

Start here:

- `docs/architecture/pipeline-overview.md` explains the implemented pipeline.
- `docs/architecture/medallion-layers.md` defines Bronze, Silver, and Gold
  responsibilities.
- `docs/architecture/storage-layout.md` describes raw, metadata, Bronze,
  quarantine, and DuckDB paths.
- `docs/architecture/bronze-schema.md` diagrams the implemented Bronze schema.
- `docs/architecture/silver-schema.md` diagrams the target Silver schema.
- `docs/domain/hpt-glossary.md` defines project and CMS terms.
- `docs/domain/cms-mrf-schema-notes.md` summarizes JSON, CSV Tall, and CSV Wide
  MRF layouts.
- `docs/domain/hospital-registry-rules.md` explains the registry contract.
- `docs/development/getting-started.md` covers local setup and first runs.
- `docs/development/testing-strategy.md` explains test coverage expectations.
- `docs/development/common-debugging-notes.md` collects common failure modes.
- `docs/cleanup.md` tracks known code/doc alignment issues.

Existing detailed references:

- `docs/bronze_layer.md`
- `docs/configuration.md`
- `docs/header_parsing.md`
- `docs/format_templates/`

## Design Direction

This project uses a medallion pattern:

- Bronze preserves source-faithful parsed records with minimal interpretation.
- Silver will normalize charge items, codes, payers, plans, modifiers, hospitals,
  and dates.
- Gold will answer analytics questions about price variation, payer behavior,
  hospital comparisons, and compliance.

DuckDB is the expected local analytical database. Polars handles parser-side
DataFrame construction and Parquet writing. dbt will own Silver and Gold SQL
models.
