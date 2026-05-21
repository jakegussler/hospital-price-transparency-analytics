# Getting Started

This guide covers local development for the current Python pipeline and
dbt/DuckDB project.

## Requirements

- Python 3.11 or newer.
- A shell environment that can create virtual environments.
- Optional: dbt with the DuckDB adapter for transform work.

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

## Verify The Environment

```bash
make test
make lint
hpt --help
```

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
cd transform
dbt run --profiles-dir .
dbt test --profiles-dir .
```

The profile reads:

- `HPT_DUCKDB_PATH`, defaulting to `../data/hpt.duckdb`.
- `HPT_BRONZE_ROOT`, defaulting to `../data/bronze`.

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
