.PHONY: install install-dev test lint format download ingest export-hospitals-seed \
	dbt-run-hospitals dbt-run-all-hospitals dbt-incremental dbt-rebuild \
	dbt-per-snapshot dbt-per-snapshot-full-refresh \
	require-hospital-ids require-dbt-incremental-scope \
	dbt-deps dbt-run dbt-run-selector dbt-test dbt-test-selector \
	dbt-unit-test dbt-seed dbt-seed-selector dbt-build dbt-build-selector \
	dbt-build-validation \
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
	ruff check src/ tests/ scripts/

format:
	ruff format src/ tests/ scripts/

# --- Pipeline (Python) -----------------------------------------------------

download:
	hpt download

ingest:
	hpt ingest

export-hospitals-seed:
	hpt export-hospitals-seed

# Snapshot-scoped dbt run: resolves HOSPITAL_IDS to their current snapshots and
# scopes the dbt build to just those snapshots (prunes Bronze partitions).
dbt-run-hospitals: require-hospital-ids
	hpt run-dbt --hospital-ids "$(HOSPITAL_IDS)" --command build

dbt-run-all-hospitals:
	hpt run-dbt --all-hospitals --command build

dbt-incremental: require-dbt-incremental-scope
	hpt run-dbt \
		$(if $(HOSPITAL_IDS),--hospital-ids "$(HOSPITAL_IDS)") \
		$(if $(SNAPSHOT_IDS),--snapshot-ids "$(SNAPSHOT_IDS)") \
		--command build $(if $(DBT_SELECTOR),--selector "$(DBT_SELECTOR)")

dbt-rebuild:
	hpt run-dbt --full-rebuild --command build

# Per-snapshot (incremental): same six-pass Gold ordering as
# dbt-per-snapshot-full-refresh but without --full-refresh.
dbt-per-snapshot:
	hpt run-dbt \
		--per-snapshot \
		--defer-tests \
		--seeds \
		--selector per_snapshot
	hpt run-dbt \
		--all-hospitals \
		--defer-tests \
		--seeds \
		--selector gold_dimension \
		--command build
	hpt run-dbt \
		--per-snapshot \
		--defer-tests \
		--selector gold_per_snapshot
	hpt run-dbt \
		--all-hospitals \
		--defer-tests \
		--selector gold_marts \
		--command build
	hpt run-dbt \
		--all-hospitals \
		--defer-tests \
		--selector gold_scorecards \
		--command build
	hpt run-dbt \
		--all-hospitals \
		--defer-tests \
		--selector gold_bi \
		--command build
	hpt run-dbt \
		--all-hospitals \
		--selector audit \
		--command build

# Per-snapshot full refresh: rebuild snapshot-grained incremental tables from
# scratch (full-refresh on the first snapshot, append the rest), then rebuild
# operational audit views once (they read append-only run Parquet, not
# snapshot-scoped Silver). --defer-tests on the per-snapshot pass materializes
# every snapshot with run, prunes once, then runs one unscoped test pass.
#
# Gold is refreshed in five ordered passes around the per-snapshot fact:
#   1. gold_dimension  - run-once full-refresh dimensions, built UNscoped AFTER
#      the per-snapshot Silver pass completes (dimensions read unscoped Silver,
#      so they need every snapshot accumulated) and BEFORE the per-snapshot Gold
#      fact, so the fact's relationships tests against the dimensions can pass.
#   2. gold_per_snapshot - the snapshot-grained fact (gld_core__rate_observations)
#      and code bridge, built per snapshot (full-refresh the first, append the
#      rest), reading inputs through hpt_scoped_ref. Built after the dimensions
#      so the dimensions are up-to-date by the time the fact is created.
#   3. gold_marts      - run-once full-refresh marts, built UNscoped AFTER the
#      per-snapshot Gold fact completes (marts read the completed fact and
#      dimensions).
#   4. gold_scorecards - run-once full-refresh coverage/transparency scorecards,
#      built UNscoped AFTER the marts (they read the completed fact, bridge, and
#      the snapshot coverage scorecard).
#   5. gold_bi         - run-once full-refresh BI presentation marts, built
#      UNscoped AFTER the marts and scorecards (they read the completed Gold
#      analytics surfaces).
# Each Gold pass re-runs seeds only where the pass's models depend on them
# directly: the dimensions read the canonical_payers and states seeds; the
# per-snapshot fact/bridge and the marts read already-built Silver/Gold models
# and so omit --seeds. --defer-tests batches each pass's tests into a trailing
# unscoped test pass that runs after that pass's materialization.
dbt-per-snapshot-full-refresh:
	hpt run-dbt \
		--per-snapshot \
		--full-refresh \
		--defer-tests \
		--seeds \
		--selector per_snapshot
	hpt run-dbt \
		--all-hospitals \
		--defer-tests \
		--seeds \
		--selector gold_dimension \
		--command build
	hpt run-dbt \
		--per-snapshot \
		--full-refresh \
		--defer-tests \
		--selector gold_per_snapshot
	hpt run-dbt \
		--all-hospitals \
		--defer-tests \
		--selector gold_marts \
		--command build
	hpt run-dbt \
		--all-hospitals \
		--defer-tests \
		--selector gold_scorecards \
		--command build
	hpt run-dbt \
		--all-hospitals \
		--defer-tests \
		--selector gold_bi \
		--command build
	hpt run-dbt \
		--all-hospitals \
		--selector audit \
		--command build

require-hospital-ids:
	@test -n "$(HOSPITAL_IDS)" || (printf '%s\n' 'Set HOSPITAL_IDS, for example: make dbt-run-hospitals HOSPITAL_IDS=some-hospital' >&2; exit 2)

require-dbt-incremental-scope:
	@test -n "$(HOSPITAL_IDS)$(SNAPSHOT_IDS)" || (printf '%s\n' 'Set HOSPITAL_IDS or SNAPSHOT_IDS, for example: make dbt-incremental HOSPITAL_IDS=some-hospital' >&2; exit 2)

# --- dbt -------------------------------------------------------------------

DBT_SELECTOR ?=

dbt-deps:
	cd transform && dbt deps --profiles-dir .

dbt-run: require-dbt-incremental-scope
	hpt run-dbt \
		$(if $(HOSPITAL_IDS),--hospital-ids "$(HOSPITAL_IDS)") \
		$(if $(SNAPSHOT_IDS),--snapshot-ids "$(SNAPSHOT_IDS)") \
		--command run

dbt-run-selector: require-dbt-incremental-scope require-dbt-selector
	hpt run-dbt \
		$(if $(HOSPITAL_IDS),--hospital-ids "$(HOSPITAL_IDS)") \
		$(if $(SNAPSHOT_IDS),--snapshot-ids "$(SNAPSHOT_IDS)") \
		--command run --selector "$(DBT_SELECTOR)"

dbt-test:
	cd transform && dbt test --profiles-dir .

dbt-test-selector: require-dbt-selector
	cd transform && dbt test --selector "$(DBT_SELECTOR)" --profiles-dir .

dbt-unit-test:
	cd transform && dbt test --resource-type unit_test --profiles-dir .

dbt-seed:
	cd transform && dbt seed --profiles-dir .

dbt-seed-selector: require-dbt-selector
	cd transform && dbt seed --selector "$(DBT_SELECTOR)" --profiles-dir .

dbt-build: require-dbt-incremental-scope
	hpt run-dbt \
		$(if $(HOSPITAL_IDS),--hospital-ids "$(HOSPITAL_IDS)") \
		$(if $(SNAPSHOT_IDS),--snapshot-ids "$(SNAPSHOT_IDS)") \
		--command build

dbt-build-selector: require-dbt-incremental-scope require-dbt-selector
	hpt run-dbt \
		$(if $(HOSPITAL_IDS),--hospital-ids "$(HOSPITAL_IDS)") \
		$(if $(SNAPSHOT_IDS),--snapshot-ids "$(SNAPSHOT_IDS)") \
		--command build --selector "$(DBT_SELECTOR)"

dbt-build-validation: require-dbt-incremental-scope
	hpt run-dbt \
		$(if $(HOSPITAL_IDS),--hospital-ids "$(HOSPITAL_IDS)") \
		$(if $(SNAPSHOT_IDS),--snapshot-ids "$(SNAPSHOT_IDS)") \
		--command build --selector validation

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
