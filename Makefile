.PHONY: install install-dev test lint format download ingest dbt-run dbt-test dbt-seed dbt-build dbt-clean clean

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

dbt-run:
	cd transform && dbt run

dbt-test:
	cd transform && dbt test

dbt-seed:
	cd transform && dbt seed

dbt-build:
	cd transform && dbt build

dbt-clean:
	cd transform && dbt clean

# --- Cleanup ---------------------------------------------------------------

clean:
	rm -rf transform/target transform/dbt_packages
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	rm -rf *.egg-info src/*.egg-info
