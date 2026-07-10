# Getting Started

This guide covers local development for the current Python pipeline and
dbt/DuckDB project.

## Requirements

- Python 3.11 or newer.
- A shell environment that can create virtual environments.
- DuckDB 1.5.2 or newer and dbt with the DuckDB adapter for transform work.

## Install

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev,warehouse]"
```

The repository includes `uv.lock`, but the current Makefile uses `pip`. Use one
environment manager consistently within a working copy.

For dbt work, also install `dbt-duckdb` in the active environment if it is not
already available.

Use DuckDB 1.5.2 or newer consistently across the Python environment and any
separately installed DuckDB CLI or UI. DuckDB 1.5.0 cannot checkpoint the
project's stored dynamic `UNPIVOT ... COLUMNS(regex)` staging view and can leave
a WAL that fails on the next open with:

```text
checkpoint WAL cannot contain a checkpoint marker
```

Close DuckDB CLI/UI sessions connected to `data/hpt.duckdb` before running dbt
writes. An open UI normally creates or retains `hpt.duckdb.wal`; the WAL's
presence alone does not indicate corruption.

## Verify The Environment

```bash
make test
make lint
hpt --help
python -c "import duckdb; print(duckdb.__version__)"
duckdb --version
```

The final command checks a separately installed DuckDB CLI, if present. Upgrade
it before opening the project database if it reports a version older than
1.5.2.

## Runtime Paths

Default local runtime output is under `data/`.

Common environment variables:

```bash
export HPT_RAW_STORAGE_BASE_URI=file:///absolute/path/to/project/data
export HPT_BRONZE_ROOT=/absolute/path/to/project/data/bronze
export HPT_QUARANTINE_ROOT=/absolute/path/to/project/data/quarantine
export HPT_DUCKDB_PATH=/absolute/path/to/project/data/hpt.duckdb
```

Most local development can use defaults and omit these exports.

## Download MRFs

Download every hospital in the active bundled registry:

```bash
hpt download
```

Download selected hospitals:

```bash
hpt download --hospital-ids ballad-jcmc,erlanger-baroness
```

Use a custom registry:

```bash
hpt download --registry-path path/to/hospitals.yml
```

## Ingest To Bronze

Parse current downloaded snapshots:

```bash
hpt ingest
```

Parse selected hospitals:

```bash
hpt ingest --hospital-ids ballad-jcmc
```

Use explicit local roots:

```bash
hpt ingest \
  --raw-base-uri file:///absolute/path/to/project/data \
  --bronze-root /absolute/path/to/project/data/bronze \
  --quarantine-root /absolute/path/to/project/data/quarantine
```

## Run dbt With DuckDB

From the repository root:

```bash
make export-hospitals-seed
make dbt-deps
hpt run-dbt --command build --seeds --hospital-ids ballad-jcmc
hpt run-dbt --command test --hospital-ids ballad-jcmc
hpt run-dbt --command build --hospital-ids ballad-jcmc --selector silver
hpt run-dbt --command build --hospital-ids ballad-jcmc --selector pipeline_charge_data
hpt run-dbt --full-rebuild --command build
```

The profile reads:

- `HPT_DUCKDB_PATH`, defaulting to `../data/hpt.duckdb`.
- `HPT_BRONZE_ROOT`, defaulting to `../data/bronze`.
- `HPT_AUDIT_ROOT`, defaulting to `../data/audit`.

The dbt project currently defines layer selectors for `staging`, `silver_base`,
`silver_core`, `silver_review_queue`, `silver_audit`, `silver`, and
`validation`; Gold selectors for `gold_core`, `gold_dimension`,
`gold_per_snapshot`, `gold_marts`, `gold_scorecards`, `gold_bi`, and `gold`; pipeline
selectors for `pipeline_snapshot_metadata` and `pipeline_charge_data`; and
operational selectors for `audit`, `audit_staging`, and `audit_marts` in
`transform/selectors.yml`.

Use `hpt run-dbt` for dbt execution. Snapshot-grained models use
`snapshot_replace`, so repeat incremental materialization without an explicit
snapshot scope is rejected. `hpt run-dbt --full-rebuild` is the canonical full
rebuild from all Bronze: it runs without `snapshot_ids` and passes dbt
`--full-refresh`.

`HPT_SILVER_RETENTION_MODE=current_only` is the default. It prunes non-current
snapshot rows from snapshot-grained Silver and validation tables after
successful materializing runs. Set `HPT_SILVER_RETENTION_MODE=all_snapshots` to
retain historical Silver/validation rows.

Layer and operational-domain tags live in `transform/dbt_project.yml`. Pipeline
selectors reuse the pipeline tags there so a single selector can span staging
and Silver models for the selected pipeline. Audit selectors are intentionally
unscoped from snapshots and only build views over `HPT_AUDIT_ROOT`.

## Build The Evidence BI App

The public Evidence app consumes generated Parquet artifacts from the Gold BI
presentation marts. Build through `hpt run-dbt`, export the allowlisted BI
tables, then run Evidence source extraction from `apps/evidence/`:

```bash
hpt run-dbt --command build --selector gold_bi
hpt run-dbt --command test --selector gold_bi
uv run python scripts/export_evidence_artifact.py --replace
cd apps/evidence
nvm use
npm ci
npm run sources
npm run dev
```

The export step is suitable for small end-to-end smoke checks, including a
single-hospital run: it requires the allowlisted marts to exist, but permits
empty Parquet files when denominator-gated BI marts have no rows. For a
public-demo corpus, run the optional readiness gate before exporting:

```bash
uv run python scripts/check_evidence_readiness.py
uv run python scripts/export_evidence_artifact.py --replace
```

Use `npm run dev -- --port 4000` if port 3000 is occupied. Production build
checks use `npm run sources && npm run build`.

The exporter writes only the documented BI marts under
`apps/evidence/sources/hpt/data/`, plus two generated artifacts
(`public_metadata` with a git `build_id`, and `public_data_dictionary` parsed
from `_gold_bi_models.yml`), and the public download bundle under
`apps/evidence/static/downloads/` (Parquet + CSV per mart; CSVs over 25 MB
gzip-compressed). All generated outputs are ignored by git. Evidence page SQL
should query `hpt.<source_name>` tables only.

## Ad Hoc Scripts

`adhoc_scripts/` contains exploration scripts for inspecting remote files,
profiling JSON paths, printing headers, and sniffing local raw files. Treat these
as disposable research utilities unless they are promoted into `scripts/`,
tested, and documented.

## Placeholder Areas

- `scripts/` is reserved for reusable project utilities.
- `infra/docker/` and `infra/terraform/` are placeholders for deployment
  infrastructure.
- `orchestration/dags/` and `orchestration/plugins/` are placeholders for
  Airflow.

Do not assume these folders represent active production workflows until code and
docs are added.
