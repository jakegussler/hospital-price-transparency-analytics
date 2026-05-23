.PHONY: install install-dev test lint format download ingest \
	dbt-deps dbt-run dbt-run-selector dbt-test dbt-test-selector \
	dbt-seed dbt-seed-selector dbt-build dbt-build-selector \
	dbt-ls dbt-ls-selector dbt-compile dbt-compile-selector dbt-clean \
	require-dbt-selector clean

# --- Python ----------------------------------------------------------------

install:
	pip install -e .

install-dev:
	pip install -e ".[dev,warehouse]"

test:
	pytest tests/

lint:
	ruff check src/ tests/

format:
	ruff format src/ tests/

# --- Pipeline (Python) -----------------------------------------------------

download:
	hpt download

ingest:
	hpt ingest

# --- dbt -------------------------------------------------------------------

DBT_SELECTOR ?=

dbt-deps:
	cd transform && dbt deps --profiles-dir .

dbt-run:
	cd transform && dbt run --profiles-dir .

dbt-run-selector: require-dbt-selector
	cd transform && dbt run --selector "$(DBT_SELECTOR)" --profiles-dir .

dbt-test:
	cd transform && dbt test --profiles-dir .

dbt-test-selector: require-dbt-selector
	cd transform && dbt test --selector "$(DBT_SELECTOR)" --profiles-dir .

dbt-seed:
	cd transform && dbt seed --profiles-dir .

dbt-seed-selector: require-dbt-selector
	cd transform && dbt seed --selector "$(DBT_SELECTOR)" --profiles-dir .

dbt-build:
	cd transform && dbt build --profiles-dir .

dbt-build-selector: require-dbt-selector
	cd transform && dbt build --selector "$(DBT_SELECTOR)" --profiles-dir .

dbt-ls:
	cd transform && dbt ls --profiles-dir .

dbt-ls-selector: require-dbt-selector
	cd transform && dbt ls --selector "$(DBT_SELECTOR)" --profiles-dir .

dbt-compile:
	cd transform && dbt compile --profiles-dir .

dbt-compile-selector: require-dbt-selector
	cd transform && dbt compile --selector "$(DBT_SELECTOR)" --profiles-dir .

dbt-clean:
	cd transform && dbt clean --profiles-dir .

require-dbt-selector:
	@test -n "$(DBT_SELECTOR)" || (printf '%s\n' 'Set DBT_SELECTOR, for example: make dbt-run-selector DBT_SELECTOR=silver' >&2; exit 2)

# --- Cleanup ---------------------------------------------------------------

clean:
	rm -rf transform/target transform/dbt_packages
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	rm -rf *.egg-info src/*.egg-info
